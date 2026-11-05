"""Score a forward journal of intraday signals (Heat Seeker and similar) against real 15-minute bars.

Historical dealer-positioning (GEX) maps can't be rebuilt after the fact, so these setups can only be judged going forward.
Each signal is logged before it can trigger, with an observable trigger, a stop and a target on the underlying. This module
replays the day's regular-hours bars and says what happened.

Journal: JSON Lines, one signal per line:
    {"id": "2026-11-02-SPY-1", "date": "2026-11-02", "logged_at": "2026-11-02T09:50:00-05:00", "ticker": "SPY",
     "setup": "gap fill", "side": "short", "tier": "B", "regime": "+GEX",
     "trigger": {"kind": "reject_below", "level": 761.0, "after": "09:45", "before": "14:00", "rvol_min": 1.4},
     "stop": {"level": 761.0, "basis": "close"}, "target": 757.67,
     "levels": {"flip": 755.62, "king": 759, "call_wall": 761, "put_wall": 757}, "contract": "...", "bid": 1.55, "ask": 1.57}
A logged no-trade has "side": "none" and a "gate" naming what failed; it is kept but never scored as a trade.

Trigger kinds, judged on a bar's close (a bar counts only if it opens at or after `after` and closes by `before`):
    close_above / close_below   the bar closes above / below `level`
    reject_below                the bar trades at or above `level` and closes below it (a failed push up: short)
    reject_above                the bar trades at or below `level` and closes above it (a failed push down: long)
The trade fills at the next bar's open. Stop basis "close": out at the first bar that closes beyond the stop, at that close.
Stop basis "touch": out at the stop when a bar trades through it (at the open if it gaps through). A target is a touch.
If the stop and the target are both reached in one bar, the stop counts. Anything still open exits at the last bar's close.
Before the session's bars are complete, an untriggered signal is "in progress" and an unresolved trade is "open".
`rvol_min`: cumulative volume up to the trigger bar ÷ the average for the same time of day over the prior 10 sessions.
"""
import datetime as dt
import json

KINDS = ("close_above", "close_below", "reject_below", "reject_above")
FIRST_ENTRY, DEFAULT_BEFORE, SESSION_CLOSE = "09:45", "14:00", "16:00"   # trigger window defaults; RTH close


def _hm(ts):
    return ts[11:16]


def _end_hm(bar, ivl):
    t = dt.datetime.fromisoformat(bar.ts) + dt.timedelta(minutes=ivl)
    return t.strftime("%H:%M")


def rvol_at(sessions, date, idx, lookback=10):
    """Cumulative volume through bar `idx` on `date`, relative to the same bar count on the prior `lookback` sessions."""
    days = [d for d, _ in sessions]
    if date not in days:
        return None
    k = days.index(date)
    today = sum(b.volume for b in sessions[k][1][:idx + 1])
    prior = [sum(b.volume for b in bars[:idx + 1]) for _, bars in sessions[max(0, k - lookback):k] if len(bars) > idx]
    if len(prior) < lookback or not sum(prior):
        return None
    return today / (sum(prior) / len(prior))


def _triggered(kind, bar, level):
    if kind == "close_above":
        return bar.close > level
    if kind == "close_below":
        return bar.close < level
    if kind == "reject_below":
        return bar.high >= level and bar.close < level
    if kind == "reject_above":
        return bar.low <= level and bar.close > level
    raise ValueError(f"unknown trigger kind {kind!r}")


def first_trigger(trig, bars, sessions, date, ivl):
    """First bar in `bars` (a prefix of `date`'s session) inside the trigger window that meets the trigger and its RVOL
    gate. Returns (index or None, rvol at the last bar that met the trigger, index of that bar); None where none did."""
    after, before, last_rv, fired = trig.get("after", FIRST_ENTRY), trig.get("before", DEFAULT_BEFORE), None, None
    for i, b in enumerate(bars):
        if _hm(b.ts) < after or _end_hm(b, ivl) > before or not _triggered(trig["kind"], b, trig["level"]):
            continue
        last_rv, fired = rvol_at(sessions, date, i), i
        if not trig.get("rvol_min") or (last_rv is not None and last_rv >= trig["rvol_min"]):
            return i, last_rv, i
    return None, last_rv, fired         # any trigger that fired was on thin volume: the gate says wait for the next one


def _blank(signal):
    out = {"id": signal["id"], "date": signal["date"], "ticker": signal["ticker"], "setup": signal.get("setup", ""),
           "side": signal.get("side", "none"), "tier": signal.get("tier", ""), "status": "", "trigger_time": "",
           "entry": None, "exit": None, "exit_time": "", "r": None, "mfe_r": None, "mae_r": None, "rvol": None,
           "regime": signal.get("regime", ""), "trigger": "", "stop_level": None, "target": signal.get("target"),
           "gate": signal.get("gate", "")}
    if signal.get("trigger"):
        out["trigger"] = f"{signal['trigger']['kind'].replace('_', ' ')} {signal['trigger']['level']:g}"
    if signal.get("stop"):
        out["stop_level"] = signal["stop"]["level"]
    return out


def score(signal, sessions, ivl=15):
    """One signal → result dict. `sessions` is chart.intraday.sessions(...) output for that ticker."""
    out = _blank(signal)
    if out["side"] not in ("long", "short"):
        out["status"] = "no trade"
        return out
    day = dict(sessions).get(signal["date"])
    if not day:
        out["status"] = "no data"
        return out
    # A session is complete once its last bar ends at the close, or a later session exists (half days).
    complete = _end_hm(day[-1], ivl) >= SESSION_CLOSE or sessions[-1][0] > signal["date"]
    sign = 1 if out["side"] == "long" else -1
    stop, basis, target = signal["stop"]["level"], signal["stop"].get("basis", "touch"), signal.get("target")
    i, out["rvol"], _ = first_trigger(signal["trigger"], day[:-1], sessions, signal["date"], ivl)   # entry needs a next bar
    if i is not None:
        out["trigger_time"] = _end_hm(day[i], ivl)
        entry = day[i + 1].open
        risk = abs(entry - stop)
        if risk == 0 or (sign > 0 and entry <= stop) or (sign < 0 and entry >= stop):
            out["status"] = "invalid at entry"
            return out
        out["entry"] = entry
        best = worst = 0.0
        for j in range(i + 1, len(day)):
            x = day[j]
            first = j == i + 1                 # the entry bar opens at the entry price, so it can't gap through a level
            worst = max(worst, (entry - x.low) if sign > 0 else (x.high - entry))
            if basis == "touch":
                hit_stop = (x.low <= stop) if sign > 0 else (x.high >= stop)
                stop_px = stop if first else (min if sign > 0 else max)(x.open, stop)
            else:
                hit_stop = (x.close < stop) if sign > 0 else (x.close > stop)
                stop_px = x.close
            if hit_stop:
                best = max(best, (x.high - entry) if sign > 0 else (entry - x.low))
                return _close(out, "stop", stop_px, x, ivl, entry, sign, risk, best, worst)
            if target is not None and ((x.high >= target) if sign > 0 else (x.low <= target)):
                tgt_px = target if first else (max if sign > 0 else min)(x.open, target)
                best = max(best, (tgt_px - entry) * sign)
                return _close(out, "target", tgt_px, x, ivl, entry, sign, risk, best, worst)
            best = max(best, (x.high - entry) if sign > 0 else (entry - x.low))
        res = _close(out, "close", day[-1].close, day[-1], ivl, entry, sign, risk, best, worst)
        if not complete:
            res["status"] = "open"
        return res
    out["status"] = "not triggered" if complete else "in progress"
    return out


def _close(out, status, px, bar, ivl, entry, sign, risk, best, worst):
    out.update(status=status, exit=px, exit_time=_end_hm(bar, ivl), r=sign * (px - entry) / risk,
               mfe_r=best / risk, mae_r=-worst / risk)
    return out


def load_journal(path):
    rows = []
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            for k in ("id", "date", "ticker"):
                if k not in s:
                    raise ValueError(f"line {n}: missing {k}")
            if s.get("side") in ("long", "short") and s["trigger"]["kind"] not in KINDS:
                raise ValueError(f"line {n}: trigger kind must be one of {KINDS}")
            rows.append(s)
    return rows


def score_journal(journal_path, bars_folder):
    """Score every signal whose ticker has a bars file in `bars_folder` (e.g. chart/data/intraday/15m)."""
    import pathlib
    from . import load_csv
    from .intraday import interval_minutes, sessions as to_sessions
    cache, results = {}, []
    for s in load_journal(journal_path):
        t = s["ticker"]
        if t not in cache:
            p = pathlib.Path(bars_folder) / f"{t}.csv"
            cache[t] = to_sessions(load_csv(p)) if p.exists() else []
        sess = cache[t]
        results.append(score(s, sess, interval_minutes(sess)) if sess else {**_blank(s), "status": "no data"})
    return results


def summary(results):
    trades = [r for r in results if r["r"] is not None]
    rs = [r["r"] for r in trades]
    return {
        "signals": len(results),
        "no_trade": sum(r["status"] == "no trade" for r in results),
        "not_triggered": sum(r["status"] == "not triggered" for r in results),
        "trades": len(trades),
        "wins": sum(x > 0 for x in rs),
        "total_r": sum(rs),
        "avg_r": sum(rs) / len(rs) if rs else None,
        "pending": sum(r["status"] == "no data" for r in results),
    }
