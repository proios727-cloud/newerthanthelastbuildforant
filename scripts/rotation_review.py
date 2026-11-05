"""Review the rotation rule's latest monthly decision before anyone acts on it: a one-page REVIEW.md of pass/flag checks.

Checks the decision against an independent recomputation from the stored bars, the rule's settings, the paper tickets'
arithmetic, the data checks, and the record so far. It changes nothing in the log. Research only: it never previews,
places or approves an order; the sign-off lines are for people.
    python3 scripts/rotation_review.py CHART_FORWARD_DIR [OUT.md]     # default: print to stdout
Exit status 0 when every check passes, 1 when any is flagged.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from chart import load_csv  # noqa: E402
from chart.forward import rotation_signal  # noqa: E402

RULE = {"lookback": 60, "top": 3}            # the rule as vetted (docs/rotation-sleeve.md); any change is a flag
NAV, WEIGHT_PCT, LIMIT_BPS = 100_000.0, 5.0, 50


def _jsonl(path):
    path = pathlib.Path(path)
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def review(d):
    d = pathlib.Path(d)
    checks = []

    def check(name, ok, detail):
        checks.append((name, ok, detail))

    decisions = _jsonl(d / "rotation.jsonl")
    tickets = _jsonl(d / "rotation_tickets.jsonl")
    doctor = json.loads((d / "DOCTOR.json").read_text()) if (d / "DOCTOR.json").exists() else {"ok": False, "problems": ["no DOCTOR.json"], "data": {}}
    if not decisions:
        check("Decision logged", False, "rotation.jsonl has no decision yet")
        return None, checks, {}
    dec, prev = decisions[-1], (decisions[-2]["picks"] if len(decisions) > 1 else [])
    bars = {f.stem: load_csv(f) for f in sorted((d / "etf").glob("*.csv"))}
    latest = max(b[-1].ts[:10] for b in bars.values())

    check("Decision is this month's", dec["as_of"][:7] == latest[:7],
          f"last decision {dec['as_of']}, latest bar {latest}" + ("" if dec["as_of"][:7] == latest[:7] else ": this month's decision is missing"))
    check("Recorded on time", not dec.get("late"),
          "recorded the same evening" if not dec.get("late") else f"recorded late, after {dec.get('recorded_after')}")
    check("Rule settings unchanged", dec.get("rule") == RULE, f"logged {dec.get('rule')}, vetted {RULE}")

    upto = {s: [x for x in b if x.ts[:10] <= dec["as_of"]] for s, b in bars.items() if s in dec.get("basket", bars)}
    again = rotation_signal(upto, prev=prev, **RULE)
    if again is None:
        check("Picks recompute", False, f"{dec['as_of']} is not a decision day in the stored bars")
    else:
        moved = [s for s in again["momentum"] if abs(again["momentum"][s] - dec["momentum"].get(s, 99)) > 1e-4]
        same = again["picks"] == dec["picks"] and again["as_of"] == dec["as_of"] and not moved
        check("Picks recompute", same, f"recomputed {again['picks']} vs logged {dec['picks']}"
              + (f"; momentum differs for {', '.join(moved)}" if moved else ""))

    t = next((r for r in tickets if r["as_of"] == dec["as_of"]), None)
    if t is None:
        check("Paper tickets", False, "no tickets for this decision")
    else:
        close = {s: next(x.close for x in bars[s] if x.ts[:10] == dec["as_of"]) for s in {k["symbol"] for k in t["tickets"]}}
        bad = []
        for k in t["tickets"]:
            c = close[k["symbol"]]
            if k["side"] == "buy":
                want_qty, want_lim = int(NAV * WEIGHT_PCT / 100 // c), round(c * (1 + LIMIT_BPS / 1e4), 2)
                if k["qty"] != want_qty or abs(k["limit"] - want_lim) > 0.005:
                    bad.append(f"{k['symbol']} {k['qty']}@{k['limit']} (expected {want_qty}@{want_lim})")
            elif abs(k["limit"] - round(c * (1 - LIMIT_BPS / 1e4), 2)) > 0.005:
                bad.append(f"{k['symbol']} sell limit {k['limit']}")
        buys = sorted(k["symbol"] for k in t["tickets"] if k["side"] == "buy")
        want_buys = sorted(set(dec["picks"]) - set(t.get("kept", [])))
        if buys != want_buys:
            bad.append(f"buys {buys} vs new picks {want_buys}")
        check("Paper tickets", not bad, "; ".join(bad) or
              ", ".join(f"{k['side']} {k['qty']} {k['symbol']} limit {k['limit']:.2f}" for k in t["tickets"]) + f" ({WEIGHT_PCT:g}% of {NAV:,.0f} paper NAV each)")

    check("Data checks", doctor["ok"], "all passing" if doctor["ok"] else "; ".join(doctor["problems"]))
    val = json.loads((d / "VALIDATE.json").read_text()) if (d / "VALIDATE.json").exists() else []
    flagged = [pathlib.Path(v.get("file", "?")).stem for v in val if v.get("problems")]
    check("Price validation", not flagged, "no problems" if not flagged else f"problems in {', '.join(flagged)}")

    rot = json.loads((d / "ROTATION.json").read_text()) if (d / "ROTATION.json").exists() else {}
    overlay = json.loads((d / "OVERLAY.json").read_text()) if (d / "OVERLAY.json").exists() else {}
    trend = _jsonl(d / "rotation_trend200.jsonl")
    context = {"decision": dec, "prev": prev, "rotation": rot, "overlay": overlay,
               "trend": trend[-1] if trend else None, "latest": latest}
    return dec, checks, context


def render(dec, checks, ctx):
    pct = lambda x: "n/a" if x is None else f"{x:+.2%}"
    ok = all(c[1] for c in checks)
    out = [f"# Rotation review: {dec['as_of'] if dec else 'no decision'}", "",
           f"**{'All checks pass' if ok else 'Flagged: resolve before review'}.** Paper only; nothing has been sent.", ""]
    if dec:
        out += [f"Decision: hold **{', '.join(dec['picks']) or 'cash'}**"
                + (f" (was {', '.join(ctx['prev'])})" if ctx["prev"] else " (first decision)") + ".", ""]
    out += ["| Check | Result | Detail |", "|---|---|---|"]
    out += [f"| {n} | {'pass' if k else '**FLAG**'} | {detail} |" for n, k, detail in checks]
    if ctx:
        rot, ov, tr = ctx["rotation"], ctx["overlay"], ctx["trend"]
        done = [p for p in rot.get("periods", []) if p.get("complete")]
        out += ["", "## Record so far", ""]
        if done:
            out += ["| Month decided | Held | Rule | Basket | Rule − basket |", "|---|---|---|---|---|"]
            out += [f"| {p['decided']} | {' '.join(p['picks']) or 'cash'} | {pct(p['rule'])} | {pct(p['basket'])} | {pct(p['excess'])} |" for p in done]
            out += ["", f"Months ahead of the basket: {rot.get('months_beat_basket', 0)} of {len(done)}."]
        else:
            out += ["No completed month yet."]
        cum = rot.get("cumulative", {})
        out += [f"Since the first fill, through {ctx['latest']}: rule {pct(cum.get('rule'))}, basket {pct(cum.get('basket'))}.", "",
                "## Context", "",
                f"- **Defensive variant (cash below the basket's 200-session average):** "
                + (f"holds {', '.join(tr['picks']) or 'cash'}." if tr else "not logged."),
                f"- **SPY regime flag:** " + (f"{'above' if ov.get('hold') else 'below'} its 10-month average, {pct(ov.get('close_vs_average_now'))} now "
                                               f"(information only, not on the book)." if ov else "not logged."),
                "- **Long history:** the rule trailed the equal-weight basket by about 1 point a year over 2004–2026 and roughly "
                "halved the worst drawdown. One month says little either way."]
    out += ["", "## Sign-off", "", "Paper review only. A live order still needs every line below, in order, and `EXECUTE`.", "",
            "- Analyst: ____________________ date ________",
            "- Risk Officer: ____________________ date ________",
            "- Trader: ____________________ date ________", ""]
    return "\n".join(out), ok


def main(argv):
    dec, checks, ctx = review(argv[1])
    text, ok = render(dec, checks, ctx)
    if len(argv) > 2:
        pathlib.Path(argv[2]).write_text(text)
    else:
        print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
