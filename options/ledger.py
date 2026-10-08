"""Signal ledger: the only valid record of whether the heatseeker model works.

Historical GEX maps cannot be rebuilt, so this forward log - taken trades AND
gate-blocked no-trades - is the evidence base. JSONL rows in data/ledger.jsonl;
the weekly report (options/report.py) renders the markdown view.

Row schema (superset of the skill's ledger-template.md columns):
  ts, ticker, setup, tier, regime, vanna, map_src, map_asof, level,
  rvol, signal_price, bid, ask, entry, stop, target, qty_hint,
  outcome (null until resolved), r (null until resolved), source, note

Sources that append: the TV webhook bridge (parse_webhook) and the desk's
board refresh (from_snapshot). This module logs; it never places orders.
"""
import json
import pathlib
from datetime import datetime, timezone

from fund.config import ROOT

LEDGER = ROOT / "data" / "ledger.jsonl"

OUTCOMES = ("target", "stop", "time-stop", "scratch", "no-trade", "no-fill", "open")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def append(row, path=LEDGER):
    """Append one ledger row. Required: ticker, setup, source."""
    for req in ("ticker", "setup", "source"):
        if not row.get(req):
            raise ValueError(f"ledger row missing '{req}'")
    row = {**row}
    row.setdefault("ts", _now_iso())
    row.setdefault("outcome", None)
    row.setdefault("r", None)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def rows(path=LEDGER):
    """All ledger rows, oldest first. Skips corrupt lines (with a count)."""
    path = pathlib.Path(path)
    out, bad = [], 0
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    if bad:
        out.append({"ticker": "LEDGER", "setup": "corrupt_lines", "source": "ledger",
                    "ts": _now_iso(), "note": f"{bad} corrupt line(s) skipped",
                    "outcome": None, "r": None})
    return out


def open_rows(path=LEDGER):
    return [r for r in rows(path) if r.get("outcome") is None and r.get("source") != "ledger"]


def parse_webhook(line):
    """HEATSEEKER|TICKER|SETUP|TIER|CLOSE|k=v... -> ledger row or None.

    Same format the Pine emits on confirmed bars. Gate-blocked lines never
    reach the webhook, but the Pine's NO TRADE log lines use the same shape
    with tier 'NO'.
    """
    parts = [p.strip() for p in line.strip().split("|")]
    if not parts or parts[0].upper() != "HEATSEEKER" or len(parts) < 5:
        return None
    rec = {
        "source": "tv-webhook",
        "ticker": parts[1].upper(),
        "setup": parts[2].upper(),
        "tier": parts[3],
        "signal_price": float(parts[4]),
    }
    for kv in parts[5:]:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        k = k.strip().lower()
        if k in ("stop", "target"):
            try:
                rec[k] = float(v)
            except ValueError:
                rec[k] = v
        elif k in ("rvol",):
            try:
                rec[k] = float(v)
            except ValueError:
                rec[k] = v
        elif k in ("regime", "vanna"):
            rec[k] = v
    return rec


def from_snapshot(snap, symbol, state_names=("ARMED",), path=LEDGER):
    """Append board-derived setup rows from a gex_snapshot symbol block.

    Only states in state_names are logged; WATCH/OFF are noise at this stage.
    Bid/ask come from the board's delayed snapshot and are labeled so.
    """
    s = snap["symbols"].get(symbol) or snap["symbols"].get(symbol.upper())
    if not s:
        return None
    recs = []
    for st in s.get("setups") or []:
        if st["state"] not in state_names:
            continue
        rec = {
            "source": "gex-board",
            "ticker": symbol.upper(),
            "setup": st["setup"],
            "tier": "B",  # board states are structure-only; doctrine needs live gates
            "regime": s.get("regime"),
            "map_asof": snap.get("captured_at"),
            "signal_price": s.get("spot"),
            "bid": s.get("spot"),
            "ask": s.get("spot"),
            "note": st["reason"] + " | bid/ask = delayed snapshot spot (no live chain)",
        }
        recs.append(append(rec, path))
    return recs


def mark_resolved(row_index, outcome, r=None, note="", path=LEDGER):
    """Rewrite row at index with outcome/r. Caller rewrites the whole file."""
    all_rows = rows(path)
    if row_index < 0 or row_index >= len(all_rows):
        raise IndexError("row index out of range")
    all_rows[row_index]["outcome"] = outcome
    all_rows[row_index]["r"] = r
    if note:
        all_rows[row_index]["resolve_note"] = note
    p = pathlib.Path(path)
    p.write_text("\n".join(json.dumps(x) for x in all_rows) + "\n", encoding="utf-8")
    return all_rows[row_index]