"""Glosten-Milgrom x Avellaneda-Stoikov toxicity-aware quoting toolkit.

Research / simulation only. Never places orders.
Usage:
  python gm_engine.py decompose --csv trades.csv [--window 120]
  python gm_engine.py simulate --demo [--steps 20000 --seed 7]
"""
import argparse, json, sys
import numpy as np
import pandas as pd


# ---- GM core ---------------------------------------------------------------
def gm_quotes(mu, V_H, V_L, prior_pH=0.5):
    p_buy_H, p_buy_L = 0.5 + 0.5 * mu, 0.5 - 0.5 * mu
    p_buy = p_buy_H * prior_pH + p_buy_L * (1 - prior_pH)
    post_buy = p_buy_H * prior_pH / p_buy
    post_sel = p_buy_L * prior_pH / (1 - p_buy)
    ask = post_buy * V_H + (1 - post_buy) * V_L
    bid = post_sel * V_H + (1 - post_sel) * V_L
    return round(bid, 6), round(ask, 6)


def gm_spread(mu, V_H, V_L):
    return mu * (V_H - V_L)


def bayesian_update(prior_pH, mu, direction):
    p_buy_VH, p_buy_VL = mu + (1 - mu) * 0.5, (1 - mu) * 0.5
    if direction == "buy":
        return p_buy_VH * prior_pH / (p_buy_VH * prior_pH + p_buy_VL * (1 - prior_pH))
    return 1 - bayesian_update(1 - prior_pH, mu, "buy")


def pin_score(alpha, mu_rate, eps_b, eps_s):
    inf = alpha * mu_rate
    return inf / (inf + eps_b + eps_s)


# ---- Live signals ----------------------------------------------------------
def compute_vpin(buy_vol, sell_vol, n_buckets=50):
    b, s = np.asarray(buy_vol, float), np.asarray(sell_vol, float)
    if len(b) < n_buckets:
        return None
    t = (b + s)[-n_buckets:]
    return float(np.mean(np.abs(b - s)[-n_buckets:] / np.where(t > 0, t, 1)))


def volume_buckets(signed_vol, bucket_size):
    """Fill equal-volume buckets from a stream of signed volumes -> (buy, sell) lists."""
    buys, sells, cb, cs = [], [], 0.0, 0.0
    for v in signed_vol:
        rem = abs(v)
        while rem > 0:
            take = min(rem, bucket_size - (cb + cs))
            if v > 0: cb += take
            else: cs += take
            rem -= take
            if cb + cs >= bucket_size - 1e-12:
                buys.append(cb); sells.append(cs); cb = cs = 0.0
    return buys, sells


def build_toxicity_features(prices, volumes, spreads, window=20):
    df = pd.DataFrame({"price": prices, "volume": volumes, "spread": spreads})
    sv = df["volume"] * np.sign(df["price"].diff())
    df["order_imbalance"] = sv.rolling(window).sum() / df["volume"].rolling(window).sum()
    df["vol_ratio"] = df["volume"] / df["volume"].rolling(window).mean()
    df["spread_change"] = df["spread"].pct_change(window)
    df["realized_vol"] = df["price"].pct_change().rolling(window).std()
    df["momentum"] = df["price"].diff(window)
    return df.dropna()


def decompose_spread(prices, order_flow, window=120):
    p, q = pd.Series(prices, dtype=float), pd.Series(order_flow, dtype=float)
    dp = p.diff()
    eff = 2 * np.sqrt((-dp.rolling(window).cov(dp.shift(1))).clip(lower=0))
    lam = dp.rolling(window).cov(q) / q.rolling(window).var().replace(0, np.nan)
    adv = (2 * lam.abs() * q.rolling(window).std().replace(0, np.nan)).clip(upper=eff)
    return pd.DataFrame({
        "effective": eff, "adverse_selection": adv,
        "inventory_processing": (eff - adv).clip(lower=0),
        "as_fraction": adv / eff.replace(0, np.nan),
    })


# ---- Control layer ---------------------------------------------------------
class MarketStateMonitor:
    def __init__(self, vpin_warn=0.70, vpin_halt=0.90, tox_warn=0.65, tox_halt=0.85):
        self.th = (vpin_warn, vpin_halt, tox_warn, tox_halt)
        self.status = "ACTIVE"

    def update(self, vpin, tox):
        vw, vh, tw, th = self.th
        self.status = ("HALTED" if vpin >= vh or tox >= th else
                       "WARNING" if vpin >= vw or tox >= tw else "ACTIVE")
        return self.status

    def pressure(self, vpin, tox):
        vw, vh, tw, th = self.th
        return float(np.clip(max((vpin - vw) / (vh - vw), (tox - tw) / (th - tw)), 0, 1))

    def spread_multiplier(self, vpin, tox):
        if self.status == "HALTED":
            return None
        return 1.0 + 2.0 * self.pressure(vpin, tox) if self.status == "WARNING" else 1.0


def position_limit(base, vpin, tox, vpin_warn=0.70, tox_warn=0.65):
    pr = max(np.clip((vpin - vpin_warn) / (1 - vpin_warn), 0, 1),
             np.clip((tox - tox_warn) / (1 - tox_warn), 0, 1))
    return max(1, int(base * (1.0 - 0.75 * pr)))


class GMASQuoteEngine:
    def __init__(self, gamma, sigma, T, mu_base=0.25, V_range=0.01):
        self.gamma, self.sigma, self.T, self.mu_base, self.V_range = gamma, sigma, T, mu_base, V_range

    def quotes(self, mid, q, t, monitor=None, vpin=0.0, tox=0.0):
        mult = 1.0
        if monitor is not None:
            monitor.update(vpin, tox)
            mult = monitor.spread_multiplier(vpin, tox)
            if mult is None:
                return None, None
        tau = max(self.T - t, 1e-9)
        r = mid - q * self.gamma * self.sigma ** 2 * tau
        half = (0.5 * self.gamma * self.sigma ** 2 * tau + 0.5 * self.mu_base * self.V_range) * mult
        return r - half, r + half


# ---- CLI -------------------------------------------------------------------
def _signed_flow(df):
    if "side" in df:
        return df["volume"] * np.sign(df["side"])
    s = np.sign(df["price"].diff()).replace(0, np.nan).ffill().fillna(0)
    return df["volume"] * s


def cmd_decompose(a):
    df = pd.read_csv(a.csv)
    d = decompose_spread(df["price"], _signed_flow(df), a.window).dropna()
    out = {k: float(d[k].median()) for k in d.columns}
    print(json.dumps({"rows": len(df), "median": out}, indent=2))


def simulate(steps=20000, seed=7, use_gm=True, base_limit=20, bucket=50.0):
    """GM-style tape: value V random-walks with jumps; informed share mu toggles regimes.
    Informed traders hit quotes that are stale vs V. P&L marked to V."""
    rng = np.random.default_rng(seed)
    V, mid, q, cash = 100.0, 100.0, 0, 0.0
    eng, mon = GMASQuoteEngine(gamma=0.1, sigma=0.02, T=1.0, mu_base=0.25, V_range=0.04), MarketStateMonitor()
    buys, sells, cb, cs = [], [], 0.0, 0.0
    log, last, adverse, fills = [], "ACTIVE", 0.0, 0
    for i in range(steps):
        toxic = (i // 2000) % 3 == 2                  # every 3rd regime is toxic
        mu = 0.85 if toxic else 0.1
        drift = (1 if (i // 6000) % 2 == 0 else -1) if toxic else 0
        V += 0.002 * drift + rng.normal(0, 0.005) + (rng.choice([-1, 1]) * 0.05 if rng.random() < 0.002 else 0)
        vpin = compute_vpin(buys, sells) or 0.0
        t = (i % 2000) / 2000
        if use_gm:
            lim = position_limit(base_limit, vpin, 0.0)
            bid, ask = eng.quotes(mid, q, t, mon, vpin, 0.0)
            if mon.status != last:
                log.append({"step": i, "from": last, "to": mon.status, "vpin": round(vpin, 3)}); last = mon.status
        else:
            lim = base_limit
            bid, ask = eng.quotes(mid, q, t)
        informed = rng.random() < mu
        side = (drift or (1 if V > mid else -1)) if informed else rng.choice([-1, 1])
        if side > 0:
            cb += 1
        else:
            cs += 1
        if cb + cs >= bucket:
            buys.append(cb); sells.append(cs); cb = cs = 0.0
        if bid is not None:
            if side > 0 and V >= ask - (0 if informed else 1) and q > -lim:
                q -= 1; cash += ask; fills += 1; adverse += max(V - ask, 0)
            elif side < 0 and V <= bid + (0 if informed else 1) and q < lim:
                q += 1; cash -= bid; fills += 1; adverse += max(bid - V, 0)
        mid += 0.3 * (V - mid) * (0.5 if informed else 0.1)   # price discovery from flow
    return {"pnl": round(cash + q * V, 3), "fills": fills, "adverse_markout": round(adverse, 3),
            "final_inventory": q, "transitions": len(log)}, log


def cmd_simulate(a):
    gm, log = simulate(a.steps, a.seed, True)
    asm, _ = simulate(a.steps, a.seed, False)
    rep = {"gm_as": gm, "pure_as": asm, "note": "synthetic GM tape; calibrate on real data before trusting"}
    json.dump(rep, open(a.out, "w"), indent=2)
    with open(a.log, "w") as f:
        for r in log: f.write(json.dumps(r) + "\n")
    print(json.dumps(rep, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("decompose"); d.add_argument("--csv", required=True); d.add_argument("--window", type=int, default=120)
    s = sp.add_parser("simulate"); s.add_argument("--demo", action="store_true")
    s.add_argument("--steps", type=int, default=20000); s.add_argument("--seed", type=int, default=7)
    s.add_argument("--out", default="gm_report.json"); s.add_argument("--log", default="gm_log.jsonl")
    a = p.parse_args(argv)
    (cmd_decompose if a.cmd == "decompose" else cmd_simulate)(a)


if __name__ == "__main__":
    main()
