"""Forward paper test: log each scan's signals before the next open, then score them as bars arrive.

Every backtest can be overfit after the fact; a signal written down before the market opens cannot.
`record` appends one JSON line per scan to ledger/signals.jsonl (one line per as-of date, so re-running
a scan the same day is a no-op). `report` scores every logged long signal against later bars: the
return from the next open to the close `h` sessions later, next to simply holding the symbol.
"""
import json
import math
import pathlib
from datetime import datetime, timezone

from . import load_csv
from .scan import symbol_for

LOG = pathlib.Path(__file__).resolve().parent.parent / "ledger" / "signals.jsonl"
HORIZONS = (1, 5, 10)


def _held(e):
    """The symbol an entry says to be long, or None."""
    if e["strategy"] == "momentum_rotation":
        tgt = e["signal"].removeprefix("hold ")
        return None if tgt in ("CASH", "None") else tgt
    return e["symbol"] if e["signal"] == "long" else None


def record(result, path=LOG, now=None):
    entries = result["signal_list"]
    if not entries:
        return None
    as_of = max(e["as_of"] for e in entries)
    path = pathlib.Path(path)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and json.loads(line)["as_of"] == as_of:
                return None
    row = {
        "recorded_at": (now or datetime.now(timezone.utc)).isoformat(),
        "as_of": as_of,
        "entries": [{"symbol": e["symbol"], "strategy": e["strategy"], "params": e["params"],
                     "long": _held(e), "candidate": e["candidate"]} for e in entries],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def report(path=LOG, folder="chart/data", universe=None, horizons=HORIZONS):
    bars = {}
    for p in pathlib.Path(folder).glob("*.csv"):
        sym = symbol_for(p, universe) if universe else p.stem.upper()
        if sym:
            bars[sym] = load_csv(p)
    rows = [json.loads(l) for l in pathlib.Path(path).read_text().splitlines() if l.strip()] if pathlib.Path(path).exists() else []
    stats, pending = {}, 0
    for row in rows:
        for e in row["entries"]:
            sym = e["long"]
            if not sym or sym not in bars:
                continue
            series = bars[sym]
            i = next((k for k, b in enumerate(series) if b.ts > row["as_of"]), None)
            if i is None:
                pending += 1
                continue
            key = e["strategy"] + (" (candidate)" if e["candidate"] else "")
            s = stats.setdefault(key, {h: [] for h in horizons})
            for h in horizons:
                j = i + h - 1
                if j < len(series):
                    s[h].append(series[j].close / series[i].open - 1)
    out = {}
    for key, s in sorted(stats.items()):
        out[key] = {f"{h}d": {"n": len(v), "mean": round(sum(v) / len(v), 5) if v else None,
                              "hit_rate": round(sum(x > 0 for x in v) / len(v), 3) if v else None}
                    for h, v in s.items()}
    return {"scans_logged": len(rows), "signals_waiting_for_next_bar": pending, "by_strategy": out}


# --- Rotation rule forward test --------------------------------------------------------------------------------------
# The stress-tested rule (chart/robust.py): rank the basket by 60-session return, hold the top 3 with positive momentum
# in equal weight, rebalance monthly. Live, the rebalance day must be recognisable on the evening itself, so the rule
# decides at the close of the FIRST session of each month (the previous session was in another month) and fills at the
# next open. Each decision is logged once; it is scored from that next open to the next decision's fill, vs the basket.

ROTATION_LOG = LOG.with_name("rotation.jsonl")
ROTATION_RULE = {"lookback": 60, "top": 3}


def rotation_signal(bars_by_symbol, lookback=60, top=3):
    """The rule's decision for the latest session, or None when that session is not a decision day."""
    from . import rotate
    syms, dates, bars = rotate.align(bars_by_symbol)
    i = len(dates) - 1
    if i < lookback or dates[i][:7] == dates[i - 1][:7]:
        return None
    mom = {s: bars[s][i].close / bars[s][i - lookback].close - 1 for s in syms}
    ranked = sorted(syms, key=lambda s: (mom[s], s), reverse=True)
    picks = sorted(s for s in ranked[:top] if mom[s] > 0)
    return {"as_of": dates[i], "rule": {"lookback": lookback, "top": top}, "picks": picks,
            "momentum": {s: round(mom[s], 4) for s in ranked}, "basket": syms}


def record_rotation(bars_by_symbol, path=ROTATION_LOG, now=None, **rule):
    sig = rotation_signal(bars_by_symbol, **{**ROTATION_RULE, **rule})
    if sig is None:
        return None
    path = pathlib.Path(path)
    if path.exists() and any(json.loads(l)["as_of"] == sig["as_of"] for l in path.read_text().splitlines() if l.strip()):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"recorded_at": (now or datetime.now(timezone.utc)).isoformat(), **sig}) + "\n")
    return sig


def _basket_return(bars_by_symbol, syms, start, end):
    """Equal-weight return of `syms` bought at the open of date `start`, marked at the close of date `end`."""
    if not syms:
        return 0.0
    rets = []
    for s in syms:
        by_date = {b.ts: b for b in bars_by_symbol[s]}
        rets.append(by_date[end].close / by_date[start].open - 1)
    return sum(rets) / len(rets)


def report_rotation(bars_by_symbol, path=ROTATION_LOG):
    """Score each logged decision from its next open to the session before the next decision's fill (or the latest bar)."""
    from . import rotate
    _, dates, _ = rotate.align(bars_by_symbol)
    rows = [json.loads(l) for l in pathlib.Path(path).read_text().splitlines() if l.strip()] if pathlib.Path(path).exists() else []
    periods, pending = [], []
    for k, r in enumerate(rows):
        later = [d for d in dates if d > r["as_of"]]
        if not later:
            pending.append(r["as_of"])
            continue
        start = later[0]
        nxt = rows[k + 1]["as_of"] if k + 1 < len(rows) else None
        fill = next((d for d in dates if d > nxt), None) if nxt else None
        end = max(d for d in dates if d < fill) if fill else dates[-1]
        rule = _basket_return(bars_by_symbol, r["picks"], start, end)
        hold = _basket_return(bars_by_symbol, r["basket"], start, end)
        periods.append({"decided": r["as_of"], "from": start, "to": end, "picks": r["picks"], "complete": fill is not None,
                        "rule": round(rule, 5), "basket": round(hold, 5), "excess": round(rule - hold, 5)})
    done = [p for p in periods if p["complete"]]
    growth = lambda key: round(math.prod(1 + p[key] for p in periods) - 1, 5) if periods else 0.0
    return {"decisions_logged": len(rows), "waiting_for_first_fill": pending, "periods": periods,
            "completed_periods": len(done), "months_beat_basket": sum(p["excess"] > 0 for p in done),
            "cumulative": {"rule": growth("rule"), "basket": growth("basket")}}


def replay_rotation(bars_by_symbol, since=None, **rule):
    """Backfill what the live rotation log would have recorded, deciding each day from bars up to that day only,
    then score it exactly as `report_rotation` scores the live log. Clearly a backtest, kept apart from the live log."""
    import tempfile
    from . import rotate
    _, dates, _ = rotate.align(bars_by_symbol)
    log = pathlib.Path(tempfile.mkdtemp()) / "replay.jsonl"
    for d in dates:
        if since and d < since:
            continue
        cut = {s: [b for b in bars if b.ts <= d] for s, bars in bars_by_symbol.items()}
        record_rotation(cut, log, **rule)
    out = report_rotation(bars_by_symbol, log)
    out["note"] = "Replay over history (a backtest), not live forward results."
    return out
