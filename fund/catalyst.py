"""News-catalyst judgment for the fund desk (TypeSafe).

Before a new or adding position is previewed, recent headlines for the symbol are judged:
  material  (noul)  — does any headline describe a scheduled or breaking event likely to move the price
                       sharply within the holding window (earnings, guidance, FDA, M&A, halt, hack, depeg)?
  direction (choice)— bullish | bearish | mixed | none, for the analyst's notes only.

Policy lives here, not in the model: a live, confident `material` answer blocks opening size the same
way a macro blackout does. Exits are never blocked. Stub answers never block.
"""
import judge

MATERIAL_MIN_P = 0.80

QUESTIONS = (
    judge.Question(
        "material", "noul",
        "Do any of the headlines in `headlines` describe an event about `symbol` that is likely to move its "
        "price sharply within the next trading day — for example earnings or guidance, regulatory decisions, "
        "mergers, trading halts, exchange hacks or stablecoin depegs? Commentary, price recaps and "
        "unrelated tickers do not count."),
    judge.Question(
        "direction", "choice",
        "Taken together, what price direction do the headlines in `headlines` imply for `symbol`?",
        {"bullish": "Headlines point to the price rising.",
         "bearish": "Headlines point to the price falling.",
         "mixed": "Headlines point in both directions with no clear balance.",
         "none": "Headlines carry no directional information about this symbol."}),
)


def assess(client, symbol, headlines):
    if not headlines:
        return None
    state = {"symbol": symbol, "headlines": list(headlines)[:20]}
    return judge.ask(client, state, QUESTIONS)


def veto(answers):
    """(rule, detail) when opening size must be blocked, else None."""
    if not answers:
        return None
    m = answers["material"]
    if m.value and m.confident(MATERIAL_MIN_P):
        return ("news_catalyst", f"material headline risk p={m.probability:.2f} ≥ {MATERIAL_MIN_P}")
    return None
