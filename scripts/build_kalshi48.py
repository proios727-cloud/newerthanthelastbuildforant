#!/usr/bin/env python3
"""Build kalshi_48h.html: a replay of the last N hours of KXBTC15M/KXETH15M from Kalshi's own history.

Usage: python scripts/build_kalshi48.py [--hours 48] [--cache PATH] [--out kalshi_48h.html]

REPLAY, not live trading: settled markets + 1-minute candles (bid/ask), read-only GETs. The late-window
rule is fixed up front (buy the favourite at the ask at T-2min if ask is in [LO, HI), hold to
settlement, taker fee charged, 1 contract) so the page is not tuned to the data. Stdlib only.
"""
import argparse
import html
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kalshi import calibration, fills, taker_fee_cents  # noqa: E402

SERIES = ("KXBTC15M", "KXETH15M")
MINUTES = (14, 10, 5, 3, 2, 1)
ENTRY_MIN, LO, HI = 2, 90, 96
# Rule B, fixed 2026-09-29 from the first 48h replay, judged only on older (out-of-sample) markets:
# at T-1min buy the favourite at the real taker prints of the next 10s if they average 50–95¢.
B_MIN, B_LO, B_HI = 1, 50, 96
IN_SAMPLE = (calibration._ts("2026-09-26T22:30:00Z"), calibration._ts("2026-09-28T22:30:00Z"))  # closes the rule was found on
E = html.escape


def collect(hours, cache):
    fetch = calibration.throttled()
    since = int(time.time()) - hours * 3600
    rows = {}
    if cache and pathlib.Path(cache).exists():
        for line in open(cache, encoding="utf-8"):
            r = json.loads(line)
            rows[(r["ticker"], r["minutes_left"])] = r
    for s in SERIES:
        for m in calibration.settled_markets(s, hours * 4 + 8, fetch, since_ts=since):
            need = [n for n in MINUTES if (m["ticker"], n) not in rows]
            for r in calibration.snapshots(m, need, fetch) if need else []:
                r["series"] = s
                rows[(r["ticker"], r["minutes_left"])] = r
                if cache:
                    with open(cache, "a", encoding="utf-8") as f:
                        f.write(json.dumps(r) + "\n")
    out = [r for r in rows.values() if r["close_ts"] >= since]
    for r in out:
        if r["minutes_left"] == B_MIN and "fill" not in r:
            r.update(fills.price_entry(r, fills.window_trades(r["ticker"], r["close_ts"], fetch=fetch)))
            if cache:
                with open(cache, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r) + "\n")
    return out


def rule_b(rows):
    """Rule B trades split into out-of-sample (outside IN_SAMPLE) and in-sample."""
    ins = lambda r: IN_SAMPLE[0] <= r["close_ts"] <= IN_SAMPLE[1]
    t = sorted((r for r in rows if r["minutes_left"] == B_MIN and r.get("fill") is not None
                and B_LO <= r["fill"] < B_HI), key=lambda r: r["close_ts"])
    return [r for r in t if not ins(r)], [r for r in t if ins(r)]


def stats(trades):
    eq = peak = dd = 0
    for r in trades:
        eq += r["pnl_c"]
        peak, dd = max(peak, eq), max(dd, max(peak, eq) - eq)
    n = len(trades)
    return {"n": n, "hit": f"{100 * sum(r['won'] for r in trades) / n:.1f}%" if n else "—",
            "pnl": eq, "ev": f"{eq / n:+.2f}¢" if n else "—", "dd": dd,
            "curve": [(r["close_ts"], sum(x["pnl_c"] for x in trades[:i + 1]), r["pnl_c"], "") for i, r in enumerate(trades)]}


def simulate(rows):
    trades = sorted((r for r in rows if r["minutes_left"] == ENTRY_MIN and LO <= r["ask"] < HI),
                    key=lambda r: r["close_ts"])
    eq, peak, dd, curve = 0, 0, 0, []
    for r in trades:
        p = (100 if r["won"] else 0) - r["ask"] - taker_fee_cents(r["ask"], 1)
        eq += p
        peak, dd = max(peak, eq), max(dd, max(peak, eq) - eq)
        curve.append((r["close_ts"], eq, p, r["series"]))
    wins = sum(1 for c in curve if c[2] > 0)
    return {"n": len(curve), "wins": wins, "pnl": eq, "max_dd": dd, "curve": curve,
            "risk": sum(r["ask"] for r in trades)}


def spread_stats(rows):
    out = []
    for n in MINUTES:
        b = [r["spread"] for r in rows if r["minutes_left"] == n]
        out.append((n, len(b), round(100 * sum(s >= 2 for s in b) / len(b)) if b else 0,
                    round(sum(b) / len(b), 1) if b else 0))
    return out


def svg_curve(curve, w=860, h=220):
    if not curve:
        return "<p class=mut>no trades in window</p>"
    xs = [c[0] for c in curve]
    ys = [0] + [c[1] for c in curve]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    x0, x1 = xs[0], xs[-1] or 1
    px = lambda t: 40 + (t - x0) / ((x1 - x0) or 1) * (w - 50)
    py = lambda v: h - 20 - (v - lo) / span * (h - 40)
    pts = " ".join(f"{px(t):.1f},{py(v):.1f}" for t, v in zip([x0] + xs, ys))
    zero = py(0)
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Equity curve in cents per contract">'
            f'<line x1="40" x2="{w-10}" y1="{zero:.1f}" y2="{zero:.1f}" class=ax />'
            f'<polyline points="{pts}" class=ln fill=none />'
            f'<text x="4" y="{py(hi)+4:.1f}" class=tx>{hi:+d}¢</text>'
            f'<text x="4" y="{py(lo)+4:.1f}" class=tx>{lo:+d}¢</text></svg>')


def rule_b_section(rows):
    oos, ins = rule_b(rows)
    so, si = stats(oos), stats(ins)
    row = lambda k, x: (f"<tr><td>{k}</td><td>{x['n']}</td><td>{x['hit']}</td><td>{x['ev']}</td>"
                        f"<td>{x['pnl']:+d}¢</td><td>{x['dd']}¢</td></tr>")
    verdict = ("holds out of sample — next gate is live shadow fills" if so["n"] >= 30 and so["pnl"] > 0
               else "does not hold out of sample yet" if so["n"] >= 30 else "not enough out-of-sample trades to judge")
    return f"""<h2>Rule B: T-{B_MIN}min favourite at real taker prints</h2>
<div class=card>{svg_curve(so["curve"])}<div class=mut>Out-of-sample equity (markets outside the 48h window the rule was found in, Sep 26 22:30 – Sep 28 22:30 UTC).
Entry = VWAP takers actually paid for the favourite in the 10s after T-{B_MIN}min, {B_LO}¢ ≤ fill &lt; {B_HI}¢, fee included, 1 contract.</div>
<table><tr><th>sample</th><th>trades</th><th>win rate</th><th>EV/trade</th><th>net</th><th>max DD</th></tr>
{row("out-of-sample (the test)", so)}{row("in-sample (the 48h it came from)", si)}</table>
<p><b>Verdict:</b> {verdict}.</p></div>"""


def page(rows, hours):
    sim = simulate(rows)
    hit = f"{100 * sim['wins'] / sim['n']:.1f}%" if sim["n"] else "—"
    roi = f"{100 * sim['pnl'] / sim['risk']:+.2f}%" if sim["risk"] else "—"
    buckets = "".join(
        f"<tr><td>{E(s['bucket'])}</td><td>{s['n']}</td>" + (
            f"<td>{s['hit']}</td><td>{s['avg_ask']}</td><td>{s['ev_c']:+}</td><td>{s['worst_c']}</td>"
            if s["n"] else "<td colspan=4 class=mut>—</td>") + "</tr>"
        for s in calibration.summarize([r for r in rows if r["minutes_left"] == ENTRY_MIN]))
    spreads = "".join(f"<tr><td>T-{n}</td><td>{c}</td><td>{p}%</td><td>{a}¢</td></tr>"
                      for n, c, p, a in spread_stats(rows))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    markets = len({r["ticker"] for r in rows})
    tile = lambda k, v, cls="": f'<div class="tile {cls}"><b>{v}</b><span>{k}</span></div>'
    good = "pos" if sim["pnl"] > 0 else "neg"
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Kalshi Replay Desk</title><style>
:root{{--bg:#0b0f14;--pn:#121923;--tx:#e6edf3;--mu:#8b98a8;--ln:#3fb6ff;--pos:#3ddc97;--neg:#ff6b6b;--bd:#223042}}
@media(prefers-color-scheme:light){{:root{{--bg:#f5f7fa;--pn:#fff;--tx:#14202b;--mu:#5b6b7b;--ln:#0a6fd6;--pos:#0c9a5e;--neg:#d23b3b;--bd:#d7dee6}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:14px/1.5 system-ui,sans-serif;padding:16px;max-width:960px;margin:auto}}
h1{{font-size:20px;margin:0}}h2{{font-size:15px;margin:22px 0 8px}}.mut{{color:var(--mu)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:14px 0}}
.tile{{background:var(--pn);border:1px solid var(--bd);border-radius:8px;padding:10px}}.tile b{{display:block;font-size:20px}}.tile span{{color:var(--mu);font-size:12px}}
.pos b{{color:var(--pos)}}.neg b{{color:var(--neg)}}.card{{background:var(--pn);border:1px solid var(--bd);border-radius:8px;padding:12px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:5px 8px;text-align:right;border-bottom:1px solid var(--bd)}}th:first-child,td:first-child{{text-align:left}}
svg{{width:100%;height:auto}}.ln{{stroke:var(--ln);stroke-width:2}}.ax{{stroke:var(--bd)}}.tx{{fill:var(--mu);font-size:11px}}
.warn{{border-left:3px solid var(--neg);padding-left:10px;color:var(--mu)}}</style></head><body>
<h1>Kalshi desk — {hours}h replay</h1>
<div class=mut>KXBTC15M + KXETH15M · as of {now} · {markets} settled markets · REPLAY from Kalshi history, SHADOW only, no orders</div>
<div class=tiles>{tile("late-window trades", sim["n"])}{tile("win rate", hit)}{tile("net P&amp;L (¢/contract)", f'{sim["pnl"]:+d}¢', good)}{tile("return on capital at risk", roi, good)}{tile("max drawdown", f'{sim["max_dd"]}¢', "neg")}</div>
{rule_b_section(rows)}
<h2>Rule A (T-2min, 90–95¢, candle ask) equity curve</h2>
<div class=card>{svg_curve(sim["curve"])}<div class=mut>Rule fixed in advance: buy the favourite at the ask at T-{ENTRY_MIN}min if {LO}¢ ≤ ask &lt; {HI}¢, hold to settlement, taker fee included, 1 contract per market.</div></div>
<h2>Favourite calibration at T-{ENTRY_MIN}min (all markets)</h2>
<div class=card><table><tr><th>ask ¢</th><th>n</th><th>hit rate</th><th>avg ask</th><th>net EV ¢</th><th>worst ¢</th></tr>{buckets}</table></div>
<h2>Lock desk context: book spread by time to close</h2>
<div class=card><table><tr><th>when</th><th>snapshots</th><th>spread ≥ 2¢</th><th>avg spread</th></tr>{spreads}</table>
<div class=mut>A lock needs spread ≥ 2¢ before any improvement. Snapshots are 1-minute candle closes, not the full book.</div></div>
<h2>Read this as</h2><p class=warn>A {hours}-hour window is a small sample; a positive result here is a lead to keep shadow-testing, not proof of edge. Candle asks are minute closes, so fills at those prices are not guaranteed. Nothing here places orders; LIVE stays gated.</p>
</body></html>"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--cache")
    ap.add_argument("--out", default=str(ROOT / "kalshi_48h.html"))
    a = ap.parse_args(argv)
    rows = collect(a.hours, a.cache)
    pathlib.Path(a.out).write_text(page(rows, a.hours), encoding="utf-8")
    sim = simulate(rows)
    oos, ins = (stats(x) for x in rule_b(rows))
    print(f"wrote {a.out}: {len({r['ticker'] for r in rows})} markets; rule A {sim['n']} trades "
          f"pnl {sim['pnl']:+d}¢ maxDD {sim['max_dd']}¢; rule B out-of-sample {oos['n']} trades "
          f"hit {oos['hit']} pnl {oos['pnl']:+d}¢ maxDD {oos['dd']}¢ | in-sample {ins['n']} pnl {ins['pnl']:+d}¢")
    return 0


if __name__ == "__main__":
    sys.exit(main())
