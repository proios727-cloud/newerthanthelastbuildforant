"""Pack stage 2-4 outputs into one compact JSON for the control board's Real-tape view.

    python -m gmdesk.board_data --data data/gm --out skills/gm-toxicity-mm/gm_real.json
"""
import argparse
import json
import os
from datetime import datetime, timezone

from .shadow import report as shadow_report


def _read(p):
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def series_block(data, s):
    rep, rp = _read(os.path.join(data, f"report_{s}.json")), _read(os.path.join(data, f"replay_{s}.json"))
    if not rep or not rp:
        return None
    sh_log = os.path.join(data, f"shadow_{s}.jsonl")
    sh = shadow_report(sh_log, os.path.join(data, f"replay_{s}.json")) if os.path.exists(sh_log) else None
    if sh and "gate4" in sh:
        with open(os.path.join(data, f"shadow_gate_{s}.json"), "w") as f:
            json.dump(sh, f, indent=2)
    tk = next(iter(rp["traces"]), None)
    tr = rp["traces"].get(tk) if tk else None
    step = lambda xs: xs[:: max(1, len(xs) // 400)] if xs else xs
    return {
        "series": s,
        "markets": rep["markets"], "trades": rep["trades"], "vpin": rep["vpin"],
        "by_vpin": rep["maker_markout_settle_by_vpin"], "by_vpin_60s": rep["maker_markout_60s_by_vpin"],
        "by_tau": rep["maker_markout_settle_by_time_to_close"], "q5_q1": rep["q5_minus_q1"],
        "decomp": rep["spread_decomposition_median"], "gate2": rep["gate2"],
        "replay": {"gm": rp["gm_as"], "as": rp["pure_as"], "diff": rp["diff_per_market"], "gate3": rp["gate3"],
                   "model": rp["model"], "half_c": {"gm": rp["config"]["gm_as"]["base_half_c"],
                                                    "as": rp["config"]["pure_as"]["base_half_c"]},
                   "per_market": rp["per_market"]},
        "trace": tr and {"ticker": tk, "gm": step(tr["gm"]), "as": step(tr["as"])},
        "shadow": sh,
    }


def build(data, series):
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "series": [b for b in (series_block(data, s) for s in series) if b]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/gm")
    ap.add_argument("--series", nargs="+", default=["KXBTC15M", "KXETH15M"])
    ap.add_argument("--out", default="skills/gm-toxicity-mm/gm_real.json")
    a = ap.parse_args(argv)
    out = build(a.data, a.series)
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {a.out}: {[b['series'] for b in out['series']]}")


if __name__ == "__main__":
    main()
