"""Forward paper test: log each scan's signals before the next open, then score them as bars arrive.

Every backtest can be overfit after the fact; a signal written down before the market opens cannot.
`record` appends one JSON line per scan to ledger/signals.jsonl (one line per as-of date, so re-running
a scan the same day is a no-op). `report` scores every logged long signal against later bars: the
return from the next open to the close `h` sessions later, next to simply holding the symbol.
"""
import json
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
