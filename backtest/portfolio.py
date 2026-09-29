"""Combine the desk's sleeves and test which mix is best, strictly out of sample (ai-fund-desk method).

    python3 -m backtest.portfolio            # writes backtest/portfolio_results.json

Pre-registered before any run (2026-09-29):
  primary    risk parity, sleeves correlated above CORR_MERGE over the lookback share one risk budget
  others     equal weight, inverse volatility, walk-forward max-Sharpe (fit on LOOKBACK months, hold 12,
             each weight capped at 50%, covariance shrunk halfway to its diagonal, means shrunk halfway to the grand mean),
             and every single sleeve
  overlays   10% portfolio vol target (never levered; the rest earns T-bills); a 10% drawdown moves the
             book to T-bills for COOLDOWN months (the kill switch; a human re-arms live)
  costs      COST_PER_TURN per unit of rebalance turnover, on top of the sleeves' own net costs
  verdict    a mix "wins" only if the 5th percentile of a paired block bootstrap of (Sharpe_mix - Sharpe_x)
             is above 0 for both the best single sleeve and T-bills
Every weight uses returns strictly before the month it is applied to (tests/test_portfolio.py checks this with a shift test).
"""
import json
import math
import pathlib
import random

from backtest import sleeves as S

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "backtest" / "portfolio_results.json"

LOOKBACK, HOLD, CAP = 36, 12, 0.50
VOL_TARGET, VOL_WINDOW, DD_KILL, COOLDOWN = 0.10, 12, 0.10, 3
CORR_MERGE = 0.70
COST_PER_TURN = 0.0010
BOOT_N, BOOT_BLOCK, SEED = 2000, 6, 20260929
STRESS = {"2008-09..2009-03": ("2008-09", "2009-03"), "2020-02..2020-04": ("2020-02", "2020-04"),
          "2022": ("2022-01", "2022-12")}


# ---------- small linear algebra (stdlib only) ----------
def mean(xs):
    return sum(xs) / len(xs)


def cov(cols):
    n, k = len(cols[0]), len(cols)
    m = [mean(c) for c in cols]
    return [[sum((cols[i][t] - m[i]) * (cols[j][t] - m[j]) for t in range(n)) / (n - 1) for j in range(k)] for i in range(k)]


def corr(c):
    k = len(c)
    return [[c[i][j] / math.sqrt(c[i][i] * c[j][j]) if c[i][i] > 0 and c[j][j] > 0 else 0.0 for j in range(k)] for i in range(k)]


def mv(m, v):
    return [sum(a * b for a, b in zip(row, v)) for row in m]


def port_var(w, c):
    return sum(a * b for a, b in zip(w, mv(c, w)))


# ---------- weighting methods ----------
def clusters(c, thresh=CORR_MERGE):
    """Group sleeves whose pairwise correlation exceeds thresh (single linkage). Returns a label per sleeve."""
    r, k = corr(c), len(c)
    lab = list(range(k))
    for i in range(k):
        for j in range(i + 1, k):
            if r[i][j] > thresh:
                a, b = lab[i], lab[j]
                lab = [a if x == b else x for x in lab]
    return lab


def w_equal(c):
    k = len(c)
    return [1 / k] * k


def w_invvol(c):
    iv = [1 / math.sqrt(c[i][i]) if c[i][i] > 0 else 0.0 for i in range(len(c))]
    s = sum(iv)
    return [x / s for x in iv]


def w_riskparity(c, budgets=None, iters=2000):
    """Long-only equal risk contribution: w_i * (C w)_i = b_i * w'Cw. Damped fixed-point iteration."""
    k = len(c)
    b = budgets or [1 / k] * k
    w = w_invvol(c)
    for _ in range(iters):
        cw = mv(c, w)
        pv = sum(a * x for a, x in zip(w, cw))
        new = [math.sqrt(w[i] * b[i] * pv / cw[i]) if cw[i] > 0 else w[i] for i in range(k)]
        s = sum(new)
        new = [x / s for x in new]
        if max(abs(a - x) for a, x in zip(new, w)) < 1e-12:
            w = new
            break
        w = new
    return w


def w_riskparity_merged(c):
    """Risk parity where each correlated cluster (> CORR_MERGE) shares one budget: the limits.yaml rule."""
    lab = clusters(c)
    groups = {x: lab.count(x) for x in set(lab)}
    b = [1 / len(groups) / groups[x] for x in lab]
    return w_riskparity(c, b)


def w_maxsharpe(c, mu, cap=CAP, draws=4000, seed=SEED):
    """Long-only max-Sharpe with shrinkage and a weight cap, by seeded search over the simplex (stdlib, deterministic)."""
    k = len(c)
    cs = [[c[i][j] * (1.0 if i == j else 0.5) for j in range(k)] for i in range(k)]
    g = mean(mu)
    ms = [0.5 * m + 0.5 * g for m in mu]
    rng = random.Random(seed)
    best, bw = -1e9, w_invvol(c)
    cands = [bw] + [[1.0 if j == i else 0.0 for j in range(k)] for i in range(k)]
    for _ in range(draws):
        x = [rng.expovariate(1.0) for _ in range(k)]
        s = sum(x)
        cands.append([v / s for v in x])
    for w in cands:
        if max(w) > cap + 1e-9:
            continue
        v = port_var(w, cs)
        if v <= 0:
            continue
        sr = sum(a * m for a, m in zip(w, ms)) / math.sqrt(v)
        if sr > best:
            best, bw = sr, w
    return bw


METHODS = {"equal": w_equal, "inverse_vol": w_invvol, "risk_parity": w_riskparity_merged}


# ---------- backtest ----------
def align(streams, months=None):
    names = sorted(streams)
    common = set.intersection(*[set(streams[n]) for n in names])
    if months:
        common &= set(months)
    return names, sorted(common)


def run(streams, tbill, method, start_idx=LOOKBACK, overlay=True, cost=COST_PER_TURN):
    """Monthly rebalanced out-of-sample run. Returns {"months", "ret", "weights", "turnover"}.

    Weights for month t use months [t-LOOKBACK, t) only. The walk-forward max-Sharpe refits every HOLD months.
    Overlay: vol target on the mix's own trailing VOL_WINDOW returns (never above 1x), then the drawdown kill."""
    names, months = align(streams)
    months = [m for m in months if m in tbill]
    rets, ws, turns, out_m = [], [], [], []
    w_prev, held, raw_hist = None, None, []
    nav, peak, cool = 1.0, 1.0, 0
    for t in range(start_idx, len(months)):
        win = months[t - LOOKBACK:t]
        cols = [[streams[n][m] for m in win] for n in names]
        c = cov(cols)
        if method == "max_sharpe":
            if held is None or (t - start_idx) % HOLD == 0:
                held = w_maxsharpe(c, [mean(col) for col in cols])
            w = held
        else:
            w = METHODS[method](c)
        m = months[t]
        raw = sum(wi * streams[n][m] for wi, n in zip(w, names))
        scale = 1.0
        if overlay and len(raw_hist) >= VOL_WINDOW:
            h = raw_hist[-VOL_WINDOW:]
            mu = mean(h)
            sd = math.sqrt(sum((x - mu) ** 2 for x in h) / (len(h) - 1)) * math.sqrt(12)
            scale = min(1.0, VOL_TARGET / sd) if sd > 0 else 1.0
        if overlay and cool > 0:
            scale, cool = 0.0, cool - 1
        eff = [wi * scale for wi in w]
        turn = sum(abs(a - b) for a, b in zip(eff, w_prev)) if w_prev else sum(eff)
        r = sum(e * streams[n][m] for e, n in zip(eff, names)) + (1 - sum(eff)) * tbill[m] - turn * cost
        raw_hist.append(raw)
        nav *= 1 + r
        peak = max(peak, nav)
        if overlay and cool == 0 and nav < (1 - DD_KILL) * peak:
            cool, peak = COOLDOWN, nav
        rets.append(r)
        ws.append([round(x, 4) for x in eff])
        turns.append(turn)
        out_m.append(m)
        w_prev = eff
    return {"names": names, "months": out_m, "ret": rets, "weights": ws, "turnover": turns}


def metrics(rets, tb):
    n = len(rets)
    nav, peak, dd = 1.0, 1.0, 0.0
    for r in rets:
        nav *= 1 + r
        peak = max(peak, nav)
        dd = min(dd, nav / peak - 1)
    yrs = n / 12
    cagr = nav ** (1 / yrs) - 1
    ex = [r - b for r, b in zip(rets, tb)]
    sd = math.sqrt(sum((x - mean(rets)) ** 2 for x in rets) / (n - 1))
    down = [min(0.0, x) for x in ex]
    dsd = math.sqrt(sum(x * x for x in down) / n)
    tb_nav = 1.0
    for b in tb:
        tb_nav *= 1 + b
    return {"cagr": round(cagr, 4), "vol": round(sd * math.sqrt(12), 4),
            "sharpe": round(mean(ex) / (sd or 1e-12) * math.sqrt(12), 3) if sd else 0.0,
            "sortino": round(mean(ex) / (dsd or 1e-12) * math.sqrt(12), 3) if dsd else None,
            "max_dd": round(dd, 4), "worst_month": round(min(rets), 4),
            "excess_cagr_vs_tbill": round(cagr - (tb_nav ** (1 / yrs) - 1), 4),
            "end_500": round(500 * nav, 2), "end_10k": round(10_000 * nav, 2), "months": n}


def sharpe(rets, tb):
    ex = [r - b for r, b in zip(rets, tb)]
    m = mean(ex)
    sd = math.sqrt(sum((x - m) ** 2 for x in ex) / (len(ex) - 1))
    return m / sd * math.sqrt(12) if sd > 0 else 0.0


def boot_idx(n, rng, block=BOOT_BLOCK):
    idx = []
    while len(idx) < n:
        s = rng.randrange(n)
        idx.extend((s + j) % n for j in range(block))
    return idx[:n]


def paired_sharpe_diff(a, b, tb, n=BOOT_N, seed=SEED):
    """5th/50th/95th percentiles of Sharpe(a) - Sharpe(b) over a circular block bootstrap of the same months."""
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        ix = boot_idx(len(a), rng)
        ta = [tb[i] for i in ix]
        d.append(sharpe([a[i] for i in ix], ta) - sharpe([b[i] for i in ix], ta))
    d.sort()
    return {"p05": round(d[int(0.05 * n)], 3), "p50": round(d[n // 2], 3), "p95": round(d[int(0.95 * n) - 1], 3)}


def sharpe_ci(a, tb, n=BOOT_N, seed=SEED):
    rng = random.Random(seed)
    s = []
    for _ in range(n):
        ix = boot_idx(len(a), rng)
        s.append(sharpe([a[i] for i in ix], [tb[i] for i in ix]))
    s.sort()
    return [round(s[int(0.05 * n)], 3), round(s[int(0.95 * n) - 1], 3)]


def corr_table(streams, months):
    names = sorted(streams)
    ms = [m for m in months if all(m in streams[n] for n in names)]
    if len(ms) < 3:
        return None
    r = corr(cov([[streams[n][m] for m in ms] for n in names]))
    return {"names": names, "months": len(ms), "matrix": [[round(x, 2) for x in row] for row in r]}


def evaluate(streams, tbill, label):
    """Every method (with and without overlay) plus every single sleeve, on one common out-of-sample window."""
    names, months = align(streams)
    months = [m for m in months if m in tbill]
    res = {"label": label, "sleeves": names, "window": None, "runs": {}}
    base = None
    for method in ("risk_parity", "equal", "inverse_vol", "max_sharpe"):
        for ov in (True, False):
            r = run(streams, tbill, method, overlay=ov)
            key = method + ("+overlay" if ov else "")
            tb = [tbill[m] for m in r["months"]]
            res["runs"][key] = {**metrics(r["ret"], tb), "sharpe_ci90": sharpe_ci(r["ret"], tb),
                                "avg_turnover": round(mean(r["turnover"]), 4),
                                "cost_drag": round(mean(r["turnover"]) * 12 * COST_PER_TURN, 4),
                                "last_weights": dict(zip(r["names"], r["weights"][-1])), "_ret": r["ret"]}
            base = base or r
    oos = base["months"]
    res["window"] = [oos[0], oos[-1]]
    tb = [tbill[m] for m in oos]
    for n in names:
        rr = [streams[n][m] for m in oos]
        res["runs"]["single:" + n] = {**metrics(rr, tb), "sharpe_ci90": sharpe_ci(rr, tb), "_ret": rr}
    res["runs"]["tbill"] = {**metrics(tb, tb), "_ret": tb}
    singles = [k for k in res["runs"] if k.startswith("single:")]
    best_single = max(singles, key=lambda k: res["runs"][k]["sharpe"])
    res["best_single"] = best_single
    for k, v in res["runs"].items():
        if k.startswith("single:") or k == "tbill":
            continue
        vs_best = paired_sharpe_diff(v["_ret"], res["runs"][best_single]["_ret"], tb)
        v["vs_best_single"] = vs_best
        v["wins"] = vs_best["p05"] > 0 and v["sharpe_ci90"][0] > 0
    res["corr"] = corr_table(streams, oos)
    res["stress_corr"] = {k: corr_table(streams, [m for m in months if a <= m <= b]) for k, (a, b) in STRESS.items()}
    for v in res["runs"].values():
        v.pop("_ret", None)
    ranked = sorted((k for k in res["runs"] if k != "tbill"), key=lambda k: -res["runs"][k]["sharpe"])
    res["ranking_by_sharpe"] = ranked
    return res


def main(root=S.LONG, out=OUT):
    net = S.build(root, net=True)
    gross = S.build(root, net=False)
    sl, tb = net["sleeves"], net["tbill"]
    sets = {
        "all_five": {k: sl[k] for k in ("SPY", "PUT", "CNDR", "BXM", "TREND")},
        "desk_three": {k: sl[k] for k in ("PUT", "CNDR", "TREND")},
        "options_long": {k: sl[k] for k in ("SPY", "PUT", "CNDR", "BXM")},
        "spy_trend": {k: sl[k] for k in ("SPY", "TREND")},
    }
    results = {"registered": "2026-09-29", "method": __doc__.strip().splitlines()[0],
               "params": {"lookback": LOOKBACK, "hold": HOLD, "cap": CAP, "vol_target": VOL_TARGET,
                          "dd_kill": DD_KILL, "cooldown": COOLDOWN, "corr_merge": CORR_MERGE,
                          "cost_per_turn": COST_PER_TURN, "boot": [BOOT_N, BOOT_BLOCK, SEED],
                          "option_drag": S.OPTION_DRAG, "etf_cost": S.ETF_COST},
               "sources": net["sources"],
               "notes": ["SPY is price-only (TradingView); dividends of about 1.5-2%/yr are left out, so SPY is understated.",
                         "The Cboe indices carry no trading costs; the net run deducts 1.0%/yr.",
                         "TREND replays trend-etf-v1 on weekly crypto closes (SMA 4/20 wk, RV 6 wk); before 2024 the ETFs did not exist, so it is a proxy.",
                         "Funding carry is not included: there is no US-legal history to test."],
               "sets": {k: evaluate(v, tb, k) for k, v in sets.items()}}
    results["gross_sleeve_cagr_full"] = {n: round(_cagr(gross["sleeves"][n]), 4) for n in gross["sleeves"]}
    results["net_sleeve_cagr_full"] = {n: round(_cagr(sl[n]), 4) for n in sl}
    results["bench_cagr_full"] = {n: round(_cagr(v), 4) for n, v in net["bench"].items()}
    out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return results


def _cagr(stream):
    ks = sorted(stream)
    nav = 1.0
    for k in ks:
        nav *= 1 + stream[k]
    return nav ** (12 / len(ks)) - 1 if ks else 0.0


if __name__ == "__main__":
    r = main()
    for name, s in r["sets"].items():
        print(f"\n{name}  {s['window'][0]}..{s['window'][1]}  best single {s['best_single']}")
        for k in s["ranking_by_sharpe"]:
            v = s["runs"][k]
            w = "  WINS" if v.get("wins") else ""
            print(f"  {k:28s} CAGR {v['cagr']:7.2%}  vol {v['vol']:6.2%}  Sharpe {v['sharpe']:5.2f} "
                  f"{v.get('sharpe_ci90', '')}  DD {v['max_dd']:7.2%}  $500->{v['end_500']:,.0f}{w}")
