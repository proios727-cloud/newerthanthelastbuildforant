"""Build the data behind the visual results page: every scan entry with its weekly equity curve vs buy-and-hold.

`python3 -m chart report FOLDER... --out report.json` runs the same rolling walk-forward as `chart scan` on every CSV in
each folder (research mode) and writes compact JSON: verdicts, stats, and curves sampled every 5 sessions.
"""
import json
import pathlib
from datetime import datetime, timezone

from . import load_csv, rotate
from .scan import basket_entry, entry
from .sweep import GRIDS, rolling_walk_forward

STEP = 5


def _sample(curve):
    idx = list(range(0, len(curve["dates"]), STEP))
    if idx[-1] != len(curve["dates"]) - 1:
        idx.append(len(curve["dates"]) - 1)
    s0, h0 = curve["strategy"][0], curve["hold"][0]
    return {"dates": [curve["dates"][i] for i in idx],
            "strategy": [round(curve["strategy"][i] / s0, 4) for i in idx],
            "hold": [round(curve["hold"][i] / h0, 4) for i in idx]}


def build(groups, min_train=252, test=21, fee_bps=1.0, slippage_bps=2.0, rotation_folder=None, longrun_folder=None,
          forward_dir=None):
    """groups: {group name: folder}. Each folder is scanned on its own, and gets its own basket rotation."""
    kw = {"min_train": min_train, "test": test, "fee_bps": fee_bps, "slippage_bps": slippage_bps}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "settings": kw, "groups": []}
    for name, folder in groups.items():
        files = sorted(pathlib.Path(folder).glob("*.csv"))
        bars = {f.stem.upper(): load_csv(f) for f in files}
        entries = []
        for sym, b in bars.items():
            for strat in GRIDS:
                e = entry(sym, b, strat, **kw)
                e["group"] = name
                e["curve"] = _sample(rolling_walk_forward(b, strat, **kw)["curve"])
                entries.append(e)
        if len(bars) >= 2:
            e = basket_entry(bars, **kw)
            e["group"] = name
            e["curve"] = _sample(rotate.rolling(rotate.align(bars), **kw)["curve"])
            entries.append(e)
        out["groups"].append({"name": name, "symbols": sorted(bars), "entries": entries,
                              "data_through": max(b[-1].ts for b in bars.values())})
    if rotation_folder:
        out["rotation"] = rotation_panel(rotation_folder)
    if longrun_folder:
        from .longrun import run
        out["longrun"] = run(longrun_folder)
    if forward_dir is not None:
        out["forward"] = forward_panel(forward_dir)
    return out


def forward_panel(folder):
    """The live forward logs' reports (ROTATION.json, ROTATION_TREND200.json from the shadow-data branch), if present."""
    from datetime import date
    from .doctor import next_decision
    read = lambda n: json.loads((pathlib.Path(folder) / n).read_text()) if (pathlib.Path(folder) / n).exists() else None
    return {"rule": read("ROTATION.json"), "trend200": read("ROTATION_TREND200.json"),
            "next_decision": next_decision(date.today()).isoformat()}


ROTATION_VARIANTS = (("Adopted rule", {}), ("Hysteresis: keep while in top 4", {"buffer": 1}),
                     ("Hysteresis: keep while in top 5", {"buffer": 2}), ("Basket trend filter, 150 days", {"trend": 150}),
                     ("Basket trend filter, 200 days", {"trend": 200}))


def _month_end_drawdown(periods, key):
    eq = peak = 1.0
    worst = 0.0
    for p in periods:
        eq *= 1 + p[key]
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def rotation_variants(bars, aligned):
    """Each variant of the rule scored the same two ways: every rebalance day at two cost levels, and the replay."""
    from .forward import ROTATION_RULE, replay_rotation
    from .robust import day_sweep
    base = {"lookback": ROTATION_RULE["lookback"], "hold": 21, "top": ROTATION_RULE["top"]}
    out = []
    for label, extra in ROTATION_VARIANTS:
        lo = day_sweep(aligned, fee_bps=1, slippage_bps=2, **base, **extra)
        hi = day_sweep(aligned, fee_bps=10, slippage_bps=10, **base, **extra)
        rp = replay_rotation(bars, **extra)
        out.append({"label": label, "params": extra, "cagr_low_cost": lo["cagr"]["median"],
                    "cagr_high_cost": hi["cagr"]["median"], "drawdown_median": lo["max_drawdown"]["median"],
                    "trades_median": lo["trades_median"], "replay_rule": rp["cumulative"]["rule"],
                    "replay_basket": rp["cumulative"]["basket"], "replay_ahead": rp["months_beat_basket"],
                    "replay_months": rp["completed_periods"],
                    "replay_drawdown": round(_month_end_drawdown(rp["periods"], "rule"), 5)})
    return out


def rotation_panel(folder):
    """Stress-test spread and live-calendar replay of the ETF rotation rule, for the page's rotation section."""
    from .forward import ROTATION_RULE, replay_rotation
    from .robust import stress
    from .rotate import align
    bars = {f.stem.upper(): load_csv(f) for f in sorted(pathlib.Path(folder).glob("*.csv"))}
    st = stress(bars, {"lookback": ROTATION_RULE["lookback"], "hold": 21, "top": ROTATION_RULE["top"]})
    rp = replay_rotation(bars)
    return {"rule": ROTATION_RULE, "stress": st,
            "replay": {k: rp[k] for k in ("periods", "completed_periods", "months_beat_basket", "cumulative")},
            "variants": rotation_variants(bars, align(bars))}


PAGE = pathlib.Path(__file__).with_name("report_page.html")


def render_html(data):
    """The scorecard page with `data` embedded; `</` is escaped so the JSON can't close its script tag."""
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.read_text(encoding="utf-8").replace("__REPORT_JSON__", blob)
