#!/usr/bin/env python3
"""Build the GEX/Flow discovery board (SPY + QQQ trinity layout).

Usage:
  python build_gex_board.py --symbols SPY,QQQ --out gex_board.html
  python build_gex_board.py --snapshot data/store.json --out gex_board.html  (offline, from last snapshot)

Validate first, render second - refuses to produce a broken board.
Stdlib only for the build; the snapshot itself is produced by options.snapshot.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MARKER = "/*__GEXDATA__*/null"

STYLE = """
:root{--bg:#0B0D10;--chrome:#0E1115;--surface:#13171C;--raised:#1A1F26;--line:#232A33;
--text:#E7ECEF;--dim:#8B95A0;--green:#10B981;--red:#EF4444;--amber:#F59E0B;--blue:#3B82F6;--violet:#8B5CF6}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font:14px/1.5 'IBM Plex Mono',monospace;padding:24px}
h1{font-size:20px;letter-spacing:.04em;margin-bottom:2px}
.sub{color:var(--dim);font-size:11.5px;margin-bottom:20px}
h2{font-size:12px;letter-spacing:.14em;color:var(--dim);margin:0 0 10px;text-transform:uppercase}
.sym{font-size:22px;font-weight:600;margin:26px 0 8px}
.sym small{font-size:12px;color:var(--dim);font-weight:400;margin-left:10px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .lb{font-size:10px;letter-spacing:.12em;color:var(--dim);text-transform:uppercase}
.tile .v{font-size:21px;font-weight:600;margin-top:4px}
.tile .v.pos{color:var(--green)} .tile .v.neg{color:var(--red)} .tile .v.amb{color:var(--amber)}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;align-items:start}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px}
.bars{display:flex;align-items:flex-end;gap:1px;height:150px;margin-top:8px}
.bar{flex:1;position:relative;background:transparent}
.bar .c,.bar .p{position:absolute;left:0;right:0;border-radius:2px}
.bar .c{bottom:50%} .bar .p{top:50%}
.bar.up .c{background:rgba(16,185,129,.75)} .bar.dn .p{background:rgba(239,68,68,.75)}
.axis{display:flex;gap:1px;margin-top:4px}
.axis span{flex:1;text-align:center;font-size:9.5px;color:var(--dim);white-space:nowrap}
.marker{position:absolute;width:1px;top:0;bottom:0;background:var(--amber);opacity:.7}
table{width:100%;border-collapse:collapse;font-size:12px}
th{color:var(--dim);font-size:10px;letter-spacing:.08em;text-transform:uppercase;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--raised)}
tr.fresh td{color:var(--text)} 
.flag{display:inline-block;font-size:9.5px;padding:1px 6px;border-radius:6px;margin-right:4px}
.flag.fresh{background:rgba(16,185,129,.18);color:var(--green)}
.flag.unusual{background:rgba(245,158,11,.18);color:var(--amber)}
.setups td{padding:8px}
.state{display:inline-block;font-size:10px;font-weight:600;letter-spacing:.1em;padding:2px 10px;border-radius:6px}
.state.armed{background:rgba(239,68,68,.16);color:var(--red)}
.state.watch{background:rgba(245,158,11,.14);color:var(--amber)}
.state.off{background:rgba(139,149,160,.12);color:var(--dim)}
.state.na{background:rgba(139,149,160,.06);color:var(--dim);opacity:.7}
.foot{color:var(--dim);font-size:10.5px;margin-top:18px;border-top:1px solid var(--line);padding-top:10px}
.warn{color:var(--amber)}
"""


def _fmt_m(x):
    if abs(x) >= 1e9:
        return f"{x/1e9:.1f}B"
    if abs(x) >= 1e6:
        return f"{x/1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"{x/1e3:.0f}K"
    return f"{x:.0f}"


def _fmt_p(x):
    return ("+" if x >= 0 else "-") + _fmt_m(abs(x))


def validate(snap):
    problems = []
    if not isinstance(snap, dict) or "symbols" not in snap:
        return ["snapshot must be an object with a 'symbols' key"]
    for sym, s in snap["symbols"].items():
        for key in ("spot", "net_gex", "regime", "bars", "flows", "setups"):
            if key not in s:
                problems.append(f"{sym}: missing '{key}'")
        if "bars" in s:
            for b in s["bars"]:
                if set(b) != {"strike", "call", "put"}:
                    problems.append(f"{sym}: bar rows must be {{strike, call, put}}")
                    break
    return problems


def render_symbol(sym, s):
    bars = s["bars"]
    mx = max((max(b["call"], -b["put"]) for b in bars), default=1) or 1
    net = s["net_gex"]
    regime_cls = "pos" if net > 0 else "neg"
    walls = s.get("walls") or {}

    def tile(label, value, cls=""):
        return f'<div class="tile"><div class="lb">{label}</div><div class="v {cls}">{value}</div></div>'

    tiles = "".join([
        tile("Spot", f'{s["spot"]:.2f}'),
        tile("Net GEX / 1%", _fmt_p(net), regime_cls),
        tile("Regime", "pos gamma" if net > 0 else "neg gamma", regime_cls),
        tile("King", f'{walls.get("king", "—")}'),
        tile("Call wall", f'{walls.get("call_wall", "—")}'),
        tile("Put wall", f'{walls.get("put_wall", "—")}'),
        tile("Flip", f'{walls.get("flip", "—")}'),
        tile("RVOL 5m", f'{s["rvol"]:.2f}' if s.get("rvol") is not None else "—"),
    ])

    h = [f'<div class="sym">{sym}<small>{s.get("note","")}</small></div>']
    h.append(f'<div class="tiles">{tiles}</div>')

    # structure + setups grid
    left = ['<div class="panel"><h2>GEX by strike ($ per 1% move)</h2><div class="bars">']
    axis = []
    n = len(bars)
    for i, b in enumerate(bars):
        ch = int(abs(b["call"]) / mx * 74) if b["call"] > 0 else 0
        ph = int(abs(b["put"]) / mx * 74) if b["put"] < 0 else 0
        strike = b["strike"]
        marker = ""
        if walls.get("flip") == strike or walls.get("king") == strike:
            marker = '<div class="marker"></div>'
        left.append(f'<div class="bar {"up" if ch else "dn"}">{marker}'
                    f'<div class="c" style="height:{ch}px"></div>'
                    f'<div class="p" style="height:{ph}px"></div></div>')
        label = f"{strike:.0f}"
        if n > 26 and i % 2:
            label = ""
        axis.append(f"<span>{label}</span>")
    left.append('</div><div class="axis">' + "".join(axis) + "</div></div>")

    setups_rows = []
    for st in s["setups"]:
        cls = {"ARMED": "armed", "WATCH": "watch", "OFF": "off", "N/A": "na"}[st["state"]]
        setups_rows.append(
            f'<tr><td>{st["setup"].replace("_", " ")}</td>'
            f'<td><span class="state {cls}">{st["state"]}</span></td>'
            f'<td style="color:var(--dim);font-size:11px">{st["reason"]}</td></tr>')
    right = ('<div class="panel"><h2>Setups (structure only)</h2>'
             '<table class="setups"><tr><th>Setup</th><th>State</th><th>Read</th></tr>'
             + "".join(setups_rows) + "</table>"
             + '<p style="color:var(--amber);font-size:10.5px;margin-top:10px">'
             "States derive from delayed structure data only. The doctrine's live "
             "confirmations (RVOL &ge; 1.4 on the breaking bar, failed retest) must be "
             "observed manually before any trade.</p></div>")

    h.append(f'<div class="grid">{"".join(left)}{right}</div>')

    # flows
    flows = s.get("flows") or []
    rows = []
    for f in flows:
        flags = ""
        if f["fresh"]:
            flags += '<span class="flag fresh">FRESH</span>'
        if f["unusual"]:
            flags += '<span class="flag unusual">UNUSUAL</span>'
        voloi = f"{f['vol_oi']:.1f}x" if f["vol_oi"] is not None else "&mdash;"
        rows.append(
            f'<tr><td>{f["strike"]:.0f} {f["kind"]}</td><td>{f["expiry"] or "—"}</td>'
            f'<td>{f["volume"]:,}</td><td>{f["oi"]:,}</td><td>{voloi}</td>'
            f'<td>{_fmt_m(f["premium"])}</td><td>{f["otm_distance"]*100:.1f}%</td>'
            f'<td>{flags}</td></tr>')
    prem = s.get("premium") or {}
    ptiles = (
        '<div class="tiles">'
        + tile("Call premium", _fmt_m(prem.get("call_premium", 0)))
        + tile("Put premium", _fmt_m(prem.get("put_premium", 0)))
        + tile("Net premium", _fmt_p(prem.get("net_premium", 0)),
               "pos" if prem.get("net_premium", 0) >= 0 else "neg")
        + tile("Fresh contracts", str(sum(1 for f in flows if f["fresh"])))
        + "</div>")
    h.append('<h2 style="margin-top:20px">Unusual flow / discovery</h2>')
    h.append(ptiles)
    h.append('<div class="panel"><table><tr><th>Contract</th><th>Exp</th><th>Vol</th>'
             '<th>OI</th><th>Vol:OI</th><th>Premium</th><th>OTM</th><th>Flags</th></tr>'
             + "".join(rows) + "</table></div>")
    return "".join(h)


def render(snap):
    syms_html = "".join(render_symbol(sym, s) for sym, s in snap["symbols"].items())
    ts = snap.get("captured_at", "unknown time")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>GEX / Flow Discovery Board</title>
<style>{STYLE}</style></head>
<body>
<h1>GEX / FLOW DISCOVERY BOARD</h1>
<div class="sub">dealer structure &middot; unusual flow &middot; setup states &mdash; captured {ts} &middot; data: yfinance (delayed; OI from prior close)</div>
{syms_html}
<div class="foot">GEX convention: dealer-short-puts/long-calls &mdash; call gamma adds, put gamma subtracts.
Exposure = gamma &middot; OI &middot; 100 &middot; spot&sup2; &middot; 1% (dollars of delta per 1% move).
Vol:OI compares today's volume to overnight OI; FRESH = vol &ge; OI (positioning that did not exist yesterday).
This board is <span class="warn">intelligence, not signals</span>: every ARMED state still requires the
heatseeker doctrine's live intraday confirmations before any trade.</div>
<script>const DATA = {MARKER};</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=str(ROOT / "data" / "gex_snapshot.json"))
    ap.add_argument("--out", default=str(ROOT / "gex_board.html"))
    a = ap.parse_args()
    try:
        snap = json.loads(pathlib.Path(a.snapshot).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"cannot read snapshot: {e}")
    problems = validate(snap)
    if problems:
        sys.exit("snapshot invalid:\n  " + "\n  ".join(problems))
    pathlib.Path(a.out).write_text(render(snap), encoding="utf-8")
    print(f"ok: wrote {a.out} ({len(snap['symbols'])} symbols)")


if __name__ == "__main__":
    main()