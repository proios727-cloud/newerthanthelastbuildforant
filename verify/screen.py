"""Screen the TraderDev leaderboard (verify/rows.csv) with the ai-fund-desk Verifier's bar.

    python3 -m verify.screen             # writes verify/screen.json and verify/screened.csv

The pull stores 1,000 rows (200 each from the sharpe/sortino/profit/trades/drawdown sorts), transcribed by script
from the public API responses. max_dd is a percent. Duplicates are the same backtest saved under several ids,
so dedupe on the metrics and window, not the id.
"""
import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROWS = ROOT / "verify" / "rows.csv"

MIN_TRADES, MIN_YEARS, MAX_DD = 150, 3.0, 30.0
PF_BAND, SHARPE_BAND = (1.2, 4.0), (0.8, 4.5)
FLAG_NAME = re.compile(r"IS-only|in-sample|tick-fixed|tick-correct|\bonly\b|verify|repro", re.I)
REALISTIC_SIDE = 0.00055    # 4.5 bp taker + 1 bp slippage, the rebuild's realistic run
CONTROL = re.compile(r"zero-info|control|random|placebo", re.I)
FAMILY = [
    ("vanta_atr_trail_1h", r"vanta"),
    ("ema9_vwap_trend_1h", r"vwap|codex recreation|desk audit codex"),
    ("donchian_breakout", r"donchian|breakout|channel|turtle"),
    ("supertrend", r"supertrend|super trend|\bst\b"),
    ("ema_cross_atr_trail", r"\bema\b|vwap|atr|ma cross|crossover|trend"),
    ("rsi_mean_reversion", r"rsi|mean.?rev|bollinger|\bbb\b"),
    ("sar_momentum", r"\bsar\b|momentum|macd"),
]


def tf_minutes(tf):
    tf = str(tf).strip().lower()
    m = re.fullmatch(r"(\d+)\s*([mhdw]?)", tf)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2) or "m"
    return n * {"m": 1, "h": 60, "d": 1440, "w": 10080}[u]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse(path=ROWS):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            span = (int(r["to_ts"]) - int(r["from_ts"])) / (365.25 * 86400 * 1000)
            net = num(r["net_pct"])
            cagr = (1 + net / 100) ** (1 / span) - 1 if net is not None and span > 0 and net > -100 else None
            out.append({"id": r["id"], "name": r["name"], "symbol": r["symbol"], "tf_min": tf_minutes(r["timeframe"]),
                        "net_pct": net, "max_dd": num(r["max_dd"]), "pf": num(r["profit_factor"]),
                        "sharpe": num(r["sharpe"]), "sortino": num(r["sortino"]), "trades": int(float(r["trades"])),
                        "years": round(span, 2), "cagr": cagr, "url": r["view_url"], "sort": r["sort_source"],
                        "from_ts": r["from_ts"], "to_ts": r["to_ts"]})
    return out


def dedupe(rows):
    """Same backtest under several ids: match symbol, timeframe, net % (to 0.01) and trades."""
    seen, out = set(), []
    for r in rows:
        key = (r["symbol"], r["tf_min"], round(r["net_pct"] or 0, 2), r["trades"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def flags(r):
    f = []
    if (r["pf"] is not None and r["pf"] > 4) or (r["sharpe"] is not None and r["sharpe"] > 5):
        f.append("pf>4 or sharpe>5")
    if r["cagr"] is not None and r["cagr"] > 0.60 and r["max_dd"] is not None and r["max_dd"] < 20:
        f.append("cagr>60% with dd<20%")
    if FLAG_NAME.search(r["name"]):
        f.append("name says in-sample/verify/only")
    if r["max_dd"] is not None and r["max_dd"] > 100:
        f.append("dd>100% (engine quirk)")
    return f


def passes(r):
    why = []
    if r["trades"] < MIN_TRADES:
        why.append("trades<150")
    if r["years"] < MIN_YEARS:
        why.append("span<3y")
    if r["max_dd"] is None or r["max_dd"] > MAX_DD:
        why.append("dd>30%")
    if r["pf"] is None or not PF_BAND[0] <= r["pf"] <= PF_BAND[1]:
        why.append("pf outside 1.2-4")
    if r["sharpe"] is None or not SHARPE_BAND[0] <= r["sharpe"] <= SHARPE_BAND[1]:
        why.append("sharpe outside 0.8-4.5")
    return why


def family(name):
    for fam, pat in FAMILY:
        if re.search(pat, name, re.I):
            return fam
    return "other"


def screen(rows):
    uniq = dedupe(rows)
    fails, survivors, fl = {}, [], {}
    for r in uniq:
        r["flags"] = flags(r)
        for x in r["flags"]:
            fl[x] = fl.get(x, 0) + 1
        why = passes(r)
        for w in why:
            fails[w] = fails.get(w, 0) + 1
        if not why and not r["flags"]:
            r["family"] = family(r["name"])
            survivors.append(r)
    for r in survivors:
        # A strategy that turns over the book this often pays this much a year at realistic fills, at full notional.
        r["cost_drag_yr"] = round(r["trades"] / r["years"] * 2 * REALISTIC_SIDE, 4) if r["years"] else None
        r["control"] = bool(CONTROL.search(r["name"]))
    fams = {}
    for r in survivors:
        f = fams.setdefault(r["family"], {"n": 0, "symbols": set(), "timeframes": set()})
        f["n"] += 1
        f["symbols"].add(r["symbol"])
        f["timeframes"].add(r["tf_min"])
        f.setdefault("drag", []).append(r["cost_drag_yr"])
        f.setdefault("cagr", []).append(r["cagr"])
    fam_out = {k: {"n": v["n"], "symbols": sorted(v["symbols"]), "timeframes_min": sorted(x for x in v["timeframes"] if x),
                   "published_cagr_range": [round(min(v["cagr"]), 3), round(max(v["cagr"]), 3)],
                   "realistic_cost_drag_yr": [min(v["drag"]), max(v["drag"])]}
               for k, v in sorted(fams.items(), key=lambda kv: -kv[1]["n"])}
    summary = {"pulled": len(rows), "unique_backtests": len(uniq), "survivors": len(survivors),
               "survival_rate": round(len(survivors) / len(uniq), 4) if uniq else 0,
               "fail_reasons": dict(sorted(fails.items(), key=lambda kv: -kv[1])),
               "red_flags": {k: {"n": v, "share": round(v / len(uniq), 3)} for k, v in sorted(fl.items(), key=lambda kv: -kv[1])},
               "families": fam_out,
               "controls_surviving": [{"name": r["name"], "sharpe": r["sharpe"], "cagr": round(r["cagr"], 3)}
                                      for r in survivors if r["control"]],
               "bar": {"min_trades": MIN_TRADES, "min_years": MIN_YEARS, "max_dd_pct": MAX_DD, "pf": PF_BAND, "sharpe": SHARPE_BAND}}
    return summary, survivors


def main(path=ROWS):
    summary, surv = screen(parse(path))
    stats = ROOT / "verify" / "stats.json"
    if stats.exists():
        summary["leaderboard"] = json.loads(stats.read_text(encoding="utf-8"))
    keep = ["id", "name", "symbol", "tf_min", "family", "net_pct", "cagr", "max_dd", "pf", "sharpe", "trades", "years",
            "cost_drag_yr", "control", "url"]
    with open(ROOT / "verify" / "screened.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(keep)
        for r in sorted(surv, key=lambda r: -(r["sharpe"] or 0)):
            w.writerow([round(r[k], 4) if isinstance(r[k], float) else r[k] for k in keep])
    (ROOT / "verify" / "screen.json").write_text(json.dumps({"summary": summary}, indent=1) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
