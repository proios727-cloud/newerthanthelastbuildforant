"""The rotation rule over two decades of weekly bars (Alpha Vantage weekly adjusted, free tier).

Daily history before 2023 is a premium feed; weekly adjusted bars are free and go back to 1999 (GLD 2004, TLT 2002,
XLRE 2015, XLC 2018). On weekly bars the live rule becomes: rank by 12-week return (≈ 60 sessions), decide at the close
of the first weekly bar of each month, fill at the next weekly open. That decides up to four sessions later than the
daily rule, so it tests whether the idea holds across regimes, not the exact live numbers. Prices are dividend- and
split-adjusted (total return), which the daily files are not.
"""
import math
import pathlib
from datetime import date

from . import load_csv
from .forward import replay_rotation

REGIMES = (("2008 crash", "2007-10-01", "2009-03-31"), ("2011 debt scare", "2011-05-01", "2011-10-31"),
           ("2015–16 slump", "2015-07-01", "2016-02-29"), ("2018 Q4", "2018-10-01", "2018-12-31"),
           ("2020 Covid crash", "2020-02-01", "2020-04-30"), ("2022 bear", "2022-01-01", "2022-10-31"))
VARIANTS = (("Adopted rule", {}), ("Hysteresis: top 4", {"buffer": 1}),
            ("Basket trend filter ≈150 days", {"trend": 30}), ("Basket trend filter ≈200 days", {"trend": 40}))
BASKETS = {"11 funds, Nov 2004 →": ("GLD", "TLT", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"),
           "13 funds, Jul 2018 →": None}


def load(folder, symbols=None):
    files = sorted(pathlib.Path(folder).glob("*.csv"))
    return {f.stem.upper(): load_csv(f) for f in files if symbols is None or f.stem.upper() in symbols}


def _drawdown(periods, key):
    eq = peak = 1.0
    worst = 0.0
    for p in periods:
        eq *= 1 + p[key]
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def summarize(periods, cost_bps=(3, 20), top=3):
    """CAGR over the calendar span, worst month-end drawdown, months ahead, turnover, and the turnover cost drag at each
    round-trip cost per side (fee + slippage, bp): each swap sells and buys 1/top of the book."""
    done = [p for p in periods if p["complete"]]
    yrs = (date.fromisoformat(periods[-1]["to"]) - date.fromisoformat(periods[0]["from"])).days / 365.25
    g = lambda k: math.prod(1 + p[k] for p in periods) ** (1 / yrs) - 1
    swaps = sum(len(set(b["picks"]) - set(a["picks"])) for a, b in zip(periods, periods[1:])) / max(1, len(periods) - 1)
    rule = g("rule")
    return {"from": periods[0]["from"], "to": periods[-1]["to"], "years": round(yrs, 1), "cagr": round(rule, 4),
            "basket_cagr": round(g("basket"), 4), "drawdown": round(_drawdown(periods, "rule"), 4),
            "basket_drawdown": round(_drawdown(periods, "basket"), 4), "months_ahead": sum(p["excess"] > 0 for p in done),
            "months": len(done), "swaps_per_month": round(swaps, 2), "cash_months": sum(not p["picks"] for p in periods),
            "net_cagr": {f"{c}bp": round(rule - swaps * 12 * 2 / top * c / 1e4, 4) for c in cost_bps}}


def regimes(periods, windows=REGIMES):
    """Rule vs basket compounded over the decision periods that start inside each stress window."""
    out = []
    for name, a, b in windows:
        ps = [p for p in periods if a <= p["from"] <= b]
        if ps:
            out.append({"regime": name, "rule": round(math.prod(1 + p["rule"] for p in ps) - 1, 4),
                        "basket": round(math.prod(1 + p["basket"] for p in ps) - 1, 4), "months": len(ps)})
    return out


def by_year(periods):
    years = {}
    for p in periods:
        r, b = years.setdefault(p["from"][:4], [1.0, 1.0])
        years[p["from"][:4]] = [r * (1 + p["rule"]), b * (1 + p["basket"])]
    return [{"year": y, "rule": round(r - 1, 4), "basket": round(b - 1, 4)} for y, (r, b) in sorted(years.items())]


def run(folder="chart/data/weekly", lookback=12, top=3):
    out = {"lookback_weeks": lookback, "top": top, "baskets": []}
    for name, syms in BASKETS.items():
        bars = load(folder, syms)
        res = {"basket": name, "funds": sorted(bars), "variants": []}
        for label, extra in VARIANTS:
            ps = replay_rotation(bars, lookback=lookback, top=top, **extra)["periods"]
            row = {"label": label, "params": extra, **summarize(ps, top=top)}
            if not extra:
                row["regimes"], row["years"] = regimes(ps), by_year(ps)
            res["variants"].append(row)
        out["baskets"].append(res)
    return out
