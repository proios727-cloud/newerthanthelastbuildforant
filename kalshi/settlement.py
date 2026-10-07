"""Settlement check (TypeSafe): verify a market's rules text before the desk quotes it.

The desk's fair value comes from the CF Benchmarks real-time index. If a market settles on anything
else, or over a different window, the fair value is wrong and the lock math is meaningless — so every
new market's rules are judged once and cached by ticker. Only a live, confident yes allows quoting.
"""
import judge

VERIFIED_MIN_P = 0.90

QUESTION = judge.Question(
    "cfb_settlement", "noul",
    "Do the rules in `market.rules` state that this market settles on the CF Benchmarks real-time index "
    "for `market.asset`, comparing the sixty-second average of that index before the end of the single "
    "`market.window_min`-minute window with the sixty-second average before its start? Answer no if another price source, an average over a different period, "
    "or a discretionary settlement is described.")


def verify(client, market, cache):
    t = market["ticker"]
    if t not in cache:
        cache[t] = judge.ask(client, {"market": market}, [QUESTION])["cfb_settlement"]
    a = cache[t]
    return bool(a.value) and a.confident(VERIFIED_MIN_P)
