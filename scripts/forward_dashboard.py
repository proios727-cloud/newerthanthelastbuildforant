"""Export the forward paper test as row files for the forward-test dashboard (docs/forward-feed.md).

Reads a chart-forward folder (the `shadow-data` branch) and writes four JSON arrays of row objects:
  status.json    one row: latest bar, data health, next decision, regime flag, paper period totals
  daily.json     one row per session since the first fill: rule and basket, cumulative, before and after costs
  holdings.json  one row per fund the rule holds now: its ticket and its return since the fill
  ranking.json   one row per basket fund: momentum at the last decision and whether the rule holds it
The paper return is the equal-weight return from the fill day's open, as `chart forward rotation-report` computes it, so
the latest daily row matches ROTATION.json; the `_net` columns take off each period's cost at its fill. Research only: nothing here previews, places or approves an order.
    python3 scripts/forward_dashboard.py CHART_FORWARD_DIR OUT_DIR
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from chart import load_csv  # noqa: E402


def _jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _bars(folder, symbols):
    return {s: {b.ts[:10]: b for b in load_csv(pathlib.Path(folder) / f"{s}.csv")} for s in symbols}


def _path(bars, symbols, start, end):
    """[(day, equal-weight return from `start`'s open)] for each session from `start` to `end` every fund has."""
    days = sorted(set.intersection(*(set(bars[s]) for s in symbols)))
    days = [d for d in days if start <= d <= end]
    if not days:
        return []
    opens = {s: bars[s][days[0]].open for s in symbols}
    return [(d, sum(bars[s][d].close / opens[s] for s in symbols) / len(symbols) - 1) for d in days]


def build(d):
    d = pathlib.Path(d)
    rotation = json.loads((d / "ROTATION.json").read_text()) if (d / "ROTATION.json").exists() else {"periods": []}
    doctor = json.loads((d / "DOCTOR.json").read_text())
    overlay = json.loads((d / "OVERLAY.json").read_text()) if (d / "OVERLAY.json").exists() else {}
    decisions = _jsonl(d / "rotation.jsonl")
    tickets = {t["as_of"]: t for t in _jsonl(d / "rotation_tickets.jsonl")}
    trend = _jsonl(d / "rotation_trend200.jsonl")
    last = decisions[-1] if decisions else {}
    basket = last.get("basket", [])
    bars = _bars(d / "etf", basket) if basket else {}
    latest = max((v["newest_bar"] for v in doctor["data"].values()), default="")

    cost = rotation.get("cost_bps_per_side", 0) / 1e4
    daily, rule_base, basket_base, rule_nb, basket_nb = [], 1.0, 1.0, 1.0, 1.0
    for k, p in enumerate(rotation["periods"]):
        rule = _path(bars, p["picks"], p["from"], p["to"]) if p["picks"] else []
        base = _path(bars, basket, p["from"], p["to"])
        rule_fee, basket_fee = 1 - cost * p.get("traded", 0), 1 - cost * (1 if k == 0 else 0)   # paid at the fill
        for (day, r), (_, b) in zip(rule, base):
            daily.append({"day": day, "decided": p["decided"], "rule": round(rule_base * (1 + r) - 1, 5),
                          "basket": round(basket_base * (1 + b) - 1, 5),
                          "rule_net": round(rule_nb * rule_fee * (1 + r) - 1, 5),
                          "basket_net": round(basket_nb * basket_fee * (1 + b) - 1, 5)})
        if rule and base:
            rule_base, basket_base = rule_base * (1 + rule[-1][1]), basket_base * (1 + base[-1][1])
            rule_nb, basket_nb = rule_nb * rule_fee * (1 + rule[-1][1]), basket_nb * basket_fee * (1 + base[-1][1])

    holdings = []
    if rotation["periods"]:
        p = rotation["periods"][-1]
        book = {t["symbol"]: t for t in tickets.get(p["decided"], {}).get("tickets", [])}
        for s in p["picks"]:
            fill, now = bars[s][p["from"]].open, bars[s][max(bars[s])]
            t = book.get(s, {})
            holdings.append({"fund": s, "momentum": last.get("momentum", {}).get(s), "qty": t.get("qty"),
                             "limit": t.get("limit"), "fill_open": round(fill, 2), "last_close": round(now.close, 2),
                             "since_fill": round(now.close / fill - 1, 5)})

    held = set(last.get("picks", []))
    ranking = [{"rank": i + 1, "fund": s, "momentum": m, "held": s in held}
               for i, (s, m) in enumerate(sorted(last.get("momentum", {}).items(), key=lambda kv: -kv[1]))]

    cum = rotation.get("cumulative", {})
    status = [{"latest_bar": latest, "data_ok": doctor["ok"], "problems": len(doctor["problems"]),
               "next_decision": doctor.get("next_rotation_decision"), "days_to_decision": doctor.get("days_to_decision"),
               "decided": last.get("as_of"), "picks": " ".join(last.get("picks", [])),
               "rule": cum.get("rule"), "basket": cum.get("basket"),
               "excess": None if cum.get("rule") is None else round(cum["rule"] - cum["basket"], 5),
               "rule_net": cum.get("rule_net"), "basket_net": cum.get("basket_net"),
               "excess_net": None if cum.get("rule_net") is None else round(cum["rule_net"] - cum["basket_net"], 5),
               "cost_bps": rotation.get("cost_bps_per_side"),
               "regime_hold": overlay.get("hold"), "spy_vs_avg": overlay.get("close_vs_average_now"),
               "trend200_picks": " ".join(trend[-1].get("picks", [])) if trend else ""}]
    return {"status": status, "daily": daily, "holdings": holdings, "ranking": ranking}


def main(argv):
    out = pathlib.Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    tables = build(argv[1])
    for name, rows in tables.items():
        (out / f"{name}.json").write_text(json.dumps(rows, indent=1))
    print(json.dumps({name: len(rows) for name, rows in tables.items()}))


if __name__ == "__main__":
    main(sys.argv)
