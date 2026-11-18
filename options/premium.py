"""Daily premium-selling screener: defined-risk credit spreads where implied volatility is rich. Rule:
research/premium-screener/RULE.md. Decision support only; nothing here places an order.

Inputs per ticker: a chain JSON (scripts/rh_chain_from_transcript.py shape: strike, type, expiry, oi, iv, delta, bid, ask)
for one 30-45 day expiry, daily closes (oldest first), and the next earnings date if any.
"""
import datetime as dt
import math

from . import mid

TARGET_DELTA = 0.20
DELTA_BAND = (0.15, 0.25)          # the short strike must land here, or the chain didn't reach far enough out
WIDTH_PCT = 0.025
MIN_IV_RV = 1.20
MIN_OI = 100                       # short leg (amended 2026-11-02: spread-first liquidity)
MAX_SPREAD_SHORT = 0.05
MAX_SPREAD_LONG = 0.10
MIN_CREDIT_FRAC = 0.25


def rv(closes, n=20):
    """Annualized close-to-close realized volatility over the last n returns."""
    if len(closes) < n + 1:
        return None
    r = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1)) * math.sqrt(252)


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def trend(closes):
    c, s50, s200 = closes[-1], sma(closes, 50), sma(closes, 200)
    if s50 is None or s200 is None:
        return "mixed", s50, s200
    if c > s50 > s200:
        return "up", s50, s200
    if c < s50 < s200:
        return "down", s50, s200
    return "mixed", s50, s200


def iv_atm(contracts, spot):
    """Average IV of the call and put at the strike nearest spot."""
    strikes = sorted({c["strike"] for c in contracts}, key=lambda k: abs(k - spot))
    for k in strikes[:3]:
        ivs = [c["iv"] for c in contracts if c["strike"] == k and c.get("iv")]
        if ivs:
            return sum(ivs) / len(ivs)
    return None


def _spread_ok(c, limit):
    b, a, m = c.get("bid"), c.get("ask"), mid(c)
    if m is None or b is None or b <= 0:
        return False
    return (a - b) <= (0.05 if m < 0.50 else limit * m)


def vertical(contracts, kind, spot):
    """Short at |delta| nearest TARGET_DELTA (out of the money), long ~WIDTH_PCT of spot further out. None if impossible."""
    side = [c for c in contracts if c["type"] == kind and c.get("delta") is not None]
    otm = [c for c in side if (c["strike"] < spot if kind == "put" else c["strike"] > spot)]
    if not otm:
        return None
    short = min(otm, key=lambda c: abs(abs(c["delta"]) - TARGET_DELTA))
    if not DELTA_BAND[0] <= abs(short["delta"]) <= DELTA_BAND[1]:
        return None
    goal = short["strike"] - WIDTH_PCT * spot if kind == "put" else short["strike"] + WIDTH_PCT * spot
    further = [c for c in side if (c["strike"] < short["strike"] if kind == "put" else c["strike"] > short["strike"])]
    if not further:
        return None
    long = min(further, key=lambda c: abs(c["strike"] - goal))
    width = abs(short["strike"] - long["strike"])
    credit = (short.get("bid") or 0) - (long.get("ask") or 0)          # natural fill: sell the bid, buy the ask
    return {"kind": kind, "short": short["strike"], "long": long["strike"], "short_delta": short["delta"],
            "short_oi": short.get("oi", 0), "short_bid": short.get("bid"), "short_ask": short.get("ask"),
            "long_bid": long.get("bid"), "long_ask": long.get("ask"), "width": width, "credit": round(credit, 2),
            "liquid": short.get("oi", 0) >= MIN_OI and _spread_ok(short, MAX_SPREAD_SHORT) and _spread_ok(long, MAX_SPREAD_LONG)}


def _setup(ticker, chain, closes, earnings, today, fields):
    """Shared start of both screens: one expiry (the earliest in the chain), its DTE, IV/RV and trend, and the earnings
    and volatility filters. Returns (out, contracts, fail); out["status"] is already "fail" if a shared filter failed."""
    today = today or dt.date.today().isoformat()
    spot = float(chain["spot"])
    expiry = min((c["expiry"] for c in chain["contracts"]), default=None)
    contracts = [c for c in chain["contracts"] if c["expiry"] == expiry]
    out = {"ticker": ticker, "spot": spot, "expiry": expiry, "dte": None, "iv30": None, "rv20": None, "iv_rv": None,
           "trend": None, "structure": "", "legs": "", "credit": None, **dict.fromkeys(fields), "pop": None,
           "score": None, "earnings": earnings or "", "status": "pass", "reason": ""}
    if expiry:
        out["dte"] = (dt.date.fromisoformat(expiry) - dt.date.fromisoformat(today)).days
    iv, r = iv_atm(contracts, spot), rv(closes)
    out.update(iv30=iv, rv20=r, trend=trend(closes)[0] if closes else "mixed", iv_rv=(iv / r) if iv and r else None)

    def fail(why):
        out.update(status="fail", reason=why)
        return out

    if earnings and expiry and today <= earnings <= expiry:
        fail(f"earnings {earnings} before expiry")
    elif out["iv_rv"] is None:
        fail("IV or realized vol unavailable")
    return out, contracts, fail


def screen(ticker, chain, closes, earnings=None, today=None):
    """One ticker → candidate dict with metrics, structure, legs, pass/fail and the first failed filter."""
    out, contracts, fail = _setup(ticker, chain, closes, earnings, today, ("width", "max_loss", "return_on_risk"))
    if out["status"] == "fail":
        return out
    t, spot = out["trend"], out["spot"]
    kinds = ["put"] if t == "up" else ["call"] if t == "down" else ["put", "call"]
    legs = [vertical(contracts, k, spot) for k in kinds]
    if any(v is None for v in legs):
        return fail("no 0.15-0.25 delta short strike in the chain")
    credit = sum(v["credit"] for v in legs)
    width = max(v["width"] for v in legs)                      # an iron condor risks one side at a time
    max_loss = width - credit
    out.update(structure={"up": "put credit spread", "down": "call credit spread"}.get(t, "iron condor"),
               legs=" / ".join(f"{'P' if v['kind'] == 'put' else 'C'} -{v['short']:g} +{v['long']:g} (Δ{abs(v['short_delta']):.2f})"
                               for v in legs),
               credit=round(credit, 2), width=width, max_loss=round(max_loss, 2),
               return_on_risk=round(credit / max_loss, 3) if max_loss > 0 else None,
               pop=round(1 - sum(abs(v["short_delta"]) for v in legs), 3))
    if out["iv_rv"] < MIN_IV_RV:
        return fail(f"IV/RV {out['iv_rv']:.2f} < {MIN_IV_RV}")
    if not all(v["liquid"] for v in legs):
        return fail("short strike open interest or bid/ask too thin")
    if credit < MIN_CREDIT_FRAC * width:
        return fail(f"credit {credit:.2f} < {MIN_CREDIT_FRAC:.0%} of width {width:g}")
    out["score"] = round(out["iv_rv"] * out["return_on_risk"], 3)
    return out


def rank(results, top=5):
    passed = sorted([r for r in results if r["status"] == "pass"], key=lambda r: -r["score"])
    for i, r in enumerate(passed):
        r["rank"] = i + 1 if i < top else None
    return passed + [r for r in results if r["status"] != "pass"]


def screen_put(ticker, chain, closes, earnings=None, today=None):
    """Single-leg cash-secured put (RULE.md amendment 2). Same metrics as screen(), plus cash and annualized return."""
    out, contracts, fail = _setup(ticker, chain, closes, earnings, today,
                                  ("strike", "cash_needed", "breakeven", "return_on_cash", "annualized"))
    if out["status"] == "fail":
        return out
    puts = [c for c in contracts if c["type"] == "put" and c.get("delta") is not None and c["strike"] < out["spot"]]
    if not puts:
        return fail("no out-of-the-money puts in the chain")
    short = min(puts, key=lambda c: abs(abs(c["delta"]) - TARGET_DELTA))
    if not DELTA_BAND[0] <= abs(short["delta"]) <= DELTA_BAND[1]:
        return fail("no 0.15-0.25 delta put in the chain")
    k, credit = short["strike"], short.get("bid") or 0.0
    roc = credit / k if k else 0.0
    out.update(structure="cash-secured put", legs=f"P -{k:g} (Δ{abs(short['delta']):.2f})", strike=k,
               credit=round(credit, 2), cash_needed=round(k * 100), breakeven=round(k - credit, 2),
               return_on_cash=round(roc, 4), annualized=round(roc * 365 / out["dte"], 4) if out["dte"] else None,
               pop=round(1 - abs(short["delta"]), 3))
    if out["trend"] == "down":
        return fail("downtrend: no puts sold into a falling stock")
    if out["iv_rv"] < MIN_IV_RV:
        return fail(f"IV/RV {out['iv_rv']:.2f} < {MIN_IV_RV}")
    if not (short.get("oi", 0) >= MIN_OI and _spread_ok(short, MAX_SPREAD_SHORT)):
        return fail("put open interest or bid/ask too thin")      # also covers a missing bid
    out["score"] = round(out["iv_rv"] * (out["annualized"] or 0), 4)
    return out


def open_picks(rows):
    """Open picks in a picks journal: pick lines (they have a ticker) without a later {"close_of": id} line."""
    closed = {r["close_of"] for r in rows if "close_of" in r}
    return [r for r in rows if "close_of" not in r and r["id"] not in closed]


def pick_expiry(expiries, today, dte=(30, 45), target=38):
    """The rule's expiry from those available: the one closest to `target` days out within 30-45 (the earlier on a
    tie), else the earliest one."""
    t = dt.date.fromisoformat(today)
    days = {e: (dt.date.fromisoformat(e) - t).days for e in expiries}
    ok = [e for e in sorted(expiries) if dte[0] <= days[e] <= dte[1]]
    return min(ok, key=lambda e: (abs(days[e] - target), e)) if ok else min(expiries)
