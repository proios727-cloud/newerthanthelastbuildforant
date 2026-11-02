"""Mark open premium-screener picks to market and apply the exit rules (research/premium-screener/RULE.md).

    python3 scripts/premium_mark.py --chains DIR [--today YYYY-MM-DD] [--write]

For each open pick in research/premium-screener/picks.jsonl, it finds the latest chain file for its ticker with the same
expiry and prices the close at the natural debit: buy back each short leg at the ask, sell each long leg at the bid.
- debit <= 50% of credit  -> "take profit"
- debit >= 2x credit      -> "stop"
- days to expiry <= 21    -> "time exit"
With --write, a pick that hit a rule is closed by appending a close record (the journal is never edited in place):
{"close_of": <id>, "date", "debit", "pnl" (credit - debit, per share), "pnl_r" (pnl / max_loss), "rule"}.
Marks without a rule hit go to research/premium-screener/marks.jsonl for the dashboard.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PICKS = ROOT / "research/premium-screener/picks.jsonl"
MARKS = ROOT / "research/premium-screener/marks.jsonl"
LEG = re.compile(r"([PC]) -([\d.]+) \+([\d.]+)")


def legs(text):
    """'P -95 +92.5 (Δ0.22) / C -105 +107.5 (Δ0.21)' -> [("put", 95.0, 92.5), ("call", 105.0, 107.5)]"""
    return [("put" if k == "P" else "call", float(s), float(l)) for k, s, l in LEG.findall(text)]


def debit(pick, chain):
    """Natural cost to close the pick from a chain snapshot, or None if a leg is missing a quote."""
    q = {(c["type"], float(c["strike"])): c for c in chain["contracts"] if c["expiry"] == pick["expiry"]}
    total = 0.0
    for kind, short, long in legs(pick["legs"]):
        s, lg = q.get((kind, short)), q.get((kind, long))
        if not s or not lg or s.get("ask") is None or lg.get("bid") is None:
            return None
        total += s["ask"] - lg["bid"]
    return round(total, 2)


def decide(pick, cost, today):
    if cost is None:
        return None
    dte = (dt.date.fromisoformat(pick["expiry"]) - dt.date.fromisoformat(today)).days
    if cost <= 0.5 * pick["credit"]:
        return "take profit"
    if cost >= 2 * pick["credit"]:
        return "stop"
    if dte <= 21:
        return "time exit"
    return ""


def open_picks():
    if not PICKS.exists():
        return []
    rows = [json.loads(x) for x in PICKS.read_text().splitlines() if x.strip()]
    closed = {r["close_of"] for r in rows if "close_of" in r}
    return [r for r in rows if "close_of" not in r and r["id"] not in closed]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--chains", required=True)
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    chains = {}
    for p in sorted(pathlib.Path(a.chains).glob("*.json")):
        c = json.loads(p.read_text())
        chains[c["symbol"]] = c
    for pick in open_picks():
        chain = chains.get(pick["ticker"])
        cost = debit(pick, chain) if chain else None
        rule = decide(pick, cost, a.today)
        pnl = None if cost is None else round(pick["credit"] - cost, 2)
        rec = {"date": a.today, "id": pick["id"], "debit": cost, "pnl": pnl,
               "pnl_r": None if pnl is None else round(pnl / pick["max_loss"], 3), "rule": rule}
        print(json.dumps(rec))
        if a.write and cost is not None:
            target = PICKS if rule else MARKS
            if rule:
                rec = {"close_of": pick["id"], **{k: v for k, v in rec.items() if k != "id"}}
            with open(target, "a") as f:
                f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
