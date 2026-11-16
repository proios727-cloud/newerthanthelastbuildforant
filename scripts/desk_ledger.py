"""Build the desk's running trade journal: every triggered trade across all books, with realized and open P&L.

    python3 scripts/desk_ledger.py [--today YYYY-MM-DD]

Reads only the append-only journals (nothing is edited):
- research/paper/positions.jsonl: premium-screener paper puts, other paper positions, and the owner's real fills
  (source "my actual fill");
- research/swing-buyer/picks.jsonl: swing-buyer paper calls;
- research/heatseeker/signals.jsonl, scored against chart/data/intraday/15m: Heat Seeker signals (in R, no dollars).
Open option positions are marked from the newest chain snapshot of their own ticker and expiry (bid for longs, ask for
shorts); a position with no snapshot is left unmarked.
Writes research/desk-ledger.md (the readable journal) and research/desk_ledger.csv (one row per trade).
"""
import argparse
import csv
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chart import read_jsonl  # noqa: E402
from chart.signals import score_journal, summary  # noqa: E402
from options import chain_index  # noqa: E402

POSITIONS = ROOT / "research/paper/positions.jsonl"
SWING = ROOT / "research/swing-buyer/picks.jsonl"
SIGNALS = ROOT / "research/heatseeker/signals.jsonl"
BARS = ROOT / "chart/data/intraday/15m"
CHAIN_DIRS = [ROOT / "options/data/chains_swing", ROOT / "options/data/chains_premium", ROOT / "options/data/chains"]
FIELDS = ["book", "id", "opened", "closed", "ticker", "contract", "side", "entry", "exit", "mark", "status", "pnl",
          "reason"]


def book_of(p):
    src = p.get("source", "")
    if src == "my actual fill":
        return "Real account"
    if "screener" in src:
        return "Paper: premium screener"
    return "Paper: other"


def load_marks():
    idx = {}
    for d in CHAIN_DIRS:
        if not d.exists():
            continue
        try:
            found = chain_index(d)
        except KeyError:  # older snapshots in this folder lack per-contract expiries
            continue
        if found:
            for k, v in found.items():
                if k not in idx or (v[1].get("asof") or "") > (idx[k][1].get("asof") or ""):
                    idx[k] = v
    return idx


def mark(idx, ticker, expiry, strike, kind, side):
    hit = idx.get((ticker, expiry))
    if not hit:
        return None
    for c in hit[1].get("contracts", []):
        if c["type"] == kind and abs(c["strike"] - float(strike)) < 1e-6:
            return c.get("ask") if side == "short" else c.get("bid")
    return None


def rows(today):
    idx = load_marks()
    out = []
    pos = read_jsonl(POSITIONS)
    closes = {r["id"]: r for r in pos if r.get("event") == "close"}
    for p in (r for r in pos if r.get("event") == "open"):
        c, sign, qty = closes.get(p["id"]), (1 if p["side"] == "long" else -1), p.get("qty", 1)
        row = {"book": book_of(p), "id": p["id"], "opened": p["date"], "ticker": p["ticker"],
               "contract": p["contract"], "side": p["side"], "entry": p["entry"]}
        if c:
            row.update(closed=c["date"], exit=c["exit"], status="closed", pnl=c["pnl"], reason=c.get("reason", ""))
        else:
            m = mark(idx, p["ticker"], p["expiry"], p["strike"], p["type"], p["side"])
            row.update(status="open", mark=m,
                       pnl=round(sign * (m - p["entry"]) * 100 * qty, 2) if m is not None else None,
                       reason="" if m is not None else "no quote snapshot")
        out.append(row)
    sw = read_jsonl(SWING) if SWING.exists() else []
    sclose = {r["close_of"]: r for r in sw if r.get("close_of")}
    for p in (r for r in sw if not r.get("close_of")):
        c = sclose.get(p["id"])
        row = {"book": "Paper: swing buyer", "id": p["id"], "opened": p["date"], "ticker": p["ticker"],
               "contract": f"{p['ticker']} {p['expiry']} {p['strike']:g} call", "side": "long", "entry": p["ask"]}
        if c:
            row.update(closed=c["date"], exit=c["exit"], status="closed", pnl=c["pnl"], reason=c.get("reason", ""))
        else:
            m = mark(idx, p["ticker"], p["expiry"], p["strike"], "call", "long")
            row.update(status="open", mark=m, pnl=round((m - p["ask"]) * 100, 2) if m is not None else None,
                       reason="" if m is not None else "no quote snapshot")
        out.append(row)
    return sorted(out, key=lambda r: (r["opened"], r["id"]))


def money(x):
    return "—" if x is None or x == "" else f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    trades = rows(a.today)
    hs = score_journal(SIGNALS, BARS)
    hsum = summary(hs)
    with open(ROOT / "research/desk_ledger.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in trades:
            w.writerow({k: ("" if r.get(k) is None else r.get(k, "")) for k in FIELDS})
    books = sorted({r["book"] for r in trades}, key=lambda b: (b != "Real account", b))
    L = [f"# Desk ledger — running journal", "",
         f"As of {a.today}. Rebuilt from the append-only journals after each close; never edited by hand.", "",
         "## Net by book", "", "| Book | Trades | Closed | Wins / losses | Realized | Open (marked) | Net |",
         "|---|---|---|---|---|---|---|"]
    tot_r = tot_u = 0
    for b in books:
        bt = [r for r in trades if r["book"] == b]
        cl = [r for r in bt if r["status"] == "closed"]
        realized = sum(r["pnl"] for r in cl)
        unreal = sum(r["pnl"] for r in bt if r["status"] == "open" and r["pnl"] is not None)
        tot_r += realized
        tot_u += unreal
        wins = sum(r["pnl"] > 0 for r in cl)
        L.append(f"| {b} | {len(bt)} | {len(cl)} | {wins} / {len(cl) - wins} | {money(realized)} | {money(unreal)} | "
                 f"{money(realized + unreal)} |")
    L.append(f"| **All books** | {len(trades)} | | | **{money(tot_r)}** | **{money(tot_u)}** | "
             f"**{money(tot_r + tot_u)}** |")
    L += ["", f"Heat Seeker (scored in R, no dollars): {hsum['signals']} signals logged, {hsum['no_trade']} no-trade, "
          f"{hsum['not_triggered']} not triggered, **{hsum['trades']} triggered**, total {hsum['total_r']:+.2f} R.", "",
          "## Every trade", "", "| Opened | Book | Contract | Side | Entry | Exit / mark | Status | P&L | Note |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in trades:
        px = r.get("exit") if r["status"] == "closed" else r.get("mark")
        st = f"closed {r['closed']}" if r["status"] == "closed" else "open"
        L.append(f"| {r['opened']} | {r['book']} | {r['contract']} | {r['side']} | {r['entry']:.2f} | "
                 f"{'—' if px is None else f'{px:.2f}'} | {st} | {money(r['pnl'])} | {r.get('reason', '')} |")
    trig = [s for s in hs if s.get("r") is not None]
    if trig:
        L += ["", "## Heat Seeker triggered trades", "", "| Signal | Side | Entry | Exit | R |", "|---|---|---|---|---|"]
        L += [f"| {s['id']} | {s['side']} | {s['entry']} | {s['exit']} | {s['r']:+.2f} |" for s in trig]
    (ROOT / "research/desk-ledger.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:12 + len(books)]))


if __name__ == "__main__":
    main()
