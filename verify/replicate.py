"""Rebuild leaderboard strategy families with honest fills and KEEP/KILL them against the incumbent.

    python3 -m verify.replicate          # writes verify/replication.json

Honest fills
  - A signal reads bar i's close and fills at bar i+1's open.
  - A stop level uses bars before the current bar only. It is checked before the trail updates, and a gap through the stop fills at the open.
  - Three cost runs per side: gross (0), 2 bp, and realistic (4.5 bp taker + 1 bp slippage = 5.5 bp).

Fair comparison
  Every family trades BTC/ETH/SOL with the incumbent's sizing: sleeves 50/30/20 and position = sleeve x min(1, 30%/RV30),
  fixed at entry. Only the entry/exit rule differs. A "raw" run (full sleeve, no vol scaling) is closer to how the
  leaderboard publishes results, and is used to check faithfulness against the published gross numbers.

KEEP only if the realistic run beats the incumbent's realistic run by > 0.5%/yr CAGR, with <= 1 point extra max drawdown,
the edge survives removing its best year, and it holds at parameters moved +/-20%. Otherwise KILL.
"""
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "verify" / "data"
OUT = ROOT / "verify" / "replication.json"

SLEEVES = {"BTCUSDT": 0.50, "ETHUSDT": 0.30, "SOLUSDT": 0.20}
COSTS = {"gross": 0.0, "2bp": 0.0002, "realistic": 0.00055}
VOL_TARGET, RV_DAYS = 0.30, 30
KEEP_CAGR, KEEP_DD = 0.005, 0.01


def load(sym, root=DATA, now=None):
    d = json.loads((root / f"{sym}_1D.json").read_text(encoding="utf-8"))
    bars = sorted(d["bars"])
    if now is not None:
        bars = [b for b in bars if b[0] + 86400 <= now]
    else:
        bars = bars[:-1]          # the last daily bar is still forming when fetched
    return {"t": [b[0] for b in bars], "o": [b[1] for b in bars], "h": [b[2] for b in bars],
            "l": [b[3] for b in bars], "c": [b[4] for b in bars], "meta": {k: d.get(k) for k in ("symbol", "source", "fetched")}}


# ---------- indicators (value at i uses bars <= i) ----------
def sma(x, n, i):
    return sum(x[i - n + 1:i + 1]) / n if i >= n - 1 else None


def ema_series(x, n):
    k, out, e = 2 / (n + 1), [], None
    for v in x:
        e = v if e is None else e + k * (v - e)
        out.append(e)
    return out


def atr_series(b, n):
    tr = [b["h"][0] - b["l"][0]]
    for i in range(1, len(b["c"])):
        pc = b["c"][i - 1]
        tr.append(max(b["h"][i] - b["l"][i], abs(b["h"][i] - pc), abs(b["l"][i] - pc)))
    out, a = [], None
    for i, v in enumerate(tr):
        a = v if a is None else (a * (n - 1) + v) / n     # Wilder
        out.append(a if i >= n - 1 else None)
    return out


def rv(c, i, n=RV_DAYS):
    if i < n:
        return None
    lr = [math.log(c[j] / c[j - 1]) for j in range(i - n + 1, i + 1)]
    m = sum(lr) / n
    return math.sqrt(sum((x - m) ** 2 for x in lr) / (n - 1)) * math.sqrt(365)


# ---------- families: each returns (enter[i], exit[i], stop_fn) evaluated on bar i's close ----------
def fam_incumbent(b, p):
    """trend-etf-v1: SMA fast/slow, 2-close confirmation, exit on the 2-close cross down or close < trail x peak close."""
    f, s, trail = p.get("fast", 20), p.get("slow", 100), p.get("trail", 0.80)
    c = b["c"]
    up = [False] * len(c)
    dn = [False] * len(c)
    for i in range(s, len(c)):
        f1, s1, f0, s0 = sma(c, f, i), sma(c, s, i), sma(c, f, i - 1), sma(c, s, i - 1)
        up[i], dn[i] = f1 > s1 and f0 > s0, f1 < s1 and f0 < s0
    return up, dn, {"close_trail": trail}


def fam_donchian(b, p):
    n_in, n_out = p.get("entry", 20), p.get("exit", 10)
    c, h, l = b["c"], b["h"], b["l"]
    up = [i >= n_in and c[i] > max(h[i - n_in:i]) for i in range(len(c))]
    dn = [i >= n_out and c[i] < min(l[i - n_out:i]) for i in range(len(c))]
    return up, dn, {}


def fam_supertrend(b, p):
    n, m = p.get("atr", 10), p.get("mult", 3.0)
    a = atr_series(b, n)
    c, h, l = b["c"], b["h"], b["l"]
    trend, fu, fl = [0] * len(c), None, None
    for i in range(len(c)):
        if a[i] is None:
            continue
        mid = (h[i] + l[i]) / 2
        bu, bl = mid + m * a[i], mid - m * a[i]
        fu = bu if fu is None or bu < fu or c[i - 1] > fu else fu
        fl = bl if fl is None or bl > fl or c[i - 1] < fl else fl
        prev = trend[i - 1] if i else 0
        trend[i] = 1 if c[i] > fu else -1 if c[i] < fl else (prev or 1)
    up = [i > 0 and trend[i] == 1 and trend[i - 1] != 1 for i in range(len(c))]
    dn = [trend[i] == -1 for i in range(len(c))]
    return up, dn, {}


def fam_ema_atr(b, p):
    f, s, n, m = p.get("fast", 20), p.get("slow", 50), p.get("atr", 14), p.get("mult", 3.0)
    ef, es = ema_series(b["c"], f), ema_series(b["c"], s)
    up = [i >= s and ef[i] > es[i] and ef[i - 1] <= es[i - 1] for i in range(len(ef))]
    dn = [i >= s and ef[i] < es[i] for i in range(len(ef))]
    return up, dn, {"atr_trail": (atr_series(b, n), m)}


FAMILIES = {
    "incumbent_trend_etf_v1": (fam_incumbent, {"fast": 20, "slow": 100, "trail": 0.80}),
    "donchian_breakout": (fam_donchian, {"entry": 20, "exit": 10}),
    "supertrend": (fam_supertrend, {"atr": 10, "mult": 3.0}),
    "ema_cross_atr_trail": (fam_ema_atr, {"fast": 20, "slow": 50, "atr": 14, "mult": 3.0}),
}


def scaled(p, k):
    out = {}
    for key, v in p.items():
        if key == "trail":
            out[key] = round(1 - (1 - v) * k, 4)
        elif isinstance(v, int):
            out[key] = max(2, int(round(v * k)))
        else:
            out[key] = round(v * k, 4)
    return out


# ---------- single-asset engine ----------
def simulate(b, fam, p, cost, capital, vol_scale=True):
    """Long/flat sub-account. Returns daily equity marks (at each close) and closed trades."""
    enter, leave, stop = fam(b, p)
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    n = len(c)
    cash, units, eq = capital, 0.0, []
    trades, entry_val, pending, peak, stop_lvl = [], 0.0, None, None, None
    for j in range(n):
        # 1) fill orders decided at the previous close, at this bar's open
        if pending == "buy" and units == 0:
            r = rv(c, j - 1)
            frac = min(1.0, VOL_TARGET / r) if vol_scale and r else 1.0
            val = cash * frac
            units, cash, entry_val = val * (1 - cost) / o[j], cash - val, val
            peak, stop_lvl = c[j - 1], None
        elif pending == "sell" and units > 0:
            proceeds = units * o[j] * (1 - cost)
            trades.append(proceeds - entry_val)
            cash, units = cash + proceeds, 0.0
        pending = None
        # 2) intrabar stop from prior bars only; a gap through fills at the open
        if units > 0 and stop_lvl is not None and l[j] <= stop_lvl:
            px = o[j] if o[j] <= stop_lvl else stop_lvl
            proceeds = units * px * (1 - cost)
            trades.append(proceeds - entry_val)
            cash, units = cash + proceeds, 0.0
        # 3) close: update trail, then decide the next open's order
        if units > 0:
            peak = max(peak, c[j])
            if "atr_trail" in stop:
                a, m = stop["atr_trail"]
                if a[j] is not None:
                    lvl = peak - m * a[j]
                    stop_lvl = lvl if stop_lvl is None else max(stop_lvl, lvl)
            ct = stop.get("close_trail")
            if leave[j] or (ct and c[j] < ct * peak):
                pending = "sell"
        elif enter[j] and j + 1 < n:
            pending = "buy"
        eq.append(cash + units * c[j])
    if units > 0:       # mark the open trade at the last close so profit factor counts it
        trades.append(units * c[-1] * (1 - cost) - entry_val)
    return eq, trades


def portfolio(data, fam, p, cost, vol_scale=True):
    """Run each asset on its sleeve of $1 and sum the equity on the common dates."""
    t0 = max(d["t"][0] for d in data.values())
    t1 = min(d["t"][-1] for d in data.values())
    total, trades = None, []
    for sym, sleeve in SLEEVES.items():
        d = data[sym]
        eq, tr = simulate(d, fam, p, cost, sleeve, vol_scale)
        idx = {t: e for t, e in zip(d["t"], eq)}
        ts = [t for t in d["t"] if t0 <= t <= t1]
        s = [idx[t] for t in ts]
        total = s if total is None else [a + x for a, x in zip(total, s)]
        trades += tr
    return ts, total, trades


def stats(ts, eq, trades, warm=0):
    ts, eq = ts[warm:], eq[warm:]
    yrs = (ts[-1] - ts[0]) / (365.25 * 86400)
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1
    peak, dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    r = [eq[i] / eq[i - 1] - 1 for i in range(1, len(eq))]
    m = sum(r) / len(r)
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    wins, losses = sum(x for x in trades if x > 0), -sum(x for x in trades if x < 0)
    years = {}
    from datetime import datetime, timezone
    for t, v in zip(ts, eq):
        y = datetime.fromtimestamp(t, timezone.utc).year
        years.setdefault(y, [v, v])[1] = v
    return {"cagr": round(cagr, 4), "max_dd": round(dd, 4), "sharpe": round(m / sd * math.sqrt(365), 2) if sd else 0.0,
            "trades": len(trades), "win_rate": round(sum(1 for x in trades if x > 0) / len(trades), 3) if trades else None,
            "profit_factor": round(wins / losses, 2) if losses else None,
            "per_year": {y: round(b / a - 1, 4) for y, (a, b) in sorted(years.items())}, "years": round(yrs, 2)}


def warmup(data):
    """Skip the first 101 days in every run so all families are scored on the same dates as the incumbent."""
    return 101


def evaluate(data):
    warm = warmup(data)
    out = {}
    for name, (fam, p) in FAMILIES.items():
        runs = {}
        for cname, cost in COSTS.items():
            ts, eq, tr = portfolio(data, fam, p, cost)
            runs[cname] = stats(ts, eq, tr, warm)
        ts, eq, tr = portfolio(data, fam, p, 0.0, vol_scale=False)
        runs["raw_gross"] = stats(ts, eq, tr, warm)
        sens = {}
        for k in (0.8, 1.2):
            ts, eq, tr = portfolio(data, fam, scaled(p, k), COSTS["realistic"])
            sens[f"x{k}"] = {"params": scaled(p, k), **{x: y for x, y in stats(ts, eq, tr, warm).items() if x != "per_year"}}
        out[name] = {"params": p, "runs": runs, "sensitivity": sens}
    inc = out["incumbent_trend_etf_v1"]["runs"]["realistic"]
    for name, v in out.items():
        if name.startswith("incumbent"):
            v["verdict"] = "INCUMBENT"
            continue
        r = v["runs"]["realistic"]
        edge = r["cagr"] - inc["cagr"]
        extra_dd = inc["max_dd"] - r["max_dd"]
        # "No single year carries it": remove the family's best year relative to the incumbent.
        yr_edge = {y: r["per_year"][y] - inc["per_year"].get(y, 0) for y in r["per_year"]}
        best_y = max(yr_edge, key=yr_edge.get) if yr_edge else None
        rest = [e for y, e in yr_edge.items() if y != best_y]
        survives_year = bool(rest) and sum(rest) / len(rest) > 0
        robust = all(s["cagr"] - inc["cagr"] > 0 for s in v["sensitivity"].values())
        keep = edge > KEEP_CAGR and extra_dd <= KEEP_DD and survives_year and robust
        v["vs_incumbent"] = {"cagr_edge": round(edge, 4), "extra_dd": round(extra_dd, 4), "best_year": best_y,
                             "edge_without_best_year": survives_year, "robust_pm20": robust}
        v["verdict"] = "KEEP" if keep else "KILL"
        why = []
        if edge <= KEEP_CAGR:
            why.append(f"realistic CAGR edge {edge:+.2%} <= +0.50%")
        if extra_dd > KEEP_DD:
            why.append(f"extra drawdown {extra_dd:.2%} > 1.00%")
        if not survives_year:
            why.append(f"edge depends on {best_y}")
        if not robust:
            why.append("fails at params +/-20%")
        v["why"] = "; ".join(why) or f"beats incumbent by {edge:+.2%}/yr after costs"
        v["gross_pf"] = v["runs"]["gross"]["profit_factor"]
    return out


def main(root=DATA, out=OUT):
    data = {s: load(s, root) for s in SLEEVES}
    res = {"registered": "2026-09-29", "rules": __doc__.strip().splitlines()[0], "costs_per_side": COSTS,
           "data": {s: {**d["meta"], "bars": len(d["t"])} for s, d in data.items()},
           "families": evaluate(data)}
    screened = ROOT / "verify" / "screen.json"
    if screened.exists():
        res["screen"] = json.loads(screened.read_text(encoding="utf-8"))["summary"]
    out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return res


if __name__ == "__main__":
    r = main()
    for name, v in r["families"].items():
        g, re_ = v["runs"]["gross"], v["runs"]["realistic"]
        print(f"{name:26s} {v['verdict']:9s} gross CAGR {g['cagr']:7.2%} PF {g['profit_factor']}  "
              f"realistic CAGR {re_['cagr']:7.2%} DD {re_['max_dd']:7.2%} Sharpe {re_['sharpe']}  trades {re_['trades']}  {v.get('why', '')}")
