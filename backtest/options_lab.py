"""O2 single-leg options lab: long calls, long puts and short (cash-secured) puts on the desk's equity
universe, driven by the shadow-book signals. Research only; nothing here places orders.

Pricing without historical chains (none are free for this universe):
  ATM IV   SPY = 0.85·VIX. Others = RV20(symbol) · k, where k = 0.85·VIX / RV20(SPY) is the market's
           implied/realized ratio that day (clipped to [0.7, 2.5]). Calibrated to live Robinhood quotes
           at the 2026-09-28 close: SPY 30d ATM 13.7% with VIX 16.07; NVDA 30d ATM 31.6%.
  Smile    iv(K) = atm · max(0.7, 1 + s·z), z = ln(S/K)/(atm·√T'), T' ≥ 7 days, capped at 3·atm.
           s = 0.25 for index ETFs (SPY 730P at 17.7%), 0.10 for single names (NVDA 210P at 34.6%).
  Costs    half the bid/ask per side, as % of premium: 1% ETFs, 2% single names (live: SPY 0.7–0.9%,
           NVDA 2.4–4.7% full spread), plus $0.03 per contract.
Rules: causal (signal at close t−1, trade at close t); one position per symbol; continuous contracts.

  python backtest/options_lab.py     # writes backtest/options_results.json and prints the summary
"""
import json
import math
import pathlib
import sys
from datetime import date, timedelta
from itertools import product

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backtest"))

import run as bt  # noqa: E402
from fund import shadow  # noqa: E402
from options import greeks  # noqa: E402

EQ = ["SPY", "QQQ", "IWM", "NVDA", "AMD", "AAPL", "MSFT", "TSLA"]
ETF = {"SPY", "QQQ", "IWM"}
R = 0.04
DTE = 30
IV_TO_VIX = 0.85
SKEW = {"etf": 0.25, "stock": 0.10}
HALF_SPREAD = {"etf": 0.01, "stock": 0.02}
FEE = 0.03 / 100          # $ per share-equivalent
LONG_RISK = 0.01          # premium per long trade, share of NAV
LONG_CAP = 0.10           # total premium at risk
PUT_NOTIONAL = 0.05       # strike notional per short put, share of NAV
PUT_CAP = 1.00            # cash-secured: total strike notional <= NAV


# ---- data -------------------------------------------------------------------
def load():
    series = bt.load_series()
    days = [d for d, _ in series["SPY"]]
    px = {s: [c for _, c in series[s]] for s in EQ}
    vix_days = sorted(bt.nyse_days("2025-07-23", 298) + ["2025-09-01", "2025-11-27"])
    vix_raw = dict(zip(vix_days, [float(x) for x in (ROOT / "backtest/data/VIX.txt").read_text().split()]))
    assert vix_days[-1] == days[-1] and vix_raw["2025-09-01"] == 16.12 and vix_raw["2025-11-27"] == 17.21
    vix, last = [], None
    for d in days:  # VIX starts two sessions after SPY; carry the first value back
        last = vix_raw.get(d, last)
        vix.append(last)
    first = next(v for v in vix if v)
    vix = [v or first for v in vix]
    return days, px, vix


def rv20(c, i):
    if i < 21:
        return None
    r = [math.log(c[j] / c[j - 1]) for j in range(i - 19, i + 1)]
    m = sum(r) / 20
    return math.sqrt(sum((x - m) ** 2 for x in r) / 19 * 252)


class Vol:
    def __init__(self, px, vix, scale=1.0):
        self.px, self.vix, self.scale = px, vix, scale
        self.cache = {}

    def atm(self, s, i):
        key = (s, i)
        if key not in self.cache:
            spy_atm = IV_TO_VIX * self.vix[i] / 100
            if s == "SPY":
                v = spy_atm
            else:
                rs, rm = rv20(self.px[s], i), rv20(self.px["SPY"], i)
                k = min(2.5, max(0.7, spy_atm / rm)) if rm else 1.3
                v = (rs or spy_atm) * k
            self.cache[key] = v * self.scale
        return self.cache[key]

    def iv(self, s, i, S, K, T):
        a = self.atm(s, i)
        z = math.log(S / K) / (a * math.sqrt(max(T, 7 / 365)))
        return min(3 * a, a * max(0.7, 1 + SKEW["etf" if s in ETF else "stock"] * z))


def price(vol, s, i, S, K, T, kind):
    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    return greeks(S, K, T, vol.iv(s, i, S, K, T), kind, r=R).price


def strike_for_delta(vol, s, i, S, T, kind, target):
    """Bisection on K for |delta| = target (0.5 ≈ ATM)."""
    lo, hi = S * 0.5, S * 1.5
    for _ in range(60):
        K = (lo + hi) / 2
        d = abs(greeks(S, K, T, vol.iv(s, i, S, K, T), kind, r=R).delta)
        # call delta falls as K rises; |put delta| rises as K rises
        if (d > target) == (kind == "call"):
            lo = K
        else:
            hi = K
    return round(K, 2)


# ---- signals (causal: evaluated on closes up to t-1) ---------------------------
def bullish(c):
    return bool(shadow.signals(c))


def bearish(c):
    if len(c) < shadow.MIN_BARS:
        return False
    px, s20, s50 = c[-1], shadow.sma(c, 20), shadow.sma(c, 50)
    return px < min(c[-21:-1]) or (px < s20 < s50 and px / c[-21] - 1 < 0)


# ---- engine -------------------------------------------------------------------
def simulate(days, px, vix, fam, p, start=0, end=None, nav0=100_000.0, cost_x=1.0, iv_scale=1.0):
    """fam: long_call | long_put | long_both | short_put | always_long_call | always_short_put.
    p: {delta, tp, stop, hold, gate}. Returns (nav series [(date, nav)], closed trades)."""
    vol = Vol(px, vix, iv_scale)
    end = len(days) - 1 if end is None else end
    cash, pos, trades, navs = nav0, {}, [], []

    def cost(s, prem, qty):
        return qty * (prem * HALF_SPREAD["etf" if s in ETF else "stock"] * cost_x + FEE)

    def mark(i):
        v = cash
        for s, q in pos.items():
            T = (q["exp"] - date.fromisoformat(days[i])).days / 365
            v += q["side"] * q["qty"] * price(vol, s, i, px[s][i], q["K"], T, q["kind"])
        return v

    def close(s, i, why):
        nonlocal cash
        q = pos.pop(s)
        T = (q["exp"] - date.fromisoformat(days[i])).days / 365
        pr = price(vol, s, i, px[s][i], q["K"], T, q["kind"])
        c = 0.0 if T <= 0 else cost(s, pr, q["qty"])  # expiry settles at intrinsic, no spread
        cash += q["side"] * q["qty"] * pr - c
        pnl = q["side"] * q["qty"] * (pr - q["px"]) - c - q["cost"]
        trades.append({"sym": s, "kind": q["kind"], "side": q["side"], "entry": days[q["i"]], "exit": days[i],
                       "why": why, "pnl": round(pnl, 2), "premium": round(q["qty"] * q["px"], 2)})

    def open_(s, i, kind, side, delta):
        nonlocal cash
        d = date.fromisoformat(days[i])
        exp = d + timedelta(days=DTE)
        T = DTE / 365
        S = px[s][i]
        K = strike_for_delta(vol, s, i, S, T, kind, delta)
        pr = price(vol, s, i, S, K, T, kind)
        if pr <= 0.01:
            return
        nav = mark(i)
        if side > 0:
            at_risk = sum(q["qty"] * q["px"] for q in pos.values() if q["side"] > 0)
            budget = min(LONG_RISK * nav, LONG_CAP * nav - at_risk)
            qty = budget / pr
        else:
            notional = sum(q["qty"] * q["K"] for q in pos.values() if q["side"] < 0)
            room = min(PUT_NOTIONAL * nav, PUT_CAP * nav - notional)
            qty = room / K
        if qty <= 0:
            return
        c = cost(s, pr, qty)
        cash -= side * qty * pr + c
        pos[s] = {"kind": kind, "side": side, "K": K, "exp": exp, "qty": qty, "px": pr, "cost": c, "i": i}

    for i in range(start, end + 1):
        today = date.fromisoformat(days[i])
        # 1. exits
        for s in list(pos):
            q = pos[s]
            T = (q["exp"] - today).days / 365
            pr = price(vol, s, i, px[s][i], q["K"], T, q["kind"])
            ret = (pr / q["px"] - 1) * q["side"]  # long: gain %; short: + when premium decays
            held = i - q["i"]
            if T <= 0:
                close(s, i, "expiry")
            elif q["side"] > 0 and ret >= p["tp"]:
                close(s, i, "target")
            elif q["side"] > 0 and ret <= -p["stop"]:
                close(s, i, "stop")
            elif q["side"] < 0 and ret >= p["tp"]:            # captured tp share of credit
                close(s, i, "target")
            elif q["side"] < 0 and pr >= (1 + p["stop"]) * q["px"]:
                close(s, i, "stop")
            elif held >= p["hold"] or T < 7 / 365:
                close(s, i, "time")
        # 2. entries on yesterday's signal
        if i > start and i < end:
            spy_rv = rv20(px["SPY"], i - 1)
            vrp_ok = spy_rv is not None and IV_TO_VIX * vix[i - 1] / 100 > spy_rv
            for s in EQ:
                if s in pos:
                    continue
                c = px[s][: i]  # closes through t-1
                if fam.startswith("always"):
                    if s != "SPY":
                        continue
                    kind, side = ("call", 1) if fam == "always_long_call" else ("put", -1)
                    open_(s, i, kind, side, p["delta"])
                    continue
                bull, bear = bullish(c), bearish(c)
                if fam in ("long_call", "long_both") and bull:
                    open_(s, i, "call", 1, p["delta"])
                elif fam in ("long_put", "long_both") and bear and not bull:
                    open_(s, i, "put", 1, p["delta"])
                elif fam == "short_put" and bull and (not p.get("gate") or vrp_ok):
                    open_(s, i, "put", -1, p["delta"])
        navs.append((days[i], mark(i)))
    for s in list(pos):  # window end: close at mark (costed)
        close(s, end, "window_end")
    if navs:
        navs[-1] = (days[end], cash)
    return navs, trades


# ---- metrics ------------------------------------------------------------------
def metrics(navs, trades):
    v = [n for _, n in navs]
    rets = [b / a - 1 for a, b in zip(v, v[1:])]
    peak, mdd = v[0], 0.0
    for x in v:
        peak = max(peak, x)
        mdd = max(mdd, 1 - x / peak)
    days = (date.fromisoformat(navs[-1][0]) - date.fromisoformat(navs[0][0])).days or 1
    tot = v[-1] / v[0] - 1
    cagr = (1 + tot) ** (365 / days) - 1
    m = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    loss = [t["pnl"] for t in trades if t["pnl"] <= 0]
    return {"start": navs[0][0], "end": navs[-1][0], "return_pct": round(100 * tot, 2),
            "cagr_pct": round(100 * cagr, 2), "max_dd_pct": round(100 * mdd, 2),
            "mar": round(cagr / max(mdd, 0.02), 2), "sharpe": round(m / sd * math.sqrt(252), 2) if sd else None,
            "trades": len(trades), "win_rate": round(len(wins) / len(trades), 3) if trades else None,
            "profit_factor": round(sum(wins) / -sum(loss), 2) if loss and sum(loss) else None}


GRID = {
    "long": {"delta": [0.5, 0.3], "tp": [0.5, 1.0], "stop": [0.5], "hold": [5, 10]},
    "short": {"delta": [0.3, 0.2], "tp": [0.5], "stop": [1.0, 2.0], "hold": [15]},
}


def grid(fam):
    g = GRID["short" if "short" in fam else "long"]
    return [dict(zip(g, v)) for v in product(*g.values())]


def walk_forward(days, px, vix, fam, first, train=120, test=40, gate=False, **kw):
    """Pick the best-MAR params on each train window, trade them on the next test window, carry NAV."""
    nav, curve, trades, picks = 100_000.0, [], [], []
    t0 = first + train
    while t0 < len(days) - 1:
        t1 = min(t0 + test, len(days) - 1)
        best = max(grid(fam), key=lambda p: metrics(*simulate(days, px, vix, fam, {**p, "gate": gate},
                                                               t0 - train, t0 - 1, **kw))["mar"])
        n, tr = simulate(days, px, vix, fam, {**best, "gate": gate}, t0, t1, nav0=nav, **kw)
        curve += n if not curve else n[1:]
        trades += tr
        nav = n[-1][1]
        picks.append({"test": [days[t0], days[t1]], **best})
        t0 = t1
    return curve, trades, picks


def main():
    days, px, vix = load()
    first = 51 + 21  # signals need 51 closes; the vol model needs RV20
    oos_start = first + 120
    out = {"calibration": {}, "oos_window": [days[oos_start], days[-1]], "ladder": {}, "benchmarks": {},
           "in_sample_grid": {}, "robustness": {}, "stress": {}, "picks": {}}

    vol = Vol(px, vix)
    i = len(days) - 1
    out["calibration"] = {"date": days[i], "vix": vix[i],
                          "SPY_atm_model": round(vol.atm("SPY", i), 4), "SPY_atm_live": 0.1370,
                          "NVDA_atm_model": round(vol.atm("NVDA", i), 4), "NVDA_atm_live": 0.3160,
                          "SPY_730P_model": round(vol.iv("SPY", i, px["SPY"][i], 730, 32 / 365), 4),
                          "SPY_730P_live": 0.1768,
                          "NVDA_210P_model": round(vol.iv("NVDA", i, px["NVDA"][i], 210, 32 / 365), 4),
                          "NVDA_210P_live": 0.3464}

    # stock baseline over the same OOS window: the equity-only shadow book
    cfg = bt.config.load()
    series = {s: v for s, v in bt.load_series().items() if s in EQ}
    sh, nav, _ = bt.run(series, cfg, start=days[oos_start - 1])
    stock = [(d, n) for d, n, _ in nav if d >= days[oos_start - 1]]
    out["ladder"]["L0 stock shadow (equities)"] = metrics(stock, [{"pnl": 0}] * 0)

    fams = [("L1 long calls on signals", "long_call", False),
            ("L2 + long puts on bearish", "long_both", False),
            ("L3 short puts on signals", "short_put", False),
            ("L4 short puts + VRP gate", "short_put", True)]
    curves = {"L0 stock shadow (equities)": stock}
    for name, fam, gate in fams:
        c, tr, picks = walk_forward(days, px, vix, fam, first, gate=gate)
        out["ladder"][name] = metrics(c, tr)
        out["picks"][name] = picks
        curves[name] = c
    for name, fam, p in [("Always-on SPY long ATM call", "always_long_call", {"delta": 0.5, "tp": 9, "stop": 9, "hold": 999}),
                         ("Always-on SPY short 30-delta put", "always_short_put", {"delta": 0.3, "tp": 9, "stop": 99, "hold": 999})]:
        c, tr = simulate(days, px, vix, fam, p, oos_start)
        out["benchmarks"][name] = metrics(c, tr)
        curves[name] = c
    spy0 = px["SPY"][oos_start]
    spy = [(d, 100_000 * px["SPY"][j] / spy0) for j, d in enumerate(days) if j >= oos_start]
    out["benchmarks"]["SPY buy-and-hold"] = metrics(spy, [])
    curves["SPY buy-and-hold"] = spy

    # hindsight ceiling + ablation: every grid point, in-sample over the whole tradable span
    for fam in ("long_call", "long_both", "short_put"):
        rows = []
        for p in grid(fam):
            m = metrics(*simulate(days, px, vix, fam, p, first))
            rows.append({**p, **{k: m[k] for k in ("return_pct", "max_dd_pct", "mar", "trades", "win_rate")}})
        out["in_sample_grid"][fam] = sorted(rows, key=lambda r: -r["mar"])
        best = {k: out["in_sample_grid"][fam][0][k] for k in ("delta", "tp", "stop", "hold")}
        c, _ = simulate(days, px, vix, fam, best, first)
        seg = [n for d, n in c if "2026-03-02" <= d <= "2026-04-02"]
        pk, dd = seg[0], 0.0
        for x in seg:
            pk = max(pk, x)
            dd = max(dd, 1 - x / pk)
        out["stress"].setdefault("Mar-2026 selloff, in-sample best params", {})[fam] = round(-100 * dd, 2)

    # robustness on the OOS walk-forward
    for label, kw in {"costs x2": {"cost_x": 2.0}, "IV x0.85": {"iv_scale": 0.85}, "IV x1.15": {"iv_scale": 1.15}}.items():
        out["robustness"][label] = {}
        for name, fam, gate in fams:
            c, tr, _ = walk_forward(days, px, vix, fam, first, gate=gate, **kw)
            out["robustness"][label][name] = metrics(c, tr)["return_pct"]
    for name, fam, gate in fams:
        c, tr, _ = walk_forward(days, px, vix, fam, first, train=80, test=40, gate=gate)
        out["robustness"].setdefault("train 80d", {})[name] = metrics(c, tr)["return_pct"]

    # stress: worst drawdown of each OOS curve inside named windows
    windows = {"Mar-2026 selloff (VIX 31)": ("2026-03-02", "2026-04-02"),
               "Jun-2026 drop (VIX 22)": ("2026-06-05", "2026-06-26"),
               "Jul-2026 tech slide": ("2026-07-17", "2026-07-31")}
    for w, (a, b) in windows.items():
        if b < days[oos_start]:
            continue
        out["stress"][w] = {}
        for name, c in curves.items():
            seg = [n for d, n in c if a <= d <= b]
            if len(seg) > 1:
                pk, dd = seg[0], 0.0
                for x in seg:
                    pk = max(pk, x)
                    dd = max(dd, 1 - x / pk)
                out["stress"][w][name] = round(-100 * dd, 2)
    out["curves"] = {k: [(d, round(n, 2)) for d, n in v] for k, v in curves.items()}
    (ROOT / "backtest/options_results.json").write_text(json.dumps(out, indent=1) + "\n")

    print("calibration", out["calibration"])
    print("OOS", out["oos_window"])
    for k, m in {**out["ladder"], **out["benchmarks"]}.items():
        print(f"{k:<34} ret {m['return_pct']:+7.2f}%  cagr {m['cagr_pct']:+7.2f}%  dd {m['max_dd_pct']:6.2f}%  "
              f"mar {m['mar']:6.2f}  trades {m['trades']:4}  win {m['win_rate']}  pf {m['profit_factor']}")
    print("robustness", json.dumps(out["robustness"]))
    print("stress", json.dumps(out["stress"]))
    for fam, rows in out["in_sample_grid"].items():
        print("IS best", fam, rows[0], "| worst", rows[-1])
    print("picks", json.dumps(out["picks"]))


if __name__ == "__main__":
    main()
