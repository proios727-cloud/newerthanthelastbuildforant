"""Regime-switching BTC paper bot. One cycle per closed candle:

  candles+book (Binance) -> snapshot PNG -> Drex regime -> playbook signal -> Drex TAKE/SKIP + entry
  -> hard risk layer -> paper broker -> hash-chained log -> phone ping

Usage:  python bot.py            # run forever
        python bot.py --once     # one cycle, then exit
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

import risk
from binance import INTERVAL_MS, Binance
from broker import PaperBroker
from config import ROOT, STATE_DIR, Config
from drex import Drex, DrexError, load_questions, top
from features import book_features, candle_features
from journal import Journal
from notify import ping
from snapshot import render
from strategies import signal_for

log = logging.getLogger("bot")


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bx = Binance(cfg.binance_base)
        self.drex = Drex(cfg.drex_base, cfg.drex_model, cfg.drex_timeout_s)
        self.broker = PaperBroker(cfg, STATE_DIR / "paper.json")
        self.journal = Journal(STATE_DIR / "decisions.jsonl")

    def _event(self, ev: dict, candle_t: int):
        self.journal.log(ev.pop("event"), candle_t=candle_t, **ev)
        leg = ev.get("leg", "")
        if "pnl" in ev:
            ping(self.cfg, f"EXIT {ev['side']} {self.cfg.symbol} ({ev['reason']})",
                 f"{ev['entry']} -> {ev['exit']}  PnL {ev['pnl']:+.2f}  ({ev['r_multiple']:+.2f}R)  equity {ev['equity']:.2f}")
        elif leg == "entry":
            ping(self.cfg, f"ENTRY {ev['side']} {self.cfg.symbol} ({ev['order_type']})",
                 f"{ev['qty']} @ {ev['price']}  [paper]")

    def cycle(self) -> bool:
        cfg, b = self.cfg, self.broker
        candles = self.bx.closed_candles(cfg.symbol, cfg.interval, cfg.candles_lookback)
        k = candles[-1]
        last_t = b.s["last_candle_t"]
        if last_t == k["t"]:
            return False
        book = self.bx.depth(cfg.symbol, cfg.depth_limit)
        Q = load_questions()
        qv = Q["version"]

        # Settle paper orders/positions on every candle closed since last cycle (handles downtime).
        missed = [c for c in candles if last_t is not None and c["t"] > last_t]
        for c in missed or [k]:
            b.roll_day(c["t"])
            for ev in b.on_candle(c):
                self._event(ev, c["t"])
            b.tick_cooldown()
        b.s["last_candle_t"] = k["t"]

        cf, bf = candle_features(candles, cfg.atr_period), book_features(book)
        snap = render(candles, book, STATE_DIR / "snapshots" / f"{k['t']}.png",
                      f"{cfg.symbol} {cfg.interval}  close {k['c']:.2f}")
        state = {"symbol": cfg.symbol, "interval": cfg.interval, "candle_open_time_ms": k["t"],
                 "candle": cf, "order_book": bf,
                 "position": b.s["position"] and {x: b.s["position"][x] for x in ("side", "entry", "stop", "target")}}
        base = {"candle_t": k["t"], "q_version": qv, "snapshot": snap.name,
                "snapshot_sha256": hashlib.sha256(snap.read_bytes()).hexdigest()}

        # Step 3: regime with probabilities
        try:
            ra = self.drex.decide(state, Q["regime"], image=snap)
        except DrexError as e:
            self.journal.log("drex_error", stage="regime", error=str(e), **base)
            b.save()
            log.error("Drex regime failed (fail closed): %s", e)
            return True
        probs = ra["answers"]["regime"]["probabilities"]
        regime, rp = top(ra["answers"]["regime"])
        p_panic = float(probs.get("PANIC", 0))
        self.journal.log("regime", regime=regime, p=rp, probs=probs, model=ra.get("model"),
                         request_id=ra.get("request_id"), usage=ra.get("usage"), candle=cf, book=bf, **base)
        log.info("candle %s close %.2f  regime %s p=%.3f  %s", k["t"], k["c"], regime, rp, probs)

        # Step 4: PANIC = hands off (and optionally flatten)
        if p_panic >= cfg.panic_threshold:
            if b.s["pending"]:
                self.journal.log("order_cancelled", reason="PANIC", trade_id=b.s["pending"]["id"], **base)
                b.s["pending"] = None
            if b.s["position"] and cfg.panic_flatten:
                self._event(b.close_market(book, "PANIC_FLATTEN", k["close_time"]), k["t"])
            self.journal.log("hands_off", p_panic=p_panic, **base)
            b.save()
            return True

        if b.s["position"] or b.s["pending"] or rp < cfg.regime_threshold:
            b.save()
            return True

        sig = signal_for(regime, candles, cfg)
        if not sig:
            b.save()
            return True

        # Steps 5 + 6: TAKE/SKIP and entry style, one Drex call
        sid = b.new_id()
        sstate = {**state, "regime": {"label": regime, "p": rp, "probs": probs}, "proposed_trade": sig.as_dict()}
        try:
            sa = self.drex.decide(sstate, Q["signal"], image=snap)
        except DrexError as e:
            self.journal.log("drex_error", stage="signal", error=str(e), trade_id=sid, signal=sig.as_dict(), **base)
            b.save()
            return True
        ans = sa["answers"]
        take_p = float(ans["take"]["noul"])
        control, control_p = top(ans["book_control"])
        entry, entry_p = top(ans["entry"])
        self.journal.log("signal", trade_id=sid, signal=sig.as_dict(), regime=regime, regime_p=rp, take_p=take_p,
                         book_control=control, book_control_probs=ans["book_control"]["probabilities"],
                         entry=entry, entry_probs=ans["entry"]["probabilities"], model=sa.get("model"),
                         request_id=sa.get("request_id"), usage=sa.get("usage"), **base)

        # Step 7: hard risk layer
        v = risk.check(cfg, regime_p=rp, take_p=take_p, signal=sig, equity=b.s["equity"],
                       open_positions=int(bool(b.s["position"])), trades_today=b.s["trades_today"],
                       day_pnl=b.s["day_pnl"], day_start_equity=b.s["day_start_equity"], cooldown_left=b.s["cooldown"])
        decision = "TAKE" if v.ok and entry != "WAIT" else ("WAIT" if v.ok else "SKIP")
        self.journal.log("gate", trade_id=sid, decision=decision, ok=v.ok, reasons=v.reasons, qty=v.qty,
                         notional=v.notional, thresholds={"regime": cfg.regime_threshold, "take": cfg.take_threshold}, **base)
        if decision == "TAKE":
            if entry == "MARKET":
                ev = b.market_entry(sig.side, v.qty, book, sig.stop, sig.target, sid, k["close_time"])
            else:
                ev = b.place_limit(sig.side, v.qty, book, sig.stop, sig.target, sid)
                ping(cfg, f"LIMIT {sig.side} {cfg.symbol}", f"{v.qty} @ {ev['price']}  {sig.playbook}  TAKE p={take_p:.2f} [paper]")
            self._event(ev, k["t"])
        b.save()
        return True

    def maybe_review(self):
        """Step 8, run inside the worker (it owns the disk): once per UTC day after review_hour_utc."""
        now = datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        if now.hour < self.cfg.review_hour_utc or self.broker.s.get("last_review_day") == day:
            return
        r = subprocess.run([sys.executable, "review.py", "--hours", str(self.cfg.review_window_hours)],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        rep = STATE_DIR / "reports"
        from publish import publish
        published = publish({f"reviews/{day}.md": rep / f"review-{day}.md",
                             f"reviews/{day}-packet.json": rep / f"review-{day}-packet.json",
                             "reviews/latest.md": rep / f"review-{day}.md",
                             "reviews/latest-packet.json": rep / f"review-{day}-packet.json",
                             "reviews/paper.json": STATE_DIR / "paper.json",
                             "reviews/tuned.json": STATE_DIR / "tuned.json"}, day)
        self.broker.s["last_review_day"] = day
        self.broker.save()
        self.cfg = Config.load()  # pick up any thresholds the review tuned
        self.journal.log("review", day=day, returncode=r.returncode, published=published,
                         stderr=r.stderr[-1500:], thresholds={"take": self.cfg.take_threshold, "regime": self.cfg.regime_threshold})
        ping(self.cfg, f"Nightly review {day}",
             f"equity {self.broker.s['equity']:.2f}  take>={self.cfg.take_threshold}  published={published}")

    def run(self):
        ms = INTERVAL_MS[self.cfg.interval]
        self.journal.log("start", config=self.cfg.as_dict())
        while True:
            try:
                self.cycle()
            except Exception as e:  # keep running; everything is logged
                log.exception("cycle failed")
                self.journal.log("error", error=repr(e))
            try:
                self.maybe_review()
            except Exception as e:
                log.exception("nightly review failed")
                self.journal.log("error", stage="review", error=repr(e))
            now = int(time.time() * 1000)
            time.sleep(max(5.0, ((now // ms + 1) * ms - now) / 1000 + 3))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot = Bot(Config.load())
    bot.cycle() if a.once else bot.run()
