"""Read-only Kalshi market feed + shadow scanner (public endpoints, no API key, never places orders).

    python -m kalshi.feed --series KXBTC15M KXETH15M          # print one scan
    python -m kalshi.feed --series KXBTC15M --log shadow.jsonl # also append to a shadow log

For every open market it reads the top of book, proposes the maker pair the desk would rest
(one tick inside the best YES and NO bids, only if the pair still locks ≥ edge), and records
whether settlement rules are verified. Nothing is sent to Kalshi except GET requests.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from . import Quote

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _get(path, params=None, timeout=10):
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _cents(m, key):
    """Kalshi returns integer cents (`yes_bid`) or dollar strings (`yes_bid_dollars`); normalise to cents."""
    if m.get(key) is not None:
        return int(m[key])
    d = m.get(f"{key}_dollars")
    return None if d in (None, "") else int(round(float(d) * 100))


def open_markets(series, fetch=_get):
    out, cursor = [], None
    while True:
        params = {"series_ticker": series, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        body = fetch("/markets", params)
        out.extend(body.get("markets", []))
        cursor = body.get("cursor")
        if not cursor:
            return out


@dataclass(frozen=True)
class Row:
    ticker: str
    close_time: str
    yes_bid: int
    no_bid: int
    book_lock_c: int          # 100 − best yes bid − best no bid (what joining the bids would lock)
    proposal: object          # Quote one tick inside, or None when that pair no longer locks ≥ edge
    settlement_ok: bool


def propose(yes_bid, no_bid, edge_c=2):
    """Improve each side by 1¢ while the pair still locks ≥ edge; else join; else nothing."""
    for y, n in ((yes_bid + 1, no_bid + 1), (yes_bid + 1, no_bid), (yes_bid, no_bid)):
        if 1 <= y <= 98 and 1 <= n <= 98 and 100 - y - n >= edge_c:
            return Quote(y, n)
    return None


def scan(series_list, fetch=_get, verify=None, edge_c=2):
    """`verify(market) -> bool` gates quoting (kalshi.settlement.verify); default: nothing is verified."""
    rows = []
    for s in series_list:
        for m in open_markets(s, fetch):
            yb, nb = _cents(m, "yes_bid"), _cents(m, "no_bid")
            if not yb or not nb:
                continue
            ok = bool(verify(m)) if verify else False
            rows.append(Row(m["ticker"], m.get("close_time", ""), yb, nb, 100 - yb - nb,
                            propose(yb, nb, edge_c) if ok else None, ok))
    return rows


def render(rows):
    lines = [f"{'ticker':<32} {'yes':>4} {'no':>4} {'book':>5}  proposal"]
    for r in rows:
        p = f"{r.proposal.yes_bid}/{r.proposal.no_bid} locks {r.proposal.lock_c}¢" if r.proposal else (
            "— settlement unverified" if not r.settlement_ok else "— no pair locks edge")
        lines.append(f"{r.ticker:<32} {r.yes_bid:>4} {r.no_bid:>4} {r.book_lock_c:>4}¢  {p}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    ap.add_argument("--edge", type=int, default=2)
    ap.add_argument("--log")
    ap.add_argument("--json", help="write a dashboard snapshot (markets + scan rows) to this path")
    a = ap.parse_args(argv)
    import judge
    from . import settlement
    client, cache = judge.from_env(), {}

    def verify(m):
        asset = "BTC" if "BTC" in m["ticker"] else "ETH" if "ETH" in m["ticker"] else m["ticker"]
        rules = " ".join(filter(None, (m.get("rules_primary"), m.get("rules_secondary"))))
        return settlement.verify(client, {"ticker": m["ticker"], "asset": asset, "window_min": 15, "rules": rules}, cache)

    raw = []

    def fetch(path, params=None):
        body = _get(path, params)
        raw.extend(body.get("markets", []))
        return body

    try:
        rows = scan(a.series, fetch=fetch, verify=verify, edge_c=a.edge)
    except OSError as e:
        print(f"Kalshi unreachable: {e}. Allow api.elections.kalshi.com in the network policy.", file=sys.stderr)
        return 2
    print(render(rows))
    if a.json:
        by = {m["ticker"]: m for m in raw}
        snap = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "Kalshi public API /markets (GET only)",
                "markets": [{**asdict(r), "proposal": asdict(r.proposal) if r.proposal else None,
                             "floor_strike": by.get(r.ticker, {}).get("floor_strike"),
                             "open_time": by.get(r.ticker, {}).get("open_time"),
                             "last_price_c": _cents(by.get(r.ticker, {}), "last_price"),
                             "rules": by.get(r.ticker, {}).get("rules_primary", "")} for r in rows]}
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1)
    if a.log:
        ts = datetime.now(timezone.utc).isoformat()
        with open(a.log, "a", encoding="utf-8") as f:
            for r in rows:
                d = asdict(r)
                d["proposal"] = asdict(r.proposal) if r.proposal else None
                f.write(json.dumps({"ts": ts, **d}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
