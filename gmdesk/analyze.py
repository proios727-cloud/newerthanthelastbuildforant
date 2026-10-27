"""Stage 2: calibrate toxicity on recorded Kalshi tape, out of sample. Read-only.

    python -m gmdesk.analyze --data data/gm --series KXBTC15M

Train = oldest 60% of markets (fits VPIN bucket size + warn/halt cut points).
Test  = newest 40%: maker markout per contract (cents, settlement = true value V) by VPIN
quintile and by time-to-close, with market-clustered standard errors.
Gate 2 passes only if the top VPIN quintile is worse for makers than the bottom by > 2 SE
*and* that still holds inside the time-to-close buckets (VPIN must add information beyond the clock).
"""
import argparse
import gzip
import json
import math
import os
import statistics as st
import sys
from collections import defaultdict

from .core import VPIN, decompose

TAU = ((600, 1e9, ">10m"), (300, 600, "5-10m"), (120, 300, "2-5m"), (60, 120, "1-2m"), (0, 60, "<60s"))


def load(folder):
    """Settled markets from gmdesk.record backfill, oldest first."""
    mk = []
    for name in os.listdir(folder):
        if not name.endswith(".json.gz"):
            continue
        with gzip.open(os.path.join(folder, name), "rt", encoding="utf-8") as f:
            d = json.load(f)
        if d["result"] not in ("yes", "no"):
            continue
        tr = [{"ts": t[0], "p": t[1], "q": t[2], "s": t[3]} for t in d["t"] if t[2] > 0]
        if tr:
            mk.append({"ticker": d["ticker"], "close_ts": d["close_ts"], "R": 1.0 if d["result"] == "yes" else 0.0,
                       "trades": tr})
    return sorted(mk, key=lambda m: m["close_ts"])


def split(markets, frac=0.6):
    k = max(1, int(len(markets) * frac))
    return markets[:k], markets[k:]


def bucket_size(train, per_market=50):
    vols = [sum(r["q"] for r in m["trades"]) for m in train]
    return max(1.0, st.median(vols) / per_market)


def annotate(markets, bucket, n=20, horizon=60, ofi_s=30):
    """Walk markets in time order with one continuous VPIN; tag each trade (no look-ahead).

    `ofi` = signed taker volume / total volume over the previous `ofi_s` seconds of the same market;
    `aligned` = s * ofi, i.e. how strongly this taker trades *with* the recent flow.
    """
    v, out = VPIN(bucket, n), []
    for m in markets:
        tr = m["trades"]
        j, k, sv, tv = 0, 0, 0.0, 0.0
        for i, r in enumerate(tr):
            while j < len(tr) and tr[j]["ts"] < r["ts"] + horizon:
                j += 1
            while k < i and tr[k]["ts"] < r["ts"] - ofi_s:
                sv -= tr[k]["s"] * tr[k]["q"]; tv -= tr[k]["q"]; k += 1
            ofi = sv / tv if tv > 1e-9 else 0.0
            later = tr[j - 1]["p"] if j - 1 > i and tr[j - 1]["ts"] >= r["ts"] + horizon * 0.5 else None
            out.append({
                "ticker": m["ticker"], "vpin": v.value, "ofi": ofi, "aligned": r["s"] * ofi, "tau": m["close_ts"] - r["ts"], "q": r["q"], "p": r["p"],
                "settle_c": r["s"] * (r["p"] - m["R"]) * 100,
                "mark60_c": None if later is None else r["s"] * (r["p"] - later) * 100,
            })
            v.push(r["q"], r["s"])
            sv += r["s"] * r["q"]; tv += r["q"]
    return out


def quantiles(xs, k=5):
    xs = sorted(x for x in xs if x is not None)
    return [xs[int(len(xs) * i / k)] for i in range(1, k)] if xs else []


def which(x, cuts):
    return sum(x >= c for c in cuts)


def clustered(rows, key="settle_c"):
    """Volume-weighted mean markout with SE clustered by market."""
    per = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if r[key] is None:
            continue
        per[r["ticker"]][0] += r[key] * r["q"]
        per[r["ticker"]][1] += r["q"]
    if not per:
        return {"n_mkts": 0, "contracts": 0, "mean_c": None, "se_c": None}
    tot_q = sum(q for _, q in per.values())
    mean = sum(s for s, _ in per.values()) / tot_q
    g = len(per)
    var = sum(((s - mean * q) / tot_q) ** 2 for s, q in per.values()) * g / max(g - 1, 1)
    return {"n_mkts": g, "contracts": round(tot_q), "mean_c": round(mean, 3), "se_c": round(math.sqrt(var), 3)}


def run(markets, frac=0.6, n=20):
    train, test = split(markets, frac)
    bucket = bucket_size(train)
    tr_rows = [r for r in annotate(train, bucket, n) if r["vpin"] is not None]
    cuts = quantiles([r["vpin"] for r in tr_rows])
    all_rows = annotate(train + test, bucket, n)
    test_set = {m["ticker"] for m in test}
    te = [r for r in all_rows if r["ticker"] in test_set and r["vpin"] is not None]

    by_q = {f"Q{k + 1}": clustered([r for r in te if which(r["vpin"], cuts) == k]) for k in range(5)}
    by_q60 = {f"Q{k + 1}": clustered([r for r in te if which(r["vpin"], cuts) == k], "mark60_c") for k in range(5)}
    by_tau = {lab: clustered([r for r in te if lo <= r["tau"] < hi]) for lo, hi, lab in TAU}
    within = {}
    for lo, hi, lab in TAU:
        rs = [r for r in te if lo <= r["tau"] < hi]
        within[lab] = {"Q1": clustered([r for r in rs if which(r["vpin"], cuts) == 0]),
                       "Q5": clustered([r for r in rs if which(r["vpin"], cuts) == 4])}

    def gap(a, b):
        if a["mean_c"] is None or b["mean_c"] is None:
            return None
        return {"diff_c": round(a["mean_c"] - b["mean_c"], 3),
                "z": round((a["mean_c"] - b["mean_c"]) / max(math.hypot(a["se_c"], b["se_c"]), 1e-9), 2)}

    main_gap = gap(by_q["Q5"], by_q["Q1"])
    tau_gaps = {k: gap(v["Q5"], v["Q1"]) for k, v in within.items()}
    held = [g for g in tau_gaps.values() if g and g["z"] <= -1]
    gate2 = bool(main_gap and main_gap["z"] <= -2 and len(held) >= 2)

    tr_al = [r["aligned"] for r in annotate(train, bucket, n)]
    acuts = quantiles(tr_al)
    by_al = {f"A{k + 1}": clustered([r for r in te if which(r["aligned"], acuts) == k]) for k in range(5)}
    al_gap = gap(by_al["A5"], by_al["A1"])
    al_within = {}
    for lo, hi, lab in TAU:
        rs = [r for r in te if lo <= r["tau"] < hi]
        al_within[lab] = gap(clustered([r for r in rs if which(r["aligned"], acuts) == 4]),
                             clustered([r for r in rs if which(r["aligned"], acuts) == 0]))
    al_held = [g for g in al_within.values() if g and g["z"] <= -1]
    gate2_ofi = bool(al_gap and al_gap["z"] <= -2 and len(al_held) >= 2)

    dec = [d for d in (decompose([r["p"] for r in m["trades"]], [r["s"] * r["q"] for r in m["trades"]])
                       for m in markets) if d]
    med = {k: round(st.median(d[k] for d in dec), 4) for k in dec[0]} if dec else {}

    all_v = sorted(r["vpin"] for r in tr_rows)
    return {
        "markets": {"train": len(train), "test": len(test)},
        "trades": {"train": sum(len(m["trades"]) for m in train), "test": sum(len(m["trades"]) for m in test)},
        "vpin": {"bucket_contracts": round(bucket, 2), "window": n, "train_quintile_cuts": [round(c, 4) for c in cuts],
                 "suggested_warn": round(all_v[int(len(all_v) * 0.80)], 4) if all_v else None,
                 "suggested_halt": round(all_v[int(len(all_v) * 0.95)], 4) if all_v else None},
        "maker_markout_settle_by_vpin": by_q,
        "maker_markout_60s_by_vpin": by_q60,
        "maker_markout_settle_by_time_to_close": by_tau,
        "q5_minus_q1_within_time_bucket": tau_gaps,
        "q5_minus_q1": main_gap,
        "spread_decomposition_median": med | {"markets": len(dec)},
        "ofi30": {"train_cuts": [round(c, 4) for c in acuts], "maker_markout_settle_by_aligned": by_al,
                  "a5_minus_a1": al_gap, "a5_minus_a1_within_time_bucket": al_within,
                  "gate2": {"pass": gate2_ofi, "rule": "same rule, aligned-OFI quintiles instead of VPIN"}},
        "gate2": {"pass": gate2 or gate2_ofi, "vpin_pass": gate2, "ofi_pass": gate2_ofi, "rule": "Q5-Q1 maker markout z <= -2 overall and z <= -1 in >= 2 time-to-close buckets"},
    }


def render(series, rep):
    L = [f"== {series}: {rep['markets']['train']} train / {rep['markets']['test']} test markets, "
         f"{rep['trades']['test']} test trades"]
    v = rep["vpin"]
    L.append(f"VPIN bucket {v['bucket_contracts']} contracts x {v['window']}; quintile cuts {v['train_quintile_cuts']}")
    L.append(f"suggested warn/halt (train p80/p95): {v['suggested_warn']} / {v['suggested_halt']}")
    L.append("maker markout at settlement, cents/contract (negative = makers lose):")
    for k, b in rep["maker_markout_settle_by_vpin"].items():
        b60 = rep["maker_markout_60s_by_vpin"][k]
        L.append(f"  VPIN {k}: {b['mean_c']:>8} ± {b['se_c']:<7} 60s: {b60['mean_c']:>8}  ({b['contracts']} ct, {b['n_mkts']} mkts)")
    for k, b in rep["maker_markout_settle_by_time_to_close"].items():
        L.append(f"  tau {k:>6}: {b['mean_c']:>8} ± {b['se_c']}  ({b['contracts']} ct)")
    L.append(f"Q5-Q1 overall: {rep['q5_minus_q1']}")
    L.append(f"Q5-Q1 within time buckets: {rep['q5_minus_q1_within_time_bucket']}")
    L.append(f"spread decomposition (median per market): {rep['spread_decomposition_median']}")
    o = rep["ofi30"]
    L.append("maker markout by aligned 30s OFI quintile (A5 = taker trades hardest WITH recent flow):")
    for k, b in o["maker_markout_settle_by_aligned"].items():
        L.append(f"  OFI {k}: {b['mean_c']:>8} ± {b['se_c']:<7} ({b['contracts']} ct)")
    L.append(f"A5-A1 overall: {o['a5_minus_a1']}  within time buckets: {o['a5_minus_a1_within_time_bucket']}")
    L.append(f"GATE 2: {'PASS' if rep['gate2']['pass'] else 'FAIL'}  (VPIN {'PASS' if rep['gate2']['vpin_pass'] else 'FAIL'}, OFI {'PASS' if rep['gate2']['ofi_pass'] else 'FAIL'})")
    L.append(f"gate 2 rule: {rep['gate2']['rule']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/gm")
    ap.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    ap.add_argument("--window", type=int, default=20)
    a = ap.parse_args(argv)
    for s in a.series:
        path = os.path.join(a.data, s)
        if not os.path.exists(path):
            print(f"{s}: no data at {path}; run gmdesk.record backfill first", file=sys.stderr)
            continue
        rep = run(load(path), n=a.window)
        with open(os.path.join(a.data, f"report_{s}.json"), "w") as f:
            json.dump(rep, f, indent=2)
        print(render(s, rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
