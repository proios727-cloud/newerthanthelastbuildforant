"""Stage 3: replay GM x A-S vs pure A-S quoting on recorded Kalshi tape. Read-only.

    python -m gmdesk.replay --data data/gm --series KXBTC15M

Honesty rules baked in:
  * every toxicity parameter is fitted on the train markets only; results are reported on test
  * quotes refresh at most once per `latency_s`, from information strictly before each trade
  * a fill needs a real trade printing *through* our price (equal price = behind the queue, no fill)
  * maker fee charged on every fill; P&L settled at the market's real result
Gate 3: GM x A-S beats pure A-S on test with a market-bootstrap 95% CI above zero AND is net
positive after fees. Otherwise the layer is not earning its keep.
"""
import argparse
import json
import math
import os
import random
import sys

from .analyze import TAU, annotate, bucket_size, load, quantiles, split, which, clustered
from .core import VPIN, Monitor, maker_fee, position_limit

DEFAULTS = dict(size=5, base_limit=25, base_half_c=1.0, inv_skew_c=0.15, latency_s=1.0, alpha=0.2,
                fee_rate=0.0175, edge_lo=0.03, edge_hi=0.97)


def fit(train, n=20):
    """Learn from train: VPIN bucket/cuts, adverse cost per VPIN quintile, toxic time buckets, warn/halt."""
    bucket = bucket_size(train)
    rows = [r for r in annotate(train, bucket, n) if r["vpin"] is not None]
    cuts = quantiles([r["vpin"] for r in rows])
    adverse = []
    for k in range(5):
        b = clustered([r for r in rows if which(r["vpin"], cuts) == k])
        adverse.append(max(0.0, -(b["mean_c"] or 0.0)))
    stop_tau = 0
    for lo, hi, lab in TAU:
        b = clustered([r for r in rows if lo <= r["tau"] < hi])
        if b["mean_c"] is not None and b["mean_c"] + 2 * b["se_c"] < 0:
            stop_tau = max(stop_tau, hi)            # makers lose with confidence here: stop quoting
    stop_tau = min(stop_tau, 600)
    vs = sorted(r["vpin"] for r in rows)
    return {"bucket": bucket, "n": n, "cuts": cuts, "adverse_c": adverse, "stop_tau": stop_tau,
            "warn": vs[int(len(vs) * 0.80)], "halt": vs[int(len(vs) * 0.95)]}


class Book:
    def __init__(self):
        self.cash = self.inv = self.fees = 0.0
        self.fills = self.contracts = 0
        self.adverse = 0.0

    def fill(self, side, px, q, fee_rate):
        """side +1 = we buy YES at px, -1 = we sell YES at px."""
        self.cash -= side * px * q
        self.inv += side * q
        f = maker_fee(px, q, fee_rate)
        self.cash -= f
        self.fees += f
        self.fills += 1
        self.contracts += q


class Quoter:
    """One market's quoting brain. Shared by replay, live shadow and the executor so all three agree.

    on_trade(r) -> fill dict or None   (checks the resting quote, then updates mid + VPIN)
    requote(ts) -> (bid, ask, limit) or None, recomputed at most once per latency_s
    """

    def __init__(self, close_ts, model, cfg, gm, vpin):
        self.close_ts, self.model, self.cfg, self.gm, self.vpin = close_ts, model, cfg, gm, vpin
        self.bk = Book()
        self.mon = Monitor(model["warn"], model["halt"]) if gm else None
        self.mid, self.last_q, self.quote, self.status = None, -1e18, None, "ACTIVE"

    def requote(self, ts):
        cfg, model = self.cfg, self.model
        if self.mid is None or ts - self.last_q < cfg["latency_s"]:
            return self.quote
        self.last_q, self.quote = ts, None
        tau, v = self.close_ts - ts, self.vpin.value
        limit, half = cfg["base_limit"], cfg["base_half_c"] / 100
        off = self.gm and tau < model["stop_tau"]
        self.status = "ACTIVE"
        if self.gm and not off:
            self.status = self.mon.update(v)
            mult = self.mon.multiplier(v)
            if mult is None:
                off = True
            else:
                limit = position_limit(cfg["base_limit"], self.mon.pressure(v))
                adv = model["adverse_c"][which(v, model["cuts"]) if v is not None else 2]
                half = (half + adv / 100) * mult
        if off:
            self.status = "HALTED"
        elif cfg["edge_lo"] < self.mid < cfg["edge_hi"]:
            res = self.mid - self.bk.inv * cfg["inv_skew_c"] / 100 * min(1.0, tau / 900)
            bid = math.floor((res - half) * 100) / 100
            ask = math.ceil((res + half) * 100) / 100
            self.quote = (max(0.01, bid), min(0.99, ask), limit)
        return self.quote

    def on_trade(self, r):
        fill, bk, cfg = None, self.bk, self.cfg
        if self.quote:
            bid, ask, limit = self.quote
            if r["s"] > 0 and r["p"] > ask and bk.inv > -limit:          # taker bought YES through our ask
                q = min(r["q"], cfg["size"], limit + bk.inv)
                bk.fill(-1, ask, q, cfg["fee_rate"]); fill = {"side": "sell_yes", "px": ask, "q": q}
            elif r["s"] < 0 and r["p"] < bid and bk.inv < limit:         # taker sold YES through our bid
                q = min(r["q"], cfg["size"], limit - bk.inv)
                bk.fill(1, bid, q, cfg["fee_rate"]); fill = {"side": "buy_yes", "px": bid, "q": q}
        a = cfg["alpha"]
        self.mid = r["p"] if self.mid is None else (1 - a) * self.mid + a * r["p"]
        self.vpin.push(r["q"], r["s"])
        return fill

    def settle(self, R):
        bk = self.bk
        return {"pnl": round(bk.cash + bk.inv * R, 4), "fees": round(bk.fees, 4), "fills": bk.fills,
                "contracts": round(bk.contracts, 2), "final_inv": bk.inv}


def run_market(m, model, cfg, gm, vpin, log=None):
    """Replay one market. `vpin` is the series-level VPIN carried across markets (updated here)."""
    qt = Quoter(m["close_ts"], model, cfg, gm, vpin)
    markout = 0.0
    for r in m["trades"]:
        before = qt.quote
        qt.requote(r["ts"])
        if log is not None and qt.quote is not before and qt.mid is not None:
            v = vpin.value
            log.append([round(r["ts"] - m["close_ts"]), round(qt.mid, 4), None if v is None else round(v, 4),
                        qt.status, qt.quote and qt.quote[0], qt.quote and qt.quote[1], round(qt.bk.inv),
                        round(qt.bk.cash + qt.bk.inv * qt.mid, 2)])
        f = qt.on_trade(r)
        if f:
            markout += f["q"] * ((f["px"] - m["R"]) if f["side"] == "sell_yes" else (m["R"] - f["px"]))
    out = qt.settle(m["R"])
    return {"ticker": m["ticker"], "pnl": out["pnl"], "fees": out["fees"], "fills": out["fills"],
            "contracts": out["contracts"], "gross_markout": round(markout, 4)}


def run_all(markets, cfg, model, gm, warm, logs=None):
    vpin = VPIN(model["bucket"], model["n"])
    for m in warm:                                    # warm the series VPIN on train tape
        for r in m["trades"]:
            vpin.push(r["q"], r["s"])
    out = []
    for m in markets:
        lg = [] if logs is not None and m["ticker"] in logs else None
        out.append(run_market(m, model, cfg, gm, vpin, lg))
        if lg is not None:
            logs[m["ticker"]] = lg
    return out


def bootstrap(diff, iters=2000, seed=7):
    rnd = random.Random(seed)
    n = len(diff)
    means = sorted(sum(rnd.choice(diff) for _ in range(n)) / n for _ in range(iters))
    return round(means[int(iters * 0.025)], 4), round(means[int(iters * 0.975)], 4)


def summarize(res):
    pn = [r["pnl"] for r in res]
    sd = (sum((x - sum(pn) / len(pn)) ** 2 for x in pn) / max(len(pn) - 1, 1)) ** 0.5
    return {"total_pnl": round(sum(pn), 2), "per_market_mean": round(sum(pn) / len(pn), 4),
            "per_market_sd": round(sd, 4), "win_markets": sum(x > 0 for x in pn), "markets": len(pn),
            "fills": sum(r["fills"] for r in res), "contracts": round(sum(r["contracts"] for r in res)),
            "fees": round(sum(r["fees"] for r in res), 2), "markout": round(sum(r["gross_markout"] for r in res), 2)}


GRID = (1.0, 2.0, 3.0, 5.0, 8.0)


def tune(train, cfg, model, gm, grid=GRID):
    """Pick base half-spread (cents) by train P&L only. Test is never touched here."""
    best = None
    for h in grid:
        res = run_all(train, {**cfg, "base_half_c": h}, model, gm, [])
        pnl = sum(r["pnl"] for r in res)
        if best is None or pnl > best[1]:
            best = (h, pnl)
    return best[0]


def run(markets, cfg=None, frac=0.6, n_trace=3, tune_grid=GRID):
    cfg = {**DEFAULTS, **(cfg or {})}
    train, test = split(markets, frac)
    model = fit(train)
    cfg_g, cfg_a = dict(cfg), dict(cfg)
    if tune_grid:
        cfg_g["base_half_c"] = tune(train, cfg, model, True, tune_grid)
        cfg_a["base_half_c"] = tune(train, cfg, model, False, tune_grid)
    traces = {m["ticker"]: None for m in test[-n_trace:]}
    tg, ta = dict(traces), dict(traces)
    gm = run_all(test, cfg_g, model, True, train, tg)
    asr = run_all(test, cfg_a, model, False, train, ta)
    diff = [g["pnl"] - a["pnl"] for g, a in zip(gm, asr)]
    ci = bootstrap(diff)
    S_g, S_a = summarize(gm), summarize(asr)
    gate3 = ci[0] > 0 and S_g["total_pnl"] > 0
    return {
        "config": {"gm_as": cfg_g, "pure_as": cfg_a}, "model": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in model.items()},
        "markets": {"train": len(train), "test": len(test)},
        "gm_as": S_g, "pure_as": S_a,
        "diff_per_market": {"mean": round(sum(diff) / len(diff), 4), "ci95": ci},
        "gate3": {"pass": gate3, "rule": "GM-AS per-market P&L diff CI95 lower > 0 and GM total P&L > 0 after fees"},
        "per_market": [{"ticker": g["ticker"], "gm": g["pnl"], "as": a["pnl"]} for g, a in zip(gm, asr)],
        "traces": {t: {"gm": tg[t], "as": ta[t]} for t in traces},
    }


def render(series, rep):
    g, a, d, mo = rep["gm_as"], rep["pure_as"], rep["diff_per_market"], rep["model"]
    L = [f"== {series} replay on {rep['markets']['test']} test markets (fit on {rep['markets']['train']})",
         f"train-tuned half-spread: GM {rep['config']['gm_as']['base_half_c']}c, A-S {rep['config']['pure_as']['base_half_c']}c",
         f"model: warn {mo['warn']} halt {mo['halt']} stop_tau {mo['stop_tau']}s adverse_c/quintile {[round(x, 2) for x in mo['adverse_c']]}",
         f"{'':10}{'P&L $':>10}{'fills':>8}{'contracts':>11}{'fees $':>9}{'markout $':>11}{'win mkts':>10}",
         f"{'GM x A-S':10}{g['total_pnl']:>10}{g['fills']:>8}{g['contracts']:>11}{g['fees']:>9}{g['markout']:>11}{g['win_markets']:>6}/{g['markets']}",
         f"{'pure A-S':10}{a['total_pnl']:>10}{a['fills']:>8}{a['contracts']:>11}{a['fees']:>9}{a['markout']:>11}{a['win_markets']:>6}/{a['markets']}",
         f"GM - A-S per market: {d['mean']} $  CI95 {d['ci95']}",
         f"GATE 3: {'PASS' if rep['gate3']['pass'] else 'FAIL'}  ({rep['gate3']['rule']})"]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/gm")
    ap.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    ap.add_argument("--set", nargs="*", default=[], help="override config, e.g. base_half_c=2 size=3")
    a = ap.parse_args(argv)
    cfg = {k: float(v) for k, v in (kv.split("=") for kv in a.set)}
    for s in a.series:
        folder = os.path.join(a.data, s)
        if not os.path.isdir(folder):
            print(f"{s}: no data; run gmdesk.record backfill first", file=sys.stderr)
            continue
        rep = run(load(folder), cfg)
        with open(os.path.join(a.data, f"replay_{s}.json"), "w") as f:
            json.dump(rep, f)
        print(render(s, rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
