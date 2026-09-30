"""Does the JEV veto earn its place? A pre-registered test over the put and spread books.

Every sale the books consider after the earnings gate gets a JEV verdict. Sales JEV lets through are
traded; sales it vetoes become ghosts: the same contract tracked through the same exits with no cash.
This module compares the two groups. The bar was fixed on 2026-09-29, before any live verdict existed,
and the constants below must not move once data arrives (change them only with a new REGISTERED date
and a note in the README explaining why).

Outcome measure: P&L per dollar of credit collected (+0.5 at the target, about -(stop - 1) at a stop),
so the $100k put book and the $500 spread book pool on one scale.

Verdicts:
  insufficient  fewer than MIN_TAKEN live-judged trades or MIN_GHOSTS closed ghosts
  unreliable    judge errors are more than MAX_ERROR_RATE of judged decisions
  keep          vetoed sales did at least MIN_EDGE worse per $ credit than the sales taken
  drop          vetoed sales did as well as or better than the sales taken, or still inconclusive
                after 2 x MIN_GHOSTS ghosts (a veto that can't show its value just costs trades)
  inconclusive  otherwise: keep collecting
"""
REGISTERED = "2026-09-29"
MIN_TAKEN, MIN_GHOSTS = 20, 8
MIN_EDGE = 0.25
MAX_ERROR_RATE = 0.10


def _ror(t):
    return t["pnl"] / t["credit"] if t.get("credit") else 0.0


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def evaluate(*books):
    taken = [t for st in books for t in st.get("closed", []) if t.get("jev_mode") == "live"]
    ghosts = [t for st in books for t in st.get("ghost_closed", [])]
    open_judged = sum(1 for st in books for p in st.get("positions", {}).values() if p.get("jev_mode"))
    open_ghosts = sum(len(st.get("ghosts", {})) for st in books)
    errors = sum(1 for st in books for x in st.get("log", [])
                 if x.get("kind", "").endswith("_skip") and x.get("jev_mode") == "error")
    judged = len(taken) + len(ghosts) + open_judged + open_ghosts + errors + \
        sum(1 for st in books for t in st.get("closed", []) if t.get("jev_mode") in ("stub", "error"))
    modes = sorted({t.get("jev_mode") for st in books for t in st.get("closed", []) + list(st.get("positions", {}).values())
                    if t.get("jev_mode")})

    t_mean, g_mean = _mean([_ror(t) for t in taken]), _mean([_ror(t) for t in ghosts])
    err_rate = round(errors / judged, 3) if judged else 0.0
    if judged and err_rate > MAX_ERROR_RATE:
        verdict = "unreliable"
    elif len(taken) < MIN_TAKEN or len(ghosts) < MIN_GHOSTS:
        verdict = "insufficient"
    elif g_mean <= t_mean - MIN_EDGE:
        verdict = "keep"
    elif g_mean >= t_mean or len(ghosts) >= 2 * MIN_GHOSTS:
        verdict = "drop"
    else:
        verdict = "inconclusive"

    def p_mean(ts, lose):
        return _mean([t["jev_p"] for t in ts if t.get("jev_p") is not None and (t["pnl"] < 0) == lose])

    return {"verdict": verdict, "registered": REGISTERED,
            "bar": {"min_taken": MIN_TAKEN, "min_ghosts": MIN_GHOSTS, "min_edge_per_credit": MIN_EDGE,
                    "max_error_rate": MAX_ERROR_RATE},
            "taken_live": len(taken), "ghosts_closed": len(ghosts), "ghosts_open": open_ghosts,
            "taken_pnl_per_credit": t_mean, "vetoed_pnl_per_credit": g_mean,
            "edge": round(t_mean - g_mean, 4) if t_mean is not None and g_mean is not None else None,
            "judge_errors": errors, "error_rate": err_rate, "modes_seen": modes,
            # report only: does P(material) run higher on the trades that lost?
            "mean_p_losers": p_mean(taken + ghosts, True), "mean_p_winners": p_mean(taken + ghosts, False)}
