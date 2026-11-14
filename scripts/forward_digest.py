"""Weekly digest of the forward paper test: one short markdown page for the Friday report (docs/forward-feed.md).

Covers the last 7 calendar days up to the latest stored bar: rule vs basket over the week and since the first fill,
before and after costs; the monthly review's flags; weekdays with no bar (a missed feed or a market holiday); data
checks; and the next decision. Built from the same rows as the dashboard (scripts/forward_dashboard.py).
Research only: nothing here previews, places or approves an order.
    python3 scripts/forward_digest.py CHART_FORWARD_DIR [OUT.md]     # default: print to stdout
"""
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import forward_dashboard  # noqa: E402


def _pct(x):
    return "n/a" if x is None else f"{x:+.2%}"


def _change(rows, key, before):
    """Compounded change of cumulative column `key` over `rows`, from the row `before` them (or from 0)."""
    if not rows or rows[-1].get(key) is None:
        return None
    base = before.get(key, 0) if before else 0
    return (1 + rows[-1][key]) / (1 + base) - 1


def digest(d):
    t = forward_dashboard.build(d)
    s, daily, review = t["status"][0], t["daily"], t["review"]
    latest = s["latest_bar"]
    if not latest:
        return "# Forward test: weekly digest\n\nNo bars stored yet.\n"
    end = date.fromisoformat(latest)
    start = end - timedelta(days=6)
    week = [r for r in daily if r["day"] >= start.isoformat()]
    before = next((r for r in reversed(daily) if r["day"] < start.isoformat()), None)
    have = {r["day"] for r in daily}
    first = daily[0]["day"] if daily else latest
    weekdays = [start + timedelta(days=i) for i in range(7)]
    gaps = [x.isoformat() for x in weekdays if x.weekday() < 5 and x.isoformat() >= first and x.isoformat() not in have]
    flags = [r for r in review if not r["pass"]]

    out = [f"# Forward test: week to {latest}", "",
           f"Holding **{s['picks'] or 'cash'}** since the {s['decided']} decision. Paper only; nothing has been sent.", "",
           "| | Rule | Basket | Rule − basket |", "|---|---|---|---|"]
    for label, key in (("This week", ""), ("This week, after costs", "_net")):
        r, b = _change(week, "rule" + key, before), _change(week, "basket" + key, before)
        out.append(f"| {label} | {_pct(r)} | {_pct(b)} | {_pct(None if r is None or b is None else r - b)} |")
    for label, key in (("Since first fill", ""), ("Since first fill, after costs", "_net")):
        out.append(f"| {label} | {_pct(s.get('rule' + key))} | {_pct(s.get('basket' + key))} | {_pct(s.get('excess' + key))} |")
    out += ["",
            f"- **Sessions this week:** {len(week)}"
            + (f"; no bar for {', '.join(gaps)} (a missed run or a market holiday)." if gaps else ", none missing."),
            f"- **Data checks:** " + ("all passing." if s["data_ok"] else f"{s['problems']} problem(s); see DOCTOR.json."),
            f"- **Monthly review of {s['decided']}:** "
            + ("all {} checks pass.".format(len(review)) if not flags else
               f"{len(flags)} flagged: " + "; ".join(f"{r['check']} ({r['detail']})" for r in flags) + "."),
            f"- **Next decision:** {s['next_decision']}, in {s['days_to_decision']} days.",
            "- **Variant A (120 sessions, top 3), paper comparison only:** " + (
                f"holding {s['v120_picks'] or 'cash'} since its {s['v120_decided']} decision; after costs since "
                f"{s['v120_from']}, {_pct(s['v120_rule_net'])} against the live rule's {_pct(s['v120_live_net_same_span'])}."
                if s.get("v120_from") else
                f"logged {s['v120_decided']}, waiting for its first fill." if s.get("v120_decided") else
                f"first decision due {s['next_decision']}."),
            "- One week says nothing about the rule; the long-history verdict is in docs/rotation-sleeve.md.", ""]
    return "\n".join(out)


def main(argv):
    text = digest(argv[1])
    if len(argv) > 2:
        pathlib.Path(argv[2]).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main(sys.argv)
