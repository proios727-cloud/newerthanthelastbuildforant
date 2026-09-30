"""Jev (TypeSafe System One) handoff for the promoted strategy.

Code keeps every number: RSI(2), moving averages, sizing, the snowball and its kill switch.
Jev answers only the judgments rules cannot: is this dip noise the strategy should buy, or news it
should avoid? Those answers can only VETO or SHRINK a code-generated entry, never create one.

    python -m handoff.jev            # writes handoff/jev_spec.json from data/live/tournament.json
"""
import json
import pathlib

import judge

HERE = pathlib.Path(__file__).resolve().parent
VETO_MIN_P = 0.75
SHRINK_MIN_P = 0.65

QUESTIONS = (
    judge.Question(
        "news_driven_dip", "noul",
        "`symbol` fell over the last two sessions (see `move`). Do the items in `headlines` show that the drop "
        "was caused by new information likely to keep pushing the price lower for days — for example a "
        "recession signal, a policy shock, a credit event or a large index constituent's guidance cut — "
        "rather than ordinary noise, positioning or profit-taking?"),
    judge.Question(
        "regime", "choice",
        "Given `headlines` and `move`, which market regime best describes the current session for `symbol`?",
        {"orderly_uptrend": "Prices are rising in steps and pullbacks are being bought.",
         "choppy_range": "Prices are moving sideways with no follow-through either way.",
         "risk_off_breakdown": "Broad selling tied to macro or credit stress is under way.",
         "event_pending": "A scheduled event (Fed decision, CPI, jobs report) dominates within 24 hours."}),
    judge.Question(
        "setup_quality", "score",
        "How closely does this pullback in `symbol` match a short-lived, liquidity-driven dip inside an "
        "intact uptrend, using `move` and `headlines`?",
        ["Clear breakdown: the dip reflects a change in the trend.",
         "Mostly news-driven with little sign of exhaustion.",
         "Mixed: some news, some routine selling.",
         "Mostly routine selling into an intact uptrend.",
         "Textbook short-lived dip with no material news."]),
)


def policy(answers):
    """Map live answers to an action on a code-generated BUY. Stub answers never change anything."""
    n, reg, q = answers["news_driven_dip"], answers["regime"], answers["setup_quality"]
    if n.value and n.confident(VETO_MIN_P):
        return "skip", f"news-driven dip p={n.probability:.2f}"
    if reg.value == "risk_off_breakdown" and reg.confident(VETO_MIN_P):
        return "skip", "risk-off breakdown regime"
    if reg.value == "event_pending" and reg.confident(SHRINK_MIN_P):
        return "half_size", "scheduled event within 24h"
    if q.live and q.value < 0.35 and q.probability >= SHRINK_MIN_P:
        return "half_size", f"setup quality {q.value:.2f}"
    return "take", "no veto"


def review(client, symbol, move, headlines):
    state = {"symbol": symbol, "move": move, "headlines": list(headlines)[:20]}
    return policy(judge.ask(client, state, QUESTIONS))


def spec(tournament):
    w = next((b for b in tournament["leaderboard"] if b["name"] == tournament["winner"]), None)
    return {
        "strategy": tournament["winner"],
        "params": w["params"] if w else None,
        "out_of_sample": w["out_of_sample"] if w else None,
        "snowball_replay": w["snowball"] if w else None,
        "division_of_labour": {
            "code": ["RSI(2) and SMA signals", "entry/exit timing", "quarter-Kelly sizing",
                     "profit banking", "kill switch (15% DD or last-20 expectancy ≤ 0)"],
            "jev": [q.id for q in QUESTIONS],
        },
        "questions": [{"id": q.id, "primitive": q.primitive, "instructions": q.instructions, "criteria": q.criteria}
                      for q in QUESTIONS],
        "policy": {"veto_min_p": VETO_MIN_P, "shrink_min_p": SHRINK_MIN_P,
                   "actions": ["take", "half_size", "skip"], "jev_can_create_trades": False},
        "go_live": "Set TYPESAFE_API_KEY, TYPESAFE_API_URL and TYPESAFE_LIVE=1; until then answers are stubbed and every BUY is taken.",
    }


def main():
    t = json.loads((HERE.parent / "data" / "live" / "tournament.json").read_text())
    (HERE / "jev_spec.json").write_text(json.dumps(spec(t), indent=1, ensure_ascii=False))
    print(f"wrote handoff/jev_spec.json for {t['winner']}")


if __name__ == "__main__":
    main()
