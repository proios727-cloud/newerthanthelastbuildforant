#!/usr/bin/env python3
"""Build dashboard.html: one page showing the state of all four desks, computed by the desks' own code.

Usage: python scripts/build_dashboard.py [--out dashboard.html]

Sample inputs (the SPY chain, the Kalshi and sportsbook scenarios) are labelled as samples on the page.
Stdlib only.
"""
import argparse
import html
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import judge  # noqa: E402
import kalshi  # noqa: E402
import options  # noqa: E402
import sportsbook  # noqa: E402
from fund import config  # noqa: E402

CHAIN = "SPY-2026-09-29T2054.json"
LIVE = ROOT / "data" / "live"
E = html.escape


def money(x):
    a = abs(x)
    s = f"${a / 1e9:.2f}B" if a >= 1e9 else f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a:,.0f}"
    return ("−" if x < 0 else "") + s


def fund_state():
    cfg = config.load()
    L = cfg.limits
    return {
        "mode": cfg.mode, "word": cfg.approval_word, "nav": cfg.starting_nav,
        "universe": len(cfg.universe),
        "limits": [
            ("Max position", f"{L.max_position_pct:g}% NAV"), ("Gross cap", f"{L.max_gross_pct:g}% NAV"),
            ("Group cap", f"{L.max_group_pct:g}% NAV"), ("Day-loss halt", f"−{L.day_loss_halt_pct:g}%"),
            ("Drawdown halt", f"−{L.drawdown_halt_pct:g}%"), ("Event blackout", f"{L.event_blackout_min:g} min"),
            ("Quote max age", f"{L.max_quote_age_sec:g}s"), ("Preview expires", f"{L.preview_ttl_sec:g}s"),
        ],
    }


def options_state():
    ch = options.load_chain(CHAIN)
    m = options.gex_map(ch)
    by = options.gex_by_strike(ch)
    return {"chain": ch, "map": m, "regime": options.regime(m),
            "bars": [(s, *by[s]) for s in sorted(by)]}


def kalshi_state():
    rows = []
    for label, p, skew in (("Fair 50¢, no skew", 0.50, 0), ("Fair 60¢, lean YES 1¢", 0.60, 1), ("Fair 35¢, no skew", 0.35, 0)):
        q = kalshi.quote(p, edge_c=2, skew_c=skew)
        rows.append((label, q))
    q = kalshi.Quote(49, 49)
    fills = [
        ("Both sides filled ×10", 10, 10, 0.50, 600),
        ("YES only ×10, fair now 42¢", 10, 0, 0.42, 600),
        ("YES only ×10, fair now 48¢", 10, 0, 0.48, 600),
        ("YES only ×10, 30s left", 10, 0, 0.50, 30),
    ]
    scen = [(lbl, kalshi.exposure(y, n, q), kalshi.should_cut(y, n, q, p, s)) for lbl, y, n, p, s in fills]
    return {"quotes": rows, "scenarios": scen}


def sportsbook_state():
    now = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
    old, new = now - timedelta(minutes=15), now - timedelta(minutes=2)
    snaps = [sportsbook.Snap(b, -3.0, old) for b in ("DraftKings", "FanDuel", "BetMGM")]
    snaps += [sportsbook.Snap(b, -4.5, new) for b in ("DraftKings", "FanDuel", "BetMGM")]
    h, a = sportsbook.no_vig(-150, +130)
    return {
        "steam": sportsbook.steam(snaps, now),
        "reverse": sportsbook.reverse_line_move(-3.0, -2.0, home_bet_pct=72),
        "volume": sportsbook.volume_anomaly(40, 62),
        "fair": (h, a), "ev_home": sportsbook.ev_pct(h, -140),
    }


MODELED = ' <span class="sub">(modeled)</span>'


def kalshi_action(m):
    p = m["proposal"]
    return pill(f'{p["yes_bid"]}/{p["no_bid"]}', "green") if p else pill("Unverified · no quote", "dim")


def snowball_state():
    t = json.loads((LIVE / "tournament.json").read_text())
    q = json.loads((LIVE / "equity_quotes.json").read_text())
    c = json.loads((LIVE / "crypto_quotes.json").read_text())
    w = next((b for b in t["leaderboard"] if b["name"] == t["winner"]), None)
    km = LIVE / "kalshi_markets.json"
    return {"t": t, "winner": w, "quotes": q, "crypto": c,
            "kalshi": json.loads(km.read_text()) if km.exists() else None}


def curve_svg(curves, start):
    W, H, padL, padR, padT, padB = 640, 200, 56, 90, 12, 24
    iw, ih = W - padL - padR, H - padT - padB
    allv = [start] + [e for _, pts, _ in curves for _, e, _ in pts]
    lo, hi = min(allv), max(allv)
    lo, hi = lo - (hi - lo) * 0.05 - 1, hi + (hi - lo) * 0.05 + 1
    n = max((len(pts) for _, pts, _ in curves), default=1)
    x = lambda i: padL + iw * i / max(n, 1)
    y = lambda v: padT + (hi - v) / (hi - lo) * ih
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="$500 snowball equity by trade" class="gex">']
    for v in (lo + (hi - lo) * f for f in (0.1, 0.5, 0.9)):
        out.append(f'<line x1="{padL}" x2="{W - padR}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{padL - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">${v:,.0f}</text>')
    out.append(f'<line x1="{padL}" x2="{W - padR}" y1="{y(start):.1f}" y2="{y(start):.1f}" class="zero"/>')
    labels = []
    for name, pts, cls in curves:
        path = " ".join(f"{x(i + 1):.1f},{y(e):.1f}" for i, (_, e, _) in enumerate(pts))
        out.append(f'<polyline points="{x(0):.1f},{y(start):.1f} {path}" class="ln {cls}"/>')
        if pts:
            ex, ey = x(len(pts)), y(pts[-1][1])
            out.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" class="dot {cls}"/>')
            labels.append([ey + 4, ex + 6, f'{E(name)} ${pts[-1][1]:,.0f}', cls])
    labels.sort()
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 12)
    for ly, lx, txt, cls in labels:
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" class="ax {cls}t">{txt}</text>')
    out.append(f'<text x="{padL}" y="{H - 6}" class="ax">trade 1</text><text x="{W - padR}" y="{H - 6}" class="ax" text-anchor="end">trade {n}</text></svg>')
    return "".join(out)


def gex_svg(bars, spot, m):
    W, H, padL, padR, padT, padB = 640, 240, 56, 16, 16, 36
    iw, ih = W - padL - padR, H - padT - padB
    top = max(max(c for _, c, _ in bars), 1.0)
    bot = min(min(p for _, _, p in bars), -1.0)
    y = lambda v: padT + (top - v) / (top - bot) * ih
    n = len(bars)
    slot = iw / n
    bw = slot * 0.34
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Gamma exposure by strike" class="gex">']
    for frac in (0, 0.5, 1):
        v = top - frac * (top - bot)
        out.append(f'<line x1="{padL}" x2="{W - padR}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{padL - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{money(v)}</text>')
    out.append(f'<line x1="{padL}" x2="{W - padR}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="zero"/>')
    for i, (s, c, p) in enumerate(bars):
        cx = padL + slot * (i + 0.5)
        if c > 0:
            out.append(f'<rect x="{cx - bw - 1:.1f}" y="{y(c):.1f}" width="{bw:.1f}" height="{y(0) - y(c):.1f}" class="call"><title>{s:g} calls {money(c)}</title></rect>')
        if p < 0:
            out.append(f'<rect x="{cx + 1:.1f}" y="{y(0):.1f}" width="{bw:.1f}" height="{y(p) - y(0):.1f}" class="put"><title>{s:g} puts {money(p)}</title></rect>')
        cls = "ax strong" if s == m.king else "ax"
        out.append(f'<text x="{cx:.1f}" y="{H - padB + 16}" class="{cls}" text-anchor="middle">{s:g}</text>')
    strikes = [b[0] for b in bars]
    if strikes[0] <= spot <= strikes[-1]:
        j = max(k for k in range(n) if strikes[k] <= spot)
        k2 = min(j + 1, n - 1)
        frac = 0 if k2 == j else (spot - strikes[j]) / (strikes[k2] - strikes[j])
        sx = padL + slot * (j + 0.5 + frac * (k2 - j))
        out.append(f'<line x1="{sx:.1f}" x2="{sx:.1f}" y1="{padT}" y2="{H - padB}" class="spot"/>'
                   f'<text x="{sx - 4:.1f}" y="{padT + 10}" class="ax spotlbl" text-anchor="end">spot {spot:g}</text>')
    out.append("</svg>")
    return "".join(out)


def pill(text, tone):
    return f'<span class="pill {tone}">{E(text)}</span>'


def render():
    f, o, k, s = fund_state(), options_state(), kalshi_state(), sportsbook_state()
    sb = snowball_state()
    t, w = sb["t"], sb["winner"]
    tones = {"meanrev_rsi2": "green", "trend_donchian": "blue", "xs_rotation": "amber", "spy_put_credit_spread_modeled": "red"}
    curves = [(b["name"].split("_")[0], b["curve"], tones.get(b["name"], "blue")) for b in t["leaderboard"]]
    board = "".join(
        f'<tr><td>{E(b["name"])}{MODELED if b["modeled"] else ""}</td>'
        f'<td class="num mono">{b["out_of_sample"]["trades"]}</td><td class="num mono">{b["out_of_sample"]["expectancy"] * 100:+.2f}%</td>'
        f'<td class="num mono">{b["out_of_sample"]["win_rate"]:.0%}</td><td class="num mono">{b["out_of_sample"]["max_dd"]:.1%}</td>'
        f'<td class="num mono">${b["snowball"]["equity"]:,.2f}</td>'
        f'<td>{pill("Promoted", "green") if b["promoted"] else pill("; ".join(b["rejected_because"]), "dim")}</td></tr>'
        for b in t["leaderboard"])
    trig = "".join(
        f'<div class="sig"><span>{E(x["symbol"])}</span><span class="mono">close {x["close"]:g} · RSI2 {x["rsi2"]} · '
        f'SMA {list(x.values())[3]:g}</span>{pill(x["signal"], "green" if x["signal"] != "none" else "dim")}</div>'
        for x in t["triggers"])
    lq = sb["quotes"]["quotes"]
    qrows = "".join(f'<tr><td>{E(k2)}</td><td class="num mono">{v["close"]:,.2f}</td><td class="num mono">{v["bid"]:,.2f} / {v["ask"]:,.2f}</td></tr>' for k2, v in lq.items())
    qrows += "".join(f'<tr><td>{E(k2)}</td><td class="num mono">{v["prev_close"]:,.2f}</td><td class="num mono">{v["bid"]:,.2f} / {v["ask"]:,.2f}</td></tr>' for k2, v in sb["crypto"]["quotes"].items())
    ws = w["snowball"] if w else None
    kl = sb["kalshi"]
    krows = "".join(
        f'<tr><td class="mono">{E(m["ticker"])}</td><td class="num mono">{m["floor_strike"]:,.2f}</td>'
        f'<td class="num mono">{m["yes_bid"]}¢</td><td class="num mono">{m["no_bid"]}¢</td><td class="num mono">{m["book_lock_c"]}¢</td>'
        f'<td>{kalshi_action(m)}</td></tr>'
        for m in (kl["markets"] if kl else []))
    trend_trig = "".join(
        f'<div class="sig"><span>{E(x["symbol"])}</span><span class="mono">close {x["close"]:g} · breakout {x["breakout_level"]:g}</span>'
        f'{pill(x["signal"], "green" if x["signal"] != "none" else "dim")}</div>'
        for x in t.get("all_triggers", {}).get("trend_donchian", []))
    live = judge.from_env().live
    m, ch = o["map"], o["chain"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    limits = "".join(f'<div class="kv"><span>{E(a)}</span><b class="mono">{E(b)}</b></div>' for a, b in f["limits"])
    quotes = "".join(
        f'<tr><td>{E(l)}</td><td class="mono num">{q.yes_bid}¢</td><td class="mono num">{q.no_bid}¢</td>'
        f'<td class="mono num">{q.lock_c}¢</td></tr>' if q else f'<tr><td>{E(l)}</td><td colspan="3">no valid pair</td></tr>'
        for l, q in k["quotes"])
    scen = "".join(
        f'<tr><td>{E(l)}</td><td class="mono num">{"+" if e < 0 else "−"}{abs(e) / 100:.2f}</td>'
        f'<td>{pill("Cut", "red") if c else pill("Hold", "green")}</td></tr>' for l, e, c in k["scenarios"])
    steam = s["steam"]
    fair_h, fair_a = s["fair"]
    regime_tone = "green" if o["regime"] == "positive_gamma" else "amber"
    regime_txt = "Positive gamma · dampening" if o["regime"] == "positive_gamma" else "Negative gamma · trending"

    return f"""<title>Desk Control Room</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root {{
    color-scheme: dark;
    --bg: #0B0D10; --surface: #13171C; --raised: #1A1F26; --border: #232931;
    --ink: #E7EAEE; --muted: #8C95A3; --dim: #5B6472;
    --green: #5EE39A; --amber: #F0B44C; --red: #F26D5B; --blue: #6AA8FF;
    --sans: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
    --mono: "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 13px/1.45 var(--sans); -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 1280px; margin: 0 auto; padding-inline: 20px; padding-block: 20px 40px; display: grid; gap: 16px; }}
  .mono, .num {{ font-family: var(--mono); font-variant-numeric: tabular-nums; }}
  .eyebrow {{ font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--dim); }}
  header {{ display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px 16px; }}
  h1 {{ margin: 0; font-size: 20px; font-weight: 600; text-wrap: balance; }}
  h2 {{ margin: 0; font-size: 14px; font-weight: 600; }}
  .sub {{ color: var(--muted); }}
  .strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
  .strip > div {{ background: var(--surface); padding: 12px 14px; display: grid; gap: 4px; }}
  .strip b {{ font-size: 15px; font-weight: 500; }}
  .grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 560px), 1fr)); gap: 16px; }}
  section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 16px; display: grid; gap: 14px; align-content: start; min-width: 0; }}
  .head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }}
  .pill {{ display: inline-block; font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 999px; border: 1px solid currentColor; white-space: nowrap; }}
  .pill.green {{ color: var(--green); }} .pill.amber {{ color: var(--amber); }} .pill.red {{ color: var(--red); }} .pill.blue {{ color: var(--blue); }} .pill.dim {{ color: var(--muted); }}
  .kvs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 6px 20px; }}
  .kv {{ display: flex; justify-content: space-between; gap: 12px; padding-block: 5px; border-bottom: 1px solid var(--border); }}
  .kv span {{ color: var(--muted); }} .kv b {{ font-weight: 500; }}
  .tbl {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-weight: 500; color: var(--dim); font-size: 11px; padding: 6px 8px 6px 0; border-bottom: 1px solid var(--border); }}
  td {{ padding: 7px 8px 7px 0; border-bottom: 1px solid var(--border); }}
  th.num, td.num {{ text-align: right; }}
  .levels {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }}
  .level {{ background: var(--raised); border-radius: 4px; padding: 8px 10px; display: grid; gap: 2px; }}
  .level b {{ font-family: var(--mono); font-size: 16px; font-weight: 500; }}
  .chart {{ overflow-x: auto; }}
  svg.gex {{ width: 100%; min-width: 440px; height: auto; display: block; }}
  .grid {{ stroke: var(--border); }} .zero {{ stroke: var(--muted); }}
  .spot {{ stroke: var(--blue); stroke-dasharray: 3 3; }}
  .call {{ fill: var(--green); }} .put {{ fill: var(--red); }}
  .ln {{ fill: none; stroke-width: 1.6; }} .ln.green {{ stroke: var(--green); stroke-width: 2.4; }} .ln.blue {{ stroke: var(--blue); }} .ln.amber {{ stroke: var(--amber); }} .ln.red {{ stroke: var(--red); }}
  .dot.green {{ fill: var(--green); }} .dot.blue {{ fill: var(--blue); }} .dot.amber {{ fill: var(--amber); }} .dot.red {{ fill: var(--red); }}
  .greent {{ fill: var(--green); }} .bluet {{ fill: var(--blue); }} .ambert {{ fill: var(--amber); }} .redt {{ fill: var(--red); }}
  .ax {{ fill: var(--dim); font: 10px var(--mono); }} .ax.strong {{ fill: var(--ink); font-weight: 500; }} .spotlbl {{ fill: var(--blue); }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-size: 12px; }}
  .sw {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }}
  .note {{ color: var(--muted); font-size: 12px; max-width: 70ch; }}
  .signals {{ display: grid; gap: 8px; align-content: start; }}
  .sig {{ display: grid; grid-template-columns: 110px 1fr auto; gap: 12px; align-items: center; padding: 8px 10px; background: var(--raised); border-radius: 4px; }}
  .sig span:first-child {{ color: var(--muted); }}
  @media (max-width: 480px) {{ .sig {{ grid-template-columns: 1fr auto; }} .sig span:first-child {{ grid-column: 1 / -1; }} }}
</style>
<div class="wrap">
  <header>
    <div><div class="eyebrow">newerthanthelastbuildforant</div><h1>Desk Control Room</h1></div>
    <div class="sub mono">Built {stamp}</div>
  </header>

  <div class="strip">
    <div><span class="eyebrow">Fund mode</span><b>{pill(f["mode"], "amber")}</b></div>
    <div><span class="eyebrow">$500 snowball · winner replay</span><b class="mono">${ws["equity"]:,.2f} <span class="sub">({ws["return_pct"]:+.2f}%)</span></b></div>
    <div><span class="eyebrow">Live data</span><b class="mono">{E(sb["quotes"]["fetched_at"][:16].replace("T", " "))} UTC</b></div>
    <div><span class="eyebrow">SPY dealer regime</span><b>{pill(regime_txt, regime_tone)}</b></div>
    <div><span class="eyebrow">Kalshi mode</span><b>{pill("SHADOW · live refused", "amber")}</b></div>
    <div><span class="eyebrow">TypeSafe judgments</span><b>{pill("Live", "green") if live else pill("Stub · never blocks", "dim")}</b></div>
  </div>

  <section>
    <div class="head"><h2>$500 snowball · strategy tournament on real Robinhood data</h2>{pill("Winner: " + (t["winner"] or "none qualified"), "green" if t["winner"] else "red")}</div>
    <div class="levels">
      <div class="level"><span class="eyebrow">Start</span><b>$500.00</b></div>
      <div class="level"><span class="eyebrow">Equity</span><b>${ws["equity"]:,.2f}</b></div>
      <div class="level"><span class="eyebrow">Banked (never risked)</span><b>${ws["banked"]:,.2f}</b></div>
      <div class="level"><span class="eyebrow">Trades · win rate</span><b>{ws["trades"]} · {ws["win_rate"]:.0%}</b></div>
      <div class="level"><span class="eyebrow">Max drawdown</span><b>{ws["max_drawdown_pct"]:.2f}%</b></div>
      <div class="level"><span class="eyebrow">Kill switch</span><b>{E(ws["halted"] or "armed")}</b></div>
    </div>
    <div class="chart">{curve_svg(curves, 500.0)}</div>
    <div class="tbl"><table>
      <thead><tr><th>Strategy (out-of-sample from {E(w["split_date"])})</th><th class="num">Trades</th><th class="num">Avg / trade</th><th class="num">Win</th><th class="num">Max DD @25%</th><th class="num">$500 →</th><th>Gate</th></tr></thead>
      <tbody>{board}</tbody></table></div>
    <div class="grid2">
      <div class="signals"><span class="eyebrow">Today's triggers · {E(t["winner"] or "")} (promoted) on {E(t["data"]["last"])} close</span>{trig}<span class="eyebrow">Watchlist · trend_donchian (not promoted)</span>{trend_trig}</div>
      <div class="tbl"><span class="eyebrow">Live quotes</span><table><thead><tr><th>Symbol</th><th class="num">Prev close</th><th class="num">Bid / ask</th></tr></thead><tbody>{qrows}</tbody></table></div>
    </div>
    <p class="note">Every curve replays only out-of-sample trades ({E(t["data"]["first"])} → {E(t["data"]["last"])} daily bars; parameters chosen on the first 70%). Gates: expectancy &gt; 0 after costs, ≥ {t["rules"]["min_trades"]} trades, drawdown ≤ {t["rules"]["kill_dd"]:.0%}. Banking moves 20% of each new high out of risk; the kill switch halts on 15% drawdown or a non-positive last-20 average. Jev can veto or halve a code-generated entry, never create one. Paper only; past results do not guarantee future profit.</p>
  </section>

  <div class="grid2">
    <section>
      <div class="head"><h2>Fund · equities + crypto</h2>{pill(f'{f["universe"]} symbols', "blue")}</div>
      <div class="kvs">{limits}</div>
      <p class="note">Every order goes preview → risk re-check → you type <b class="mono">{E(f["word"])}</b> within the preview window. Exits skip halts and caps so the desk can always get smaller. A confident TypeSafe news-catalyst answer blocks new size only.</p>
    </section>

    <section>
      <div class="head"><h2>Options · SPY gamma map</h2>{pill(regime_txt, regime_tone)}</div>
      <div class="levels">
        <div class="level"><span class="eyebrow">Spot</span><b>{ch["spot"]:g}</b></div>
        <div class="level"><span class="eyebrow">King node</span><b>{m.king:g}</b></div>
        <div class="level"><span class="eyebrow">Call wall</span><b>{m.call_wall:g}</b></div>
        <div class="level"><span class="eyebrow">Put wall</span><b>{m.put_wall:g}</b></div>
        <div class="level"><span class="eyebrow">Flip</span><b>{f"{m.flip:g}" if m.flip else "—"}</b></div>
        <div class="level"><span class="eyebrow">Net / 1%</span><b>{money(m.net)}</b></div>
      </div>
      <div class="chart">{gex_svg(o["bars"], ch["spot"], m)}</div>
      <div class="legend"><span><i class="sw" style="background:var(--green)"></i>Call gamma</span><span><i class="sw" style="background:var(--red)"></i>Put gamma</span><span><i class="sw" style="background:var(--blue)"></i>Spot</span></div>
      <p class="note">Live: {E(ch["source"])}, {E(ch["captured_at"])}. Dollars of dealer delta per 1% move, per strike.</p>
    </section>

    <section>
      <div class="head"><h2>Kalshi · 15-min BTC/ETH maker</h2>{pill("Live · " + (kl["fetched_at"][11:16] + " UTC" if kl else "no data"), "green" if kl else "dim")}</div>
      <div class="tbl"><table>
        <thead><tr><th>Open market</th><th class="num">Strike</th><th class="num">YES bid</th><th class="num">NO bid</th><th class="num">Book lock</th><th>Desk quote</th></tr></thead>
        <tbody>{krows}</tbody></table></div>
      <div class="tbl"><table>
        <thead><tr><th>Fill scenarios on a 49¢ / 49¢ pair</th><th class="num">P&amp;L at risk ($)</th><th>Action</th></tr></thead>
        <tbody>{scen}</tbody></table></div>
      <p class="note">Live from Kalshi's public API (read-only). Each market settles on the 60-second average of the CF Benchmarks index at the end of its 15-minute window vs. its start. The desk quotes nothing until TypeSafe verifies those rules; with the stub, every market shows as unverified. The scenario rows illustrate the cut rules.</p>
    </section>

    <section>
      <div class="head"><h2>Sportsbook · line tracker</h2>{pill("Sample · needs odds key", "dim")}</div>
      <div class="signals">
        <div class="sig"><span>Steam</span><span>{E(f"{len(steam[1])} books moved toward {steam[0]}: " + ", ".join(steam[1])) if steam else "No steam"}</span>{pill("Alert", "amber") if steam else pill("Quiet", "dim")}</div>
        <div class="sig"><span>Reverse line</span><span>72% of bets on home, line moved −3.0 → −2.0 toward {E(s["reverse"] or "none")}</span>{pill("Sharp", "amber") if s["reverse"] else pill("Quiet", "dim")}</div>
        <div class="sig"><span>Money vs tickets</span><span>40% of tickets carry 62% of money</span>{pill("Anomaly", "amber") if s["volume"] else pill("Normal", "dim")}</div>
        <div class="sig"><span>Fair price</span><span class="mono">−150 / +130 → {fair_h:.1%} / {fair_a:.1%} no-vig</span>{pill(f'Home −140 EV {s["ev_home"]:+.1f}%', "green" if s["ev_home"] > 0 else "dim")}</div>
      </div>
      <p class="note">A move counts as sharp only when TypeSafe finds no injury, lineup or weather news that explains it. Alerts only; no bets are placed.</p>
    </section>
  </div>
</div>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dashboard.html"))
    out = pathlib.Path(ap.parse_args().out)
    out.write_text(render(), encoding="utf-8")
    print(f"ok: wrote {out}")


if __name__ == "__main__":
    main()
