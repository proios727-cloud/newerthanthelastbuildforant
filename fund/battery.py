"""The JEV question battery for option-selling entries (TypeSafe System One). Veto-only.

Four atomic questions ride one request over a compact, structured state (numbers computed in code plus
cleaned headlines — never raw page text):
  material   noul   does a headline describe an event likely to move the price sharply soon?
  regime     choice calm_trend | choppy | high_vol | crisis
  setup      score  poor < weak < acceptable < strong: does the state support selling this put now?
  liquidity  score  illiquid < thin < adequate < deep: can the contract be entered and exited near mid?

Policy lives here, in code: each question has a "bad" probability and a threshold, and a sale is vetoed
only when a LIVE answer's bad probability reaches it. Stub answers never veto. Answers whose confidence
is below ESCALATE_BELOW are flagged for review by the head agent (Opus) instead of being acted on.
Every bad probability is stored on the trade so fund/calibration.py can score it against outcomes.
"""
import judge

from .catalyst import QUESTIONS as CATALYST_QUESTIONS, clean

MATERIAL = CATALYST_QUESTIONS[0]
REGIME = judge.Question(
    "regime", "choice",
    "Given `market` for `symbol` (recent returns, realized and implied volatility, the signal that fired) and "
    "the headlines in `headlines`, which regime is `symbol` trading in right now?",
    {"calm_trend": "Orderly move in one direction with volatility near or below its usual level.",
     "choppy": "Range-bound or directionless trading with ordinary volatility.",
     "high_vol": "Volatility clearly above normal, large daily swings, but markets functioning.",
     "crisis": "Disorderly selling, gaps, halts or a systemic shock: selling downside protection is dangerous."})
SETUP = judge.Question(
    "setup", "score",
    "Judge the trade in `trade` against `market` and `headlines`: how good is selling this put now, considering "
    "whether implied volatility pays for realized risk, the distance to the strike, time to expiry and the "
    "signal? Do not judge liquidity here.",
    ["poor: the premium does not pay for the risk or the setup contradicts the signal",
     "weak: marginal; small premium for the risk or mixed evidence",
     "acceptable: premium roughly fair for the risk, signal intact",
     "strong: implied volatility clearly exceeds realized, strike well protected, signal intact"])
LIQUIDITY = judge.Question(
    "liquidity", "score",
    "Using the bid-ask spread and size fields in `trade`, how easily can this contract be sold now and bought "
    "back later near the middle of the spread?",
    ["illiquid: spread so wide or size so small that fills near mid are unlikely",
     "thin: fills possible but expect to give up a meaningful part of the spread",
     "adequate: normal spread for this underlying, modest slippage",
     "deep: tight spread and ample size"])
QUESTIONS = (MATERIAL, REGIME, SETUP, LIQUIDITY)

# code-side policy: (question id, rule name, threshold on the bad probability)
VETO = (("material", "news_catalyst", 0.80), ("regime", "regime_crisis", 0.70),
        ("setup", "setup_poor", 0.70), ("liquidity", "illiquid", 0.70))
ESCALATE_BELOW = 0.60


def bad_p(qid, a):
    """Probability of the bad outcome for one answer, or None when the answer carries none."""
    if a is None:
        return None
    if qid == "material":
        return a.probability
    d = a.distribution or {}
    if qid == "regime":
        return d.get("crisis")
    if qid in ("setup", "liquidity"):
        return d.get("0", d.get(0))
    return None


def state(symbol, headlines, context):
    items = [h for h in (clean(x) for x in list(headlines or [])[:20]) if h]
    ctx = context or {}
    return {"symbol": symbol, "headlines": items, "market": ctx.get("market", {}), "trade": ctx.get("trade", {})}


def assess(client, symbol, headlines, context):
    """{question_id: Answer} for the whole battery, or just the headline question when there is no context."""
    st = state(symbol, headlines, context)
    if context:
        return judge.ask(client, st, QUESTIONS)
    if not st["headlines"]:
        return None
    return judge.ask(client, st, (MATERIAL,))


def verdict(answers, live):
    """{"veto": (rule, detail) | None, "answers": {qid: bad_p}, "escalate": [qid, ...]}."""
    if not answers:
        return {"veto": None, "answers": {}, "escalate": []}
    probs = {q: (round(p, 4) if (p := bad_p(q, a)) is not None else None) for q, a in answers.items()}
    veto = None
    for q, rule, th in VETO:
        a, p = answers.get(q), probs.get(q)
        if veto is None and a is not None and a.live and p is not None and p >= th:
            veto = (rule, f"{q} bad p={p:.2f} >= {th}")
    escalate = [q for q, a in answers.items()
                if live and a.live and q != "material" and a.probability is not None and a.probability < ESCALATE_BELOW]
    return {"veto": veto, "answers": probs, "escalate": escalate}


# ---- crypto trend book (fund/trendbook.py): buys only; sells, stops and kills never go to JEV ----
DATA_ERROR = judge.Question(
    "data_error", "noul",
    "Look at the signal packet in `order` (moving averages, realized volatility, last close, bar date, ETF bid "
    "and ask). Is there a data problem: a stale bar, a zero or crossed quote, a price that does not fit the "
    "other numbers, or a sign the ETF is halted?")
EVENT = judge.Question(
    "event", "choice",
    "Using only `headlines` about `asset`, what known event risk sits in the next five trading days?",
    {"none": "Nothing scheduled or breaking that matters for this asset.",
     "macro_scheduled": "A scheduled macro release such as FOMC or CPI.",
     "crypto_structural": "An exchange hack or failure, a stablecoin depeg, or regulatory action against crypto ETFs or venues.",
     "unknown": "The headlines are not enough to tell."})
ORDER_MISTAKE = judge.Question(
    "order_mistake", "noul",
    "Compare the order in `order` with the rule in `spec`. Is the order mechanically wrong: the wrong ETF for "
    "the asset, the wrong side, or a size that does not match target weight times NAV?")
TREND_QUESTIONS = (DATA_ERROR, EVENT, ORDER_MISTAKE)
TREND_VETO = (("data_error", "data_error", 0.35), ("event", "crypto_structural", 0.50),
              ("order_mistake", "order_mistake", 0.20))


def trend_bad_p(qid, a):
    if a is None:
        return None
    if qid == "event":
        return (a.distribution or {}).get("crypto_structural")
    return a.probability


def assess_trend(client, asset, order, headlines=(), spec=None):
    st = {"asset": asset, "order": order, "spec": spec or {},
          "headlines": [h for h in (clean(x) for x in list(headlines)[:20]) if h]}
    return judge.ask(client, st, TREND_QUESTIONS)


def trend_verdict(answers):
    probs = {q: (round(p, 4) if (p := trend_bad_p(q, a)) is not None else None) for q, a in (answers or {}).items()}
    veto = None
    for q, rule, th in TREND_VETO:
        a, p = (answers or {}).get(q), probs.get(q)
        if veto is None and a is not None and a.live and p is not None and p >= th:
            veto = (rule, f"{q} bad p={p:.2f} >= {th}")
    return {"veto": veto, "answers": probs}
