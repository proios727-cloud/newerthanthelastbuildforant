"""Per-strike and per-expiry options positioning from a chain snapshot: net GEX, net VEX, open interest and premium.

Input is the chain JSON that scripts/rh_chain_from_transcript.py writes (the gex_map.py shape, plus bid/ask). Conventions
match gex_map.py so the totals reconcile with the Heat Seeker map:
- Dealers are assumed long calls and short puts: calls add, puts subtract. This is the usual naive assumption, not a
  measurement of real dealer books.
- GEX at a strike = gamma × OI × 100 × spot² × 1%: dollars of delta dealers must trade per 1% move. The broker's gamma is
  used when given; otherwise Black-Scholes gamma.
- VEX = vanna × OI × 100 × spot × 1%: dollars of delta per 1 vol point.
- Premium = volume × mid × 100. Net premium = call premium − put premium. **Direction-blind:** the chain doesn't say whether
  a trade was bought or sold, so this is where money traded, not which way it leans.
"""
import datetime as dt
import math
import re
from collections import defaultdict

from . import _pdf, mid as _mid

RATE = 0.04
MIN_T = 1.0 / (365.0 * 24.0 * 4.0)          # ~15 minutes, as in gex_map.py


def _d1d2(S, K, T, sigma, r=RATE):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None, None
    v = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / v
    return d1, d1 - v


def bs_gamma(S, K, T, sigma, r=RATE):
    d1, _ = _d1d2(S, K, T, sigma, r)
    return 0.0 if d1 is None else _pdf(d1) / (S * sigma * math.sqrt(T))


def bs_vanna(S, K, T, sigma, r=RATE):
    d1, d2 = _d1d2(S, K, T, sigma, r)
    return 0.0 if d1 is None else -_pdf(d1) * d2 / sigma


def parse_time(ts):
    """ISO time with a Z or offset and up to nanosecond precision -> aware datetime (UTC if no zone)."""
    ts = ts.replace("Z", "+00:00")
    m = re.match(r"(.*?\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", ts)
    if m:
        ts = m.group(1) + ((m.group(2) or "")[:7]) + m.group(3)
    t = dt.datetime.fromisoformat(ts)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def years_to_expiry(expiry, asof):
    """Year fraction to 16:00 ET (20:00 UTC) on the expiry date, floored at MIN_T."""
    exp = dt.datetime.fromisoformat(expiry).replace(hour=20, tzinfo=dt.timezone.utc)
    return max((exp - parse_time(asof)).total_seconds() / (365.0 * 86400.0), MIN_T)


def strike_table(chain):
    """Rows per (expiry, strike): call/put OI, volume, premium, and net GEX / VEX / premium. Plus an 'all' expiry roll-up."""
    spot, asof = float(chain["spot"]), chain["asof"]
    rows = defaultdict(lambda: defaultdict(float))
    for c in chain["contracts"]:
        K, kind, exp = float(c["strike"]), c["type"], c["expiry"]
        oi, vol, iv = float(c.get("oi") or 0), float(c.get("volume") or 0), float(c.get("iv") or 0)
        T = years_to_expiry(exp, asof)
        g = c.get("gamma")
        g = float(g) if g is not None else bs_gamma(spot, K, T, iv)
        sign = 1.0 if kind == "call" else -1.0
        mid = _mid(c)
        prem = vol * mid * 100 if mid is not None else 0.0
        for key in ((exp, K), ("all", K)):
            r = rows[key]
            r[f"{kind}_oi"] += oi
            r[f"{kind}_volume"] += vol
            r[f"{kind}_premium"] += prem
            r["net_gex"] += sign * g * oi * 100 * spot * spot * 0.01
            r["net_vex"] += sign * bs_vanna(spot, K, T, iv) * oi * 100 * spot * 0.01
    out = []
    for (exp, K), r in sorted(rows.items(), key=lambda kv: (kv[0][0] != "all", kv[0][0], kv[0][1])):
        out.append({"expiry": exp, "strike": K,
                    "call_oi": int(r["call_oi"]), "put_oi": int(r["put_oi"]),
                    "call_volume": int(r["call_volume"]), "put_volume": int(r["put_volume"]),
                    "call_premium": round(r["call_premium"]), "put_premium": round(r["put_premium"]),
                    "net_premium": round(r["call_premium"] - r["put_premium"]),
                    "net_gex": round(r["net_gex"]), "net_vex": round(r["net_vex"])})
    return out


def expiry_table(strikes):
    """Totals per expiry (and 'all') from strike_table rows: net GEX/VEX, premium, put/call ratios."""
    acc = defaultdict(lambda: defaultdict(float))
    for r in strikes:
        a = acc[r["expiry"]]
        for k in ("call_oi", "put_oi", "call_volume", "put_volume", "call_premium", "put_premium", "net_gex", "net_vex"):
            a[k] += r[k]
    out = []
    for exp, a in sorted(acc.items(), key=lambda kv: (kv[0] == "all", kv[0])):
        out.append({"expiry": exp, "net_gex": round(a["net_gex"]), "net_vex": round(a["net_vex"]),
                    "call_premium": round(a["call_premium"]), "put_premium": round(a["put_premium"]),
                    "net_premium": round(a["call_premium"] - a["put_premium"]),
                    "put_call_volume": round(a["put_volume"] / a["call_volume"], 3) if a["call_volume"] else None,
                    "put_call_oi": round(a["put_oi"] / a["call_oi"], 3) if a["call_oi"] else None})
    return out
