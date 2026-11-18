"""Read-only Kalshi desk scan (public GET endpoints only; no keys, no orders, no previews).

    python -m kalshi.desk scan --series KXBTC15M KXETH15M [--out DIR] [--min-edge-cents N] [--offline FIXTURE.json]

For every open market it reads the order book and, from the book alone, computes the YES ask, the
NO ask, the "both sides" lock cost (YES ask + NO ask), its fee-net edge in cents per contract
(100 - cost - taker fees on both legs), spread and top-of-book depth. Rows are ranked by fee-net
edge; a market whose lock is positive after fees is flagged LOCK. Usually none are: say so.

Writes scan.json, kalshi_desk.json (a PAPER-mode board config for scripts/build_board.py) and
appends one summary line per run to paper_log.jsonl. Paper observation only.
"""
import argparse
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

from . import taker_fee_cents
from .feed import _get, open_markets
from .shadow import book_side

MODE = "PAPER"
MAX_REQUESTS = 40
SLEEP_S = 0.3


def analyse(ticker, book, close_time="", min_edge_c=1):
    """One row from one order book (qty 1). Empty or one-sided books get edge None."""
    ya, yd, _ = book_side(book, "yes", 1)
    na, nd, _ = book_side(book, "no", 1)
    row = {"ticker": ticker, "close_time": close_time, "yes_ask": ya, "no_ask": na,
           "cost_c": None, "fees_c": None, "edge_c": None, "spread_c": None,
           "depth": None, "lock": False}
    if ya is None or na is None:
        return row
    cost = ya + na
    fees = taker_fee_cents(ya, 1) + taker_fee_cents(na, 1)
    edge = round(100 - cost - fees, 2)
    row.update(cost_c=round(cost, 2), fees_c=fees, edge_c=edge,
               spread_c=round(ya - (100 - na), 2),      # YES ask minus YES bid (= 100 - NO ask)
               depth=round(min(yd, nd), 2), lock=edge >= max(min_edge_c, 0.01))
    return row


def rank(rows):
    return sorted(rows, key=lambda r: (r["edge_c"] is None, -(r["edge_c"] or 0), r["ticker"]))


def summarise(rows, min_edge_c=1):
    priced = [r for r in rows if r["edge_c"] is not None]
    locks = [r for r in rows if r["lock"]]
    best = max(priced, key=lambda r: r["edge_c"]) if priced else None
    if locks:
        msg = f"{len(locks)} LOCK market(s); best {best['ticker']} at {best['edge_c']:+.2f}c/contract after fees"
    elif priced:
        msg = f"No fee-net edge: best {best['ticker']} at {best['edge_c']:+.2f}c/contract after fees"
    else:
        msg = "No priced markets (empty or one-sided books)"
    return {"markets": len(rows), "priced": len(priced), "locks": len(locks),
            "best_edge_c": best["edge_c"] if best else None, "min_edge_c": min_edge_c, "message": msg}


def scan(series_list, fetch=_get, min_edge_c=1, sleep=0.0):
    rows = []
    for s in series_list:
        for m in open_markets(s, fetch):
            if sleep:
                time.sleep(sleep)
            book = fetch(f"/markets/{m['ticker']}/orderbook", {"depth": 10})
            rows.append(analyse(m["ticker"], book, m.get("close_time", ""), min_edge_c))
    return rank(rows)


def offline_fetch(fixture):
    """fixture: {"markets": {SERIES: [market,...]}, "books": {TICKER: book}}"""
    def fetch(path, params=None):
        if path == "/markets":
            return {"markets": fixture.get("markets", {}).get((params or {}).get("series_ticker"), [])}
        if path.startswith("/markets/") and path.endswith("/orderbook"):
            return fixture.get("books", {}).get(path.split("/")[2], {})
        raise KeyError(path)
    return fetch


def limited(fetch, cap=MAX_REQUESTS):
    n = [0]

    def f(path, params=None):
        n[0] += 1
        if n[0] > cap:
            raise RuntimeError(f"request cap {cap} reached; stopping")
        return fetch(path, params)
    f.count = n
    return f


def board_config(result):
    s, rows = result["summary"], result["rows"]
    fmt = lambda v: "—" if v is None else f"{v:+.2f}¢"
    top = rows[:5]
    seat = lambda i, n, role, color, task, done: {"id": i, "name": n, "role": role, "color": color,
                                                  "status": "idle", "task": task, "done": done,
                                                  "trigger": "On each `python -m kalshi.desk scan` run"}
    return {
        "name": "Kalshi Book Scan (paper)",
        "mission": "Read Kalshi 15-minute order books and report whether buying both sides ever locks a profit after taker fees. Observation only: no orders, no previews.",
        "mode": MODE,
        "session": f"Scan as of {result['as_of']} · series {', '.join(result['series'])}",
        "domain": "kalshi-book-scan",
        "approval_word": "NONE-PAPER-ONLY",
        "coordinator": {
            "name": "Scan Router",
            "brief": ["Every number comes from the public Kalshi order book at scan time; no outside price model.",
                      "Edge = 100 - (YES ask + NO ask) - taker fees on both legs, in cents per contract.",
                      "LOCK means the edge is positive after fees. If none, the honest answer is that there is none.",
                      "Nothing here places, previews or approves an order."],
            "go_line": "Paper observation only. There is no execution path from this board."},
        "tiles": [
            {"label": "Markets scanned", "value": s["markets"], "trend": "flat"},
            {"label": "LOCK markets", "value": s["locks"], "trend": "up" if s["locks"] else "flat"},
            {"label": "Best fee-net edge", "value": fmt(s["best_edge_c"]), "trend": "flat"},
        ],
        "funnel": [{"stage": "Open markets", "count": s["markets"], "seat": "router"},
                   {"stage": "Priced both sides", "count": s["priced"], "seat": "scanner"},
                   {"stage": "LOCK after fees", "count": s["locks"], "seat": "scanner"}],
        "seats": [seat("router", "Scan Router", "router", "green", "Run the scan and publish the summary.", "scan.json written."),
                  seat("scanner", "Book Scanner", "scanner", "blue", "Compute ask, lock cost and fee-net edge per market.", "Rows ranked by fee-net edge.")],
        "queue": [{"id": f"Q{i + 1}", "title": f"{r['ticker']}: edge {fmt(r['edge_c'])}" + (" LOCK" if r["lock"] else ""),
                   "owner": "scanner", "pct": 100} for i, r in enumerate(top)],
        "watch": [{"label": "Series", "value": ", ".join(result["series"])},
                  {"label": "As of (UTC)", "value": result["as_of"]}],
        "feed": [{"t": result["as_of"][11:19], "agent": "router", "msg": s["message"]}],
        "handoffs": [], "gates": [],
    }


def render(result, n=5):
    lines = [result["summary"]["message"],
             f"{'ticker':<30} {'yesA':>6} {'noA':>6} {'cost':>6} {'fees':>4} {'edge':>7} {'sprd':>5} {'depth':>7}  flag"]
    f = lambda v, w, p=1: f"{'—':>{w}}" if v is None else f"{v:>{w}.{p}f}"
    for r in result["rows"][:n]:
        lines.append(f"{r['ticker']:<30} {f(r['yes_ask'], 6)} {f(r['no_ask'], 6)} {f(r['cost_c'], 6)} "
                     f"{'—' if r['fees_c'] is None else r['fees_c']:>4} {f(r['edge_c'], 7, 2)} {f(r['spread_c'], 5)} {f(r['depth'], 7, 0)}  "
                     f"{'LOCK' if r['lock'] else ''}")
    return "\n".join(lines)


def run(series, out, min_edge_c=1, offline=None):
    if offline:
        fetch, sleep = offline_fetch(json.loads(pathlib.Path(offline).read_text(encoding="utf-8"))), 0.0
    else:
        fetch, sleep = limited(_get), SLEEP_S
    rows = scan(series, fetch, min_edge_c, sleep)
    result = {"as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "series": list(series),
              "mode": MODE, "rows": rows, "summary": summarise(rows, min_edge_c)}
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scan.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out / "kalshi_desk.json").write_text(json.dumps(board_config(result), indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out / "paper_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"as_of": result["as_of"], "series": result["series"], "mode": MODE, **result["summary"]}) + "\n")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kalshi.desk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("scan")
    sp.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    sp.add_argument("--out", default="./kalshi-desk-out")
    sp.add_argument("--min-edge-cents", type=float, default=1)
    sp.add_argument("--offline")
    a = ap.parse_args(argv)
    try:
        result = run(a.series, a.out, a.min_edge_cents, a.offline)
    except OSError as e:
        print(f"Kalshi unreachable: {e}. Allow api.elections.kalshi.com in the network policy.", file=sys.stderr)
        return 2
    print(render(result))
    print(f"wrote {pathlib.Path(a.out)}/scan.json, kalshi_desk.json, paper_log.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
