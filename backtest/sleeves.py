"""Monthly net-return streams ("sleeves") for the combination test (backtest/portfolio.py).

Every stream is {"YYYY-MM": return}, measured from the prior month's close to this month's close.

Data comes from backtest/data/long/*.json. These are TradingView and Alpha Vantage series, transcribed
through the desk's connectors because the sandbox can't reach market-data hosts. Each file records its
source and fetch date:
    {"name", "symbol", "interval", "source", "fetched", "bars": [[unix_t, close], ...]}
    TBILL_M: {"rows": [["YYYY-MM-DD", pct], ...]}

Sleeves
  SPY        buy and hold, price only (TradingView carries no dividends: ~1.5-2%/yr is left out; noted in results)
  PUT/BXM/CNDR  Cboe benchmark indices (cash-secured puts / buy-write / iron condor, the spread-book proxy).
             The indices carry no trading costs, so the "net" run deducts OPTION_DRAG a year.
  TREND      the desk's trend-etf-v1 rules, replayed on weekly crypto closes (see trend_weekly)
  TBILL      3-month T-bill, the cash every sleeve's idle money earns
"""
import json
import math
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
LONG = ROOT / "backtest" / "data" / "long"

OPTION_DRAG = 0.010        # %/yr implementation cost for the option-index sleeves in the net run
ETF_COST = 0.0008          # per side: ~3 bp ETF spread + 5 bp slippage when trend-etf-v1 trades IBIT/ETHA/BSOL

# trend-etf-v1 mapped from daily bars to weekly bars. This is an approximation and is documented as one.
# SMA20/100 days is about 4/20 weeks; the RV30-day window is about 6 weeks; the 2-close confirmation and 80% trail are unchanged.
T_FAST, T_SLOW, T_RV, T_TARGET, T_TRAIL = 4, 20, 6, 0.30, 0.80
T_SLEEVES = {"BTC": 0.50, "ETH": 0.30, "SOL": 0.20}


def month_of(t):
    return datetime.fromtimestamp(int(t), timezone.utc).strftime("%Y-%m")


def load(name, root=LONG):
    return json.loads((root / f"{name}.json").read_text(encoding="utf-8"))


def monthly_closes(bars):
    """[[t, close]] (any bar size) -> {"YYYY-MM": last close in that month}."""
    out = {}
    for t, c in sorted(bars):
        if c and c > 0:
            out[month_of(t)] = float(c)
    return out


def returns(closes):
    """{"YYYY-MM": close} -> {"YYYY-MM": close/prior - 1}; the first month has no return."""
    ks = sorted(closes)
    return {k: closes[k] / closes[p] - 1 for p, k in zip(ks, ks[1:])}


def tbill(rows):
    """[["YYYY-MM-DD", annual pct]] -> {"YYYY-MM": monthly return}. Each month uses the prior month's yield (known in advance)."""
    by = {}
    for d, pct in sorted(rows):
        by[d[:7]] = float(pct) / 100
    ks = sorted(by)
    return {k: by[p] / 12 for p, k in zip(ks, ks[1:])}


def _sma(xs, n, end):
    return sum(xs[end - n:end]) / n


def trend_weekly(weekly, tb_month, cost=ETF_COST):
    """Replay trend-etf-v1 on weekly closes. weekly = {asset: [[t, close], ...]}.

    A signal read at week i's close is traded at that close and earns week i+1's return. That matches the live
    book, which trades at the next US close after the signal bar. Idle money earns the T-bill.
    Returns {"YYYY-MM": monthly net return}, from the first week any asset has enough history.
    """
    series = {a: {int(t): float(c) for t, c in weekly.get(a, []) if c and c > 0} for a in T_SLEEVES}
    weeks = sorted(set().union(*[s.keys() for s in series.values()]))
    state = {a: {"on": False, "peak": None} for a in T_SLEEVES}
    hist = {a: [] for a in T_SLEEVES}
    w_prev = {a: 0.0 for a in T_SLEEVES}
    monthly, started = {}, False
    for i, t in enumerate(weeks[:-1]):
        t_next = weeks[i + 1]
        w = {}
        for a, sleeve in T_SLEEVES.items():
            c = series[a].get(t)
            if c is None:
                w[a] = 0.0
                continue
            h = hist[a]
            h.append(c)
            if len(h) < T_SLOW + 2:
                w[a] = 0.0
                continue
            n = len(h)
            f1, s1, f0, s0 = _sma(h, T_FAST, n), _sma(h, T_SLOW, n), _sma(h, T_FAST, n - 1), _sma(h, T_SLOW, n - 1)
            sig = state[a]
            if not sig["on"] and f1 > s1 and f0 > s0:
                sig.update(on=True, peak=c)
            elif sig["on"]:
                sig["peak"] = max(sig["peak"], c)
                if (f1 < s1 and f0 < s0) or c < T_TRAIL * sig["peak"]:
                    sig.update(on=False, peak=None)
            lr = [math.log(h[j] / h[j - 1]) for j in range(n - T_RV, n)]
            m = sum(lr) / len(lr)
            rv = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(52)
            w[a] = sleeve * min(1.0, T_TARGET / rv) if sig["on"] and rv > 0 else 0.0
            started = True
        if not started:
            continue
        # The live book trades only when a target crosses zero or moves more than 20% from what is held.
        for a in w:
            if w_prev[a] and w[a] and abs(w[a] - w_prev[a]) <= 0.20 * w_prev[a]:
                w[a] = w_prev[a]
        turn = sum(abs(w[a] - w_prev[a]) for a in w)
        wk_cash = tb_month.get(month_of(t_next), 0.0) * 12 / 52
        r = sum(w[a] * (series[a][t_next] / series[a][t] - 1) for a in w if w[a] and t_next in series[a])
        r += (1 - sum(w.values())) * wk_cash - turn * cost
        mk = month_of(t_next)
        monthly[mk] = (1 + monthly.get(mk, 0.0)) * (1 + r) - 1
        w_prev = w
    # Drop the first month, which is partial.
    ks = sorted(monthly)
    return {k: monthly[k] for k in ks[1:]}


def build(root=LONG, net=True):
    """Every sleeve plus benchmarks: {"sleeves": {name: {month: r}}, "tbill": {...}, "bench": {...}, "sources": [...]}."""
    tb = tbill(load("TBILL_M", root)["rows"])
    sleeves, bench, sources = {}, {}, []
    for name in ("SPY", "PUT", "BXM", "CNDR"):
        d = load(f"{name}_M", root)
        sources.append({k: d.get(k) for k in ("name", "symbol", "interval", "source", "fetched")})
        r = returns(monthly_closes(d["bars"]))
        if net and name != "SPY":
            r = {k: v - OPTION_DRAG / 12 for k, v in r.items()}
        sleeves[name] = r
    wk = {}
    for a in T_SLEEVES:
        d = load(f"{a}_W", root)
        sources.append({k: d.get(k) for k in ("name", "symbol", "interval", "source", "fetched")})
        wk[a] = d["bars"]
    sleeves["TREND"] = trend_weekly(wk, tb, cost=ETF_COST if net else 0.0)
    d = load("BTC_M", root)
    bench["BTC"] = returns(monthly_closes(d["bars"]))
    bench["SPY"] = sleeves["SPY"]
    bench["60/40 SPY/T-bill"] = {k: 0.6 * v + 0.4 * tb[k] for k, v in sleeves["SPY"].items() if k in tb}
    return {"sleeves": sleeves, "tbill": tb, "bench": bench, "sources": sources}
