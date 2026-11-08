"""NBA edge scan: Kalshi NBA ladders vs themselves and vs sportsbook consensus. Read-only.

    python skills/nba-edge-scan/scripts/nba_edge_scan.py --dates 26NOV05 26NOV06 [--live] [--out nba_scan.json]

Three checks, in order of how much they can be trusted:
  1. Locks: a higher rung's YES bid above a lower rung's YES ask on the same ladder (total, spread,
     team total, player stat). Buying YES low + NO high pays at least $1 whatever happens.
  2. Book edge: Kalshi price vs the sportsbook consensus with the vig removed (The Odds API, needs
     ODDS_API_KEY). Only same-line comparisons (moneyline, exact spread, exact total), net of the
     Kalshi taker fee.
  3. Off-curve rungs: a normal CDF fitted through each ladder's tight mids; rungs 4+ cents off it.
     A lead only: live ladders late in a game have fat tails a normal fit cannot follow.

Only GET requests. No order, login or key for Kalshi.
"""
import argparse
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from sportsbook import no_vig  # noqa: E402  (repo module: proportional vig removal)

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
ODDS = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
SERIES = {
    "KXNBAGAME": "ml", "KXNBASPREAD": "spread", "KXNBATOTAL": "total", "KXNBATEAMTOTAL": "team_total",
    "KXNBA1HSPREAD": "spread_1h", "KXNBA1HTOTAL": "total_1h",
    "KXNBAPTS": "pts", "KXNBAREB": "reb", "KXNBAAST": "ast", "KXNBA3PT": "threes", "KXNBAPRA": "pra",
    "KXNBASTL": "stl", "KXNBABLK": "blk",
}
TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}
CODE = {v: k for k, v in TEAMS.items()}


def kalshi_fee(p, contracts=1):
    """Kalshi taker fee per contract in dollars: ceil to the cent of 0.07 * C * P * (1 - P)."""
    return math.ceil(0.07 * contracts * p * (1 - p) * 100 - 1e-9) / 100 / contracts


def _f(v):
    return None if v in (None, "") else float(v)


def quote(m):
    """Top of book from a Kalshi market dict (dollar fields, with the legacy cent fields as fallback)."""
    def px(k):
        v = _f(m.get(k + "_dollars"))
        if v is None and m.get(k) is not None:
            v = float(m[k]) / 100
        return v
    bid, ask = px("yes_bid"), px("yes_ask")
    return {"ticker": m["ticker"], "event": m["event_ticker"], "title": m.get("title", ""),
            "bid": bid or 0.0, "ask": ask if ask is not None else 1.0,
            "bid_size": _f(m.get("yes_bid_size_fp")) or 0.0, "ask_size": _f(m.get("yes_ask_size_fp")) or 0.0,
            "volume": _f(m.get("volume_fp")) or 0.0, "status": m.get("status", "")}


def ladder_key(series, m):
    """(ladder id, threshold) for a laddered market, or None. Thresholds are the 'over' cut: 'over k'."""
    kind = SERIES.get(series)
    tail = m["ticker"][len(m["event_ticker"]) + 1:]
    if kind in ("total", "total_1h"):
        return (series, m["event_ticker"], "over"), float(tail) - 0.5
    if kind in ("spread", "spread_1h", "team_total"):
        mm = re.match(r"([A-Z]+)(\d+)$", tail)
        return ((series, m["event_ticker"], mm.group(1)), float(mm.group(2)) - 0.5) if mm else None
    if kind in ("pts", "reb", "ast", "threes", "pra", "stl", "blk"):
        who, _, k = tail.rpartition("-")
        return ((series, m["event_ticker"], who), float(k) - 0.5) if k.isdigit() else None
    return None


def find_locks(ladders, min_gain=0.01):
    """Monotonicity breaks: P(over k) must not rise with k. Gain is per $1 pair before fees."""
    out = []
    for key, rungs in ladders.items():
        rungs = sorted(rungs, key=lambda r: r["k"])
        for i, lo in enumerate(rungs):
            for hi in rungs[i + 1:]:
                gain = hi["bid"] - lo["ask"]
                if gain >= min_gain and lo["ask"] < 1 and hi["bid"] > 0:
                    fees = kalshi_fee(lo["ask"]) + kalshi_fee(1 - hi["bid"])
                    out.append({"ladder": "|".join(key), "buy_yes": lo["ticker"], "yes_ask": lo["ask"],
                                "buy_no": hi["ticker"], "no_ask": round(1 - hi["bid"], 4),
                                "gain": round(gain, 4), "gain_after_fees": round(gain - fees, 4),
                                "size": min(lo["ask_size"], hi["bid_size"])})
    return sorted(out, key=lambda x: -x["gain_after_fees"])


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def off_curve(ladders, min_gap=0.04, min_size=50):
    out = []
    for key, rungs in ladders.items():
        pts = [(r["k"], (r["bid"] + r["ask"]) / 2, r["ask"] - r["bid"]) for r in rungs
               if 0.04 <= r["bid"] and r["ask"] <= 0.96 and r["ask"] - r["bid"] <= 0.05]
        if len(pts) < 4:
            continue
        ks = [p[0] for p in pts]
        best = None
        for mu10 in range(int(min(ks) * 10) - 300, int(max(ks) * 10) + 300, 5):
            mu = mu10 / 10
            for sd in (x / 2 for x in range(2, 80)):
                e = sum((_ncdf((mu - k) / sd) - p) ** 2 / (s + 0.01) for k, p, s in pts)
                if best is None or e < best[0]:
                    best = (e, mu, sd)
        _, mu, sd = best
        for r in rungs:
            fair = _ncdf((mu - r["k"]) / sd)
            if 0.03 <= r["ask"] < 0.97 and fair - r["ask"] >= min_gap and r["ask_size"] >= min_size:
                out.append({"side": "YES", "ticker": r["ticker"], "title": r["title"], "price": r["ask"],
                            "fair": round(fair, 3), "gap": round(fair - r["ask"], 3), "mu": mu, "sd": sd})
            if 0.03 < r["bid"] <= 0.97 and r["bid"] - fair >= min_gap and r["bid_size"] >= min_size:
                out.append({"side": "NO", "ticker": r["ticker"], "title": r["title"], "price": round(1 - r["bid"], 4),
                            "fair": round(1 - fair, 3), "gap": round(r["bid"] - fair, 3), "mu": mu, "sd": sd})
    return sorted(out, key=lambda x: -x["gap"])


def book_edges(markets, books, min_edge=0.01):
    """Kalshi YES/NO vs no-vig consensus at the same line. Edge is net of the Kalshi taker fee."""
    by_ticker = {m["ticker"]: quote(m) for ms in markets.values() for m in ms}
    out = []

    def check(ticker, fair, label, book_line):
        q = by_ticker.get(ticker)
        if not q or q["status"] not in ("active", ""):
            return
        for side, price, p in (("YES", q["ask"], fair), ("NO", 1 - q["bid"], 1 - fair)):
            if 0.02 <= price <= 0.98:
                edge = p - price - kalshi_fee(price)
                if edge >= min_edge:
                    out.append({"side": side, "ticker": ticker, "what": label, "kalshi": round(price, 4),
                                "book_fair": round(p, 4), "edge": round(edge, 4), "book_line": book_line})

    for g in books:
        ev_suffix = g["kalshi_event_suffix"]
        for code, p in g.get("ml_fair", {}).items():
            check(f"KXNBAGAME-{ev_suffix}-{code}", p, f"{TEAMS[code]} win", "moneyline")
        for code, (line, p_cover) in g.get("spread_fair", {}).items():
            if line < 0 and abs(line) % 1 == 0.5:          # favourite -k.5 == 'wins by over k.5' rung
                check(f"KXNBASPREAD-{ev_suffix}-{code}{int(abs(line) + 0.5)}", p_cover,
                      f"{TEAMS[code]} by {abs(line) + 0.5:.0f}+", f"{code} {line}")
        if g.get("total_fair"):
            line, p_over = g["total_fair"]
            if line % 1 == 0.5:
                check(f"KXNBATOTAL-{ev_suffix}-{int(line + 0.5)}", p_over, f"Over {line}", f"total {line}")
    return sorted(out, key=lambda x: -x["edge"])


# ---------- I/O ----------
def _get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nba-edge-scan"}), timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # rate limits come back as HTTP 429 or a JSON error body
            if i == tries - 1:
                raise RuntimeError(f"GET failed: {url}: {e}") from e
            time.sleep(1.5 * 2 ** i)


def pull_kalshi(dates):
    out = {}
    for s in SERIES:
        ms, cur = [], ""
        while True:
            d = _get(f"{KALSHI}/markets?series_ticker={s}&status=open&limit=1000" + (f"&cursor={cur}" if cur else ""))
            ms += d.get("markets", [])
            cur = d.get("cursor") or ""
            if not cur:
                break
        out[s] = [m for m in ms if any(dt in m["event_ticker"] for dt in dates)]
    return out


def pull_books(key):
    q = urllib.parse.urlencode({"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american", "apiKey": key})
    games = _get(f"{ODDS}?{q}")
    out = []
    for g in games:
        home, away = CODE.get(g["home_team"]), CODE.get(g["away_team"])
        if not home or not away:
            continue
        t = datetime.fromisoformat(g["commence_time"].replace("Z", "+00:00"))
        # Kalshi dates NBA events by US Eastern game date; tip-offs after midnight UTC belong to the prior day
        local = t.astimezone(timezone.utc).timestamp() - 5 * 3600
        day = datetime.fromtimestamp(local, timezone.utc).strftime("%y%b%d").upper()
        rec = {"home": home, "away": away, "commence": g["commence_time"], "books": len(g.get("bookmakers", [])),
               "kalshi_event_suffix": f"{day}{away}{home}"}
        ml, sp, tot = defaultdict(list), defaultdict(list), []
        for b in g.get("bookmakers", []):
            for mk in b.get("markets", []):
                oc = {o["name"]: o for o in mk["outcomes"]}
                if mk["key"] == "h2h" and len(oc) == 2:
                    ph, pa = no_vig(oc[g["home_team"]]["price"], oc[g["away_team"]]["price"])
                    ml[home].append(ph); ml[away].append(pa)
                elif mk["key"] == "spreads" and len(oc) == 2:
                    h, a = oc[g["home_team"]], oc[g["away_team"]]
                    ph, pa = no_vig(h["price"], a["price"])
                    sp[(home, h["point"])].append(ph); sp[(away, a["point"])].append(pa)
                elif mk["key"] == "totals" and {"Over", "Under"} <= set(oc):
                    po, _ = no_vig(oc["Over"]["price"], oc["Under"]["price"])
                    tot.append((oc["Over"]["point"], po))
        med = lambda xs: sorted(xs)[len(xs) // 2]
        rec["ml_fair"] = {c: round(med(v), 4) for c, v in ml.items()}
        spreads = {}
        for (c, line), v in sp.items():                    # most-quoted line per team
            if c not in spreads or len(v) > spreads[c][2]:
                spreads[c] = (line, round(med(v), 4), len(v))
        rec["spread_fair"] = {c: (l, p) for c, (l, p, _) in spreads.items()}
        if tot:
            lines = defaultdict(list)
            for line, p in tot:
                lines[line].append(p)
            line = max(lines, key=lambda x: len(lines[x]))
            rec["total_fair"] = (line, round(med(lines[line]), 4))
        out.append(rec)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dates", nargs="+", help="Kalshi date codes, e.g. 26NOV05 (default: today and tomorrow, US Eastern)")
    ap.add_argument("--live", action="store_true", help="include games already in progress (skips the off-curve check, which misreads live tails)")
    ap.add_argument("--out", default="nba_scan.json")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc).timestamp() - 5 * 3600
    dates = a.dates or [datetime.fromtimestamp(now + d * 86400, timezone.utc).strftime("%y%b%d").upper() for d in (0, 1)]
    mk = pull_kalshi(dates)
    ladders = defaultdict(list)
    for s, ms in mk.items():
        for m in ms:
            lk = ladder_key(s, m)
            if lk:
                q = quote(m); q["k"] = lk[1]; ladders[lk[0]].append(q)
    res = {"generated": datetime.now(timezone.utc).isoformat(), "dates": dates,
           "markets": sum(len(v) for v in mk.values()), "locks": find_locks(ladders)}
    res["off_curve"] = [] if a.live else off_curve(ladders)
    key = os.environ.get("ODDS_API_KEY")
    if key:
        books = pull_books(key)
        res["books_games"] = len(books)
        res["book_edges"] = book_edges(mk, books)
    else:
        res["book_edges"] = None
        res["note"] = "ODDS_API_KEY not set: sportsbook comparison skipped."
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"{res['markets']} Kalshi NBA markets for {', '.join(dates)}")
    print(f"locks: {len(res['locks'])}")
    for x in res["locks"][:10]:
        print(f"  +{x['gain_after_fees']:.2f}/pair  YES {x['buy_yes']} @{x['yes_ask']:.2f} + NO {x['buy_no']} @{x['no_ask']:.2f}  size {x['size']:.0f}")
    if res["book_edges"] is None:
        print(res["note"])
    else:
        print(f"book edges (net of Kalshi fee) across {res['books_games']} book games: {len(res['book_edges'])}")
        for x in res["book_edges"][:15]:
            print(f"  {x['edge']:+.3f}  {x['side']} {x['what']} @ {x['kalshi']:.2f}  book fair {x['book_fair']:.2f}  [{x['book_line']}]  {x['ticker']}")
    if not a.live:
        print(f"off-curve leads: {len(res['off_curve'])}")
        for x in res["off_curve"][:10]:
            print(f"  {x['gap']:+.3f}  {x['side']} {x['title']} @ {x['price']:.2f}  curve {x['fair']:.2f}")
    print(f"wrote {a.out}")
    return res


if __name__ == "__main__":
    main()
