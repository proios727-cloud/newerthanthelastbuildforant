"""Render backtest/O2_report.html from backtest/options_results.json.

  python backtest/options_lab.py && python backtest/options_report.py
"""
import json
import pathlib
from statistics import median

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = json.loads((ROOT / "backtest/options_results.json").read_text())

LADDER_VERDICT = {
    "L0 stock shadow (equities)": ("Baseline", "idle"),
    "L1 long calls on signals": ("Kill", "bad"),
    "L2 + long puts on bearish": ("Kill", "bad"),
    "L3 short puts on signals": ("Marginal", "warn"),
    "L4 short puts + VRP gate": ("Kill as return, keep as overlay", "warn"),
}
SERIES = ["L3 short puts on signals", "L1 long calls on signals", "L0 stock shadow (equities)", "SPY buy-and-hold"]


def pct(v):
    return "–" if v is None else f"{v:+.2f}%"


def row(name, m, verdict=None):
    v = f'<td><span class="chip {verdict[1]}">{verdict[0]}</span></td>' if verdict else "<td></td>"
    wr = "–" if m.get("win_rate") is None else f"{round(100 * m['win_rate'])}%"
    cls = "pos" if m["return_pct"] >= 0 else "neg"
    return (f"<tr><td>{name}</td><td class='{cls}'>{pct(m['return_pct'])}</td><td>{pct(m['cagr_pct'])}</td>"
            f"<td>{m['max_dd_pct']:.2f}%</td><td>{m['mar']}</td><td>{m['trades'] or '–'}</td><td>{wr}</td>"
            f"<td>{m.get('profit_factor') or '–'}</td>{v}</tr>")


def ablation():
    out = []
    labels = {"long_call": "Long calls", "long_both": "Long calls + puts", "short_put": "Short puts"}
    for fam, rows in R["in_sample_grid"].items():
        for k in ("delta", "tp", "stop", "hold"):
            vals = sorted({x[k] for x in rows})
            if len(vals) > 1:
                cells = " · ".join(f"{k} {v}: <b>{median(x['return_pct'] for x in rows if x[k] == v):+.2f}%</b>" for v in vals)
                out.append(f"<tr><td>{labels[fam]}</td><td style='text-align:left;white-space:normal'>{cells}</td></tr>")
    return "".join(out)


def monthly(name):
    m, prev, out = {}, None, []
    for d, n in R["curves"][name]:
        m.setdefault(d[:7], []).append(n)
    for k, v in m.items():
        base = prev or v[0]
        out.append((k, round(100 * (v[-1] / base - 1), 2)))
        prev = v[-1]
    return out


def main():
    lad, bm, cal = R["ladder"], R["benchmarks"], R["calibration"]
    L3, L1, L2, SPY = lad["L3 short puts on signals"], lad["L1 long calls on signals"], lad["L2 + long puts on bearish"], bm["SPY buy-and-hold"]
    rob = R["robustness"]
    rob_rows = "".join(
        f"<tr><td>{k}</td>" + "".join(f"<td class='{'pos' if v >= 0 else 'neg'}'>{pct(v)}</td>" for v in d.values()) + "</tr>"
        for k, d in rob.items())
    cal_rows = "".join(
        f"<tr><td>{a}</td><td>{cal[b] * 100:.1f}%</td><td>{cal[c] * 100:.1f}%</td><td>{(cal[b] / cal[c] - 1) * 100:+.0f}%</td></tr>"
        for a, b, c in [("SPY 30d at-the-money", "SPY_atm_model", "SPY_atm_live"),
                        ("SPY 730 put (4.6% OTM)", "SPY_730P_model", "SPY_730P_live"),
                        ("NVDA 30d at-the-money", "NVDA_atm_model", "NVDA_atm_live"),
                        ("NVDA 210 put (8% OTM)", "NVDA_210P_model", "NVDA_210P_live")])
    stress_rows = ""
    for w, d in R["stress"].items():
        cells = " · ".join(f"{k}: <b>{v:.2f}%</b>" for k, v in d.items())
        stress_rows += f"<tr><td>{w}</td><td style='text-align:left;white-space:normal'>{cells}</td></tr>"
    picks = "".join(
        f"<tr><td>{name}</td><td>{p['test'][0]} → {p['test'][1]}</td><td>{p['delta']}</td><td>{p['tp']}</td><td>{p['stop']}</td><td>{p['hold']}</td></tr>"
        for name, ps in R["picks"].items() for p in ps)
    mon = monthly("L3 short puts on signals")
    mmax = max(abs(v) for _, v in mon) or 1
    mon_rows = "".join(
        f"<div class='bar'><span>{k}</span><span class='track'><span class='fill {'neg-fill' if v < 0 else ''}' "
        f"style='width:{max(2, 100 * abs(v) / mmax):.0f}%'></span></span><span class='val num'>{pct(v)}</span></div>"
        for k, v in mon)
    data = {"series": SERIES, "curves": {k: R["curves"][k] for k in SERIES}}

    html = TEMPLATE
    for k, v in {
        "__OOS__": f"{R['oos_window'][0]} → {R['oos_window'][1]}",
        "__L3C__": pct(L3["cagr_pct"]), "__L3D__": f"{L3['max_dd_pct']:.2f}%", "__L3R__": pct(L3["return_pct"]),
        "__L1R__": pct(L1["return_pct"]), "__L1D__": f"{L1['max_dd_pct']:.2f}%",
        "__L2R__": pct(L2["return_pct"]), "__SPYR__": pct(SPY["return_pct"]),
        "__L3T__": str(L3["trades"]), "__L3W__": f"{round(100 * L3['win_rate'])}%", "__L3PF__": str(L3["profit_factor"]),
        "__LADDER__": "".join(row(k, m, LADDER_VERDICT[k]) for k, m in lad.items()),
        "__BENCH__": "".join(row(k, m) for k, m in bm.items()),
        "__ROBH__": "".join(f"<th>{k.split(' ', 1)[0]}</th>" for k in next(iter(rob.values()))),
        "__ROB__": rob_rows, "__ABL__": ablation(), "__CAL__": cal_rows, "__STRESS__": stress_rows,
        "__PICKS__": picks, "__MON__": mon_rows, "__DATA__": json.dumps(data, separators=(",", ":")),
    }.items():
        html = html.replace(k, v)
    (ROOT / "backtest/O2_report.html").write_text(html)
    print("wrote backtest/O2_report.html")


TEMPLATE = r"""<title>O2 Single-Leg Options Lab</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: verdict first, then tiles, equity chart, ladder, robustness, calibration, then the rules and what's not modeled. */
:root{--bg:#f7f8fa;--surface:#fff;--line:#e3e6ec;--grid:#eceef2;--fg:#12151b;--fg2:#4b5261;--muted:#7a8191;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#8a8f99;
--good:#1f7a3f;--good-bg:#e5f4ea;--warn:#8a5a00;--warn-bg:#fdf1d8;--bad:#b3261e;--bad-bg:#fbe6e4;--idle:#5a6272;--idle-bg:#eef0f4;
--sans:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111318;--surface:#181b21;--line:#2a2f38;--grid:#23272f;--fg:#f2f4f7;--fg2:#b8bfcc;--muted:#8a92a1;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#9aa0aa;--good:#6fd08f;--good-bg:#173323;--warn:#f0c060;--warn-bg:#3a2e12;--bad:#f08a82;--bad-bg:#3d1d1a;--idle:#aab2c0;--idle-bg:#232830;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111318;--surface:#181b21;--line:#2a2f38;--grid:#23272f;--fg:#f2f4f7;--fg2:#b8bfcc;--muted:#8a92a1;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#9aa0aa;--good:#6fd08f;--good-bg:#173323;--warn:#f0c060;--warn-bg:#3a2e12;--bad:#f08a82;--bad-bg:#3d1d1a;--idle:#aab2c0;--idle-bg:#232830;color-scheme:dark}
*{box-sizing:border-box}body{background:var(--bg);color:var(--fg);font:15px/1.55 var(--sans);padding-inline:16px;padding-block:28px 56px}
.wrap{max-width:980px;margin:0 auto;display:grid;gap:26px}h1,h2{margin:0;text-wrap:balance}h1{font-size:1.85rem}h2{font-size:1.12rem}
.eyebrow{font:500 .72rem/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
p{margin:0;max-width:70ch;color:var(--fg2)}.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
section,header{display:grid;gap:12px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;font:500 .76rem/1.3 var(--sans);background:var(--idle-bg);color:var(--idle);white-space:nowrap}
.chip.good{background:var(--good-bg);color:var(--good)}.chip.warn{background:var(--warn-bg);color:var(--warn)}.chip.bad{background:var(--bad-bg);color:var(--bad)}
.verdict{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:10px;padding:16px 18px;display:grid;gap:8px}
.verdict ul{margin:0;padding-left:18px;color:var(--fg2);display:grid;gap:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;gap:2px}
.kpi .v{font:500 1.3rem/1.2 var(--mono)}.kpi .l{font-size:.8rem;color:var(--muted)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;display:grid;gap:12px;min-width:0}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:.84rem;color:var(--fg2)}.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:14px;height:3px;border-radius:2px;display:inline-block}
.chart{position:relative}.chart svg{display:block;width:100%;height:auto}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:12px/1.5 var(--mono);box-shadow:0 4px 14px rgb(0 0 0/.12);white-space:nowrap}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap;vertical-align:top}
th:first-child,td:first-child{text-align:left}th{font:500 .7rem/1.2 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
td{font-family:var(--mono);font-variant-numeric:tabular-nums}td:first-child{font-family:var(--sans)}
.pos{color:var(--good)}.neg{color:var(--bad)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.bars{display:grid;gap:6px}.bar{display:grid;grid-template-columns:70px 1fr 70px;gap:10px;align-items:center;font-size:.84rem}
.track{height:8px;background:var(--grid);border-radius:4px;overflow:hidden;display:block}.fill{display:block;height:100%;background:var(--s1);border-radius:0 4px 4px 0}
.neg-fill{background:var(--bad)}.val{text-align:right}
.rules{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.rule{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;gap:4px}
.rule b{font-size:.78rem;font-family:var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:500}
details{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px 14px}summary{cursor:pointer;font-weight:600}
ul.plain{margin:0;padding-left:18px;color:var(--fg2);display:grid;gap:4px}.foot{font-size:.8rem;color:var(--muted)}
</style>
<div class="wrap">
<header>
  <div class="eyebrow">O2 · research module · single-leg options on the desk universe</div>
  <h1>O2 Single-Leg Options Lab</h1>
  <p>Long calls, long puts and cash-secured short puts on SPY, QQQ, IWM, NVDA, AMD, AAPL, MSFT and TSLA, triggered by the shadow-book signals. Parameters are picked walk-forward (120-day train, 40-day test) and every trade pays modeled bid/ask costs. Out-of-sample window: __OOS__.</p>
</header>

<div class="verdict">
  <strong>Verdict: ITERATE. Selling puts on signals is the only structure that survives, and only just.</strong>
  <ul>
    <li><b>Short puts on bullish signals:</b> __L3R__ out of sample (__L3C__ a year), max drawdown __L3D__, __L3T__ trades, __L3W__ wins, profit factor __L3PF__. It stayed positive at double costs and at ±15% option prices.</li>
    <li><b>Buying calls on the same signals:</b> __L1R__ with a __L1D__ drawdown. The result flips between −3.8% and +14.7% depending on how option prices are modeled, so there's no reliable edge.</li>
    <li><b>Adding long puts on bearish signals:</b> __L2R__. It lost in every variant tested. Kill.</li>
    <li><b>SPY buy-and-hold made __SPYR__ in the same window.</b> Short puts had a far smaller drawdown but didn't beat it on raw return. The test covers five months and one mostly rising market, with option prices modeled rather than recorded.</li>
  </ul>
</div>

<div class="kpis">
  <div class="kpi"><span class="l">Short puts, annualized</span><span class="v">__L3C__</span><span class="l">max DD __L3D__</span></div>
  <div class="kpi"><span class="l">Long calls, out of sample</span><span class="v">__L1R__</span><span class="l">max DD __L1D__</span></div>
  <div class="kpi"><span class="l">Calls + puts, out of sample</span><span class="v">__L2R__</span><span class="l">worst structure</span></div>
  <div class="kpi"><span class="l">SPY buy-and-hold</span><span class="v">__SPYR__</span><span class="l">same window</span></div>
</div>

<section>
  <div class="eyebrow">Out-of-sample equity, $100k start</div>
  <div class="panel">
    <div class="legend" id="lg"></div>
    <div class="chart" id="chart"><div class="tip" id="tip" hidden></div></div>
    <p class="foot">Each walk-forward window starts where the previous one ended, with positions closed at the boundary (costed). Hover or tap for daily values.</p>
  </div>
</section>

<section>
  <div><div class="eyebrow">Upgrade ladder · same out-of-sample window</div><h2>What each step adds</h2></div>
  <div class="panel tbl"><table>
    <thead><tr><th>Step</th><th>Return</th><th>CAGR</th><th>Max DD</th><th>MAR</th><th>Trades</th><th>Win</th><th>PF</th><th>Verdict</th></tr></thead>
    <tbody>__LADDER__</tbody>
    <tbody>__BENCH__</tbody>
  </table></div>
  <p class="foot">KEEP means CAGR is more than 0.5%/yr above the prior step without adding more than 1% drawdown. Short puts beat the stock shadow book by only 0.2%/yr but with a third of the drawdown, so they're rated Marginal. The VRP gate (sell only when implied vol is above realized) cut returns but also cut drawdown, so keep it as a risk overlay.</p>
</section>

<section class="grid2">
  <div class="panel tbl">
    <div class="eyebrow">Robustness · out-of-sample return</div>
    <table><thead><tr><th>Change</th>__ROBH__</tr></thead><tbody>__ROB__</tbody></table>
    <p class="foot">Columns in order: long calls, calls + puts, short puts, short puts with the gate.</p>
  </div>
  <div class="panel">
    <div class="eyebrow">Short puts, monthly</div>
    <div class="bars">__MON__</div>
  </div>
</section>

<section class="grid2">
  <div class="panel tbl">
    <div class="eyebrow">Pricing calibration · live Robinhood, 2026-09-28 close</div>
    <table><thead><tr><th>Contract</th><th>Model IV</th><th>Live IV</th><th>Diff</th></tr></thead><tbody>__CAL__</tbody></table>
    <p class="foot">SPY prices match. Single names come out about 9% rich, which flatters selling premium and penalizes buying it. The IV ×0.85 row above shows the result with cheaper options.</p>
  </div>
  <div class="panel tbl">
    <div class="eyebrow">Ablation · median in-sample return by ingredient</div>
    <table><tbody>__ABL__</tbody></table>
    <p class="foot">Which choices help, across the whole grid. For short puts, 30-delta strikes and a 3× stop beat 20-delta strikes and a 2× stop.</p>
  </div>
</section>

<section>
  <div class="panel tbl">
    <div class="eyebrow">Stress · worst drawdown inside each window</div>
    <table><tbody>__STRESS__</tbody></table>
    <p class="foot">March 2026 (VIX 31) falls before the out-of-sample window, so it's tested with each structure's best in-sample parameters.</p>
  </div>
</section>

<section>
  <div><div class="eyebrow">The surviving strategy</div><h2>How the short-put rule trades</h2></div>
  <div class="rules">
    <div class="rule"><b>Trigger</b>A bullish shadow signal (momentum, breakout or mean reversion) at yesterday's close. One position per symbol.</div>
    <div class="rule"><b>Contract</b>Sell a 30-delta put, about 30 days to expiry, at today's close. Cash-secured.</div>
    <div class="rule"><b>Size</b>Strike × 100 up to 5% of NAV per position. Total secured notional capped at 100% of NAV.</div>
    <div class="rule"><b>Exit</b>Buy back at 50% of the credit, or when the put reaches 3× the credit (walk-forward picked 2–3×), or after 15 sessions or at 7 days left.</div>
    <div class="rule"><b>Overlay</b>Optional VRP gate: sell only when SPY implied vol is above its 20-day realized vol.</div>
    <div class="rule"><b>Status</b>Research only. The next step is a shadow book on live chains with no real orders.</div>
  </div>
</section>

<details><summary>Walk-forward parameter picks</summary><div class="tbl"><table>
  <thead><tr><th>Strategy</th><th>Test window</th><th>Delta</th><th>TP</th><th>Stop</th><th>Hold</th></tr></thead><tbody>__PICKS__</tbody></table></div></details>

<section>
  <div class="eyebrow">Not modeled</div>
  <ul class="plain">
    <li>Real historical option chains. Prices come from a volatility model, which matches live SPY quotes and runs about 9% rich on single names.</li>
    <li>Overnight gaps inside a day, early assignment, dividends and earnings-day IV crush. Stops fill at the close.</li>
    <li>Interest on cash and on put collateral. Idle cash earns 0 here; T-bills would add to short-put returns.</li>
    <li>Any sample longer than 14 months. The out-of-sample window is five months of mostly rising prices with no crash; March 2026 is in-sample only.</li>
    <li>Short calls and multi-leg spreads. These were out of scope for single-leg research.</li>
  </ul>
</section>
<p class="foot">Built from backtest/options_lab.py, which reuses the desk's signals and the options/ Black-Scholes pricer. Data: TradingView daily closes and VIX, plus live Robinhood option quotes for calibration. Research only; not investment advice.</p>
</div>
<script>
const D=__DATA__;const cols=["var(--s1)","var(--s2)","var(--s3)","var(--s4)"];
document.getElementById("lg").innerHTML=D.series.map((s,i)=>`<span><i class="sw" style="background:${cols[i]}"></i>${s}</span>`).join("");
(function(){const el=document.getElementById("chart"),tip=document.getElementById("tip");
const base=D.curves[D.series[0]].map(p=>p[0]);const idx=D.series.map(s=>Object.fromEntries(D.curves[s]));
const W=900,H=320,m={l:64,r:16,t:14,b:30};const vals=D.series.flatMap(s=>D.curves[s].map(p=>p[1]));
const lo=Math.floor(Math.min(...vals)/2500)*2500,hi=Math.ceil(Math.max(...vals)/2500)*2500;
const x=i=>m.l+i*(W-m.l-m.r)/(base.length-1),y=v=>m.t+(hi-v)*(H-m.t-m.b)/(hi-lo);
const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.setAttribute("role","img");
svg.setAttribute("aria-label","Out-of-sample equity curves for "+D.series.join(", "));let g="";
for(let v=lo;v<=hi;v+=2500)g+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${m.l-8}" y="${y(v)+4}" text-anchor="end" font-size="11" font-family="JetBrains Mono,monospace" fill="var(--muted)">$${(v/1000).toFixed(1)}k</text>`;
let lm="";base.forEach((d,i)=>{if(d.slice(0,7)!==lm){lm=d.slice(0,7);g+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle" font-size="11" font-family="JetBrains Mono,monospace" fill="var(--muted)">${new Date(d+"T12:00:00Z").toLocaleString("en-US",{month:"short",timeZone:"UTC"})}</text>`}});
g+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(100000)}" y2="${y(100000)}" stroke="var(--muted)" stroke-dasharray="3 4"/>`;
D.series.slice().reverse().forEach((s,ri)=>{const k=D.series.length-1-ri;let d="",last=null;base.forEach((dt,i)=>{const v=idx[k][dt]??last;if(v==null)return;last=v;d+=(d?"L":"M")+x(i).toFixed(1)+" "+y(v).toFixed(1)});g+=`<path d="${d}" fill="none" stroke="${cols[k]}" stroke-width="2" stroke-linejoin="round"/>`});
g+=`<line id="xh" y1="${m.t}" y2="${H-m.b}" stroke="var(--muted)" visibility="hidden"/>`;svg.innerHTML=g;el.prepend(svg);
const xh=svg.querySelector("#xh");const show=ev=>{const r=svg.getBoundingClientRect(),sx=(ev.clientX-r.left)*W/r.width;
const i=Math.max(0,Math.min(base.length-1,Math.round((sx-m.l)*(base.length-1)/(W-m.l-m.r))));const dt=base[i];
xh.setAttribute("x1",x(i));xh.setAttribute("x2",x(i));xh.setAttribute("visibility","visible");
tip.innerHTML=dt+"<br>"+D.series.map((s,k)=>{const v=idx[k][dt];return v==null?"":`<span style="color:${cols[k]}">■</span> ${s.replace(/^L\d /,"")}: $${Math.round(v).toLocaleString("en-US")}`}).filter(Boolean).join("<br>");
tip.hidden=false;const px=x(i)*r.width/W;tip.style.left=(px>r.width*.55?px-tip.offsetWidth-12:px+12)+"px";tip.style.top="8px"};
svg.addEventListener("pointermove",show);svg.addEventListener("pointerdown",show);svg.addEventListener("pointerleave",()=>{tip.hidden=true;xh.setAttribute("visibility","hidden")});})();
</script>
"""

if __name__ == "__main__":
    main()
