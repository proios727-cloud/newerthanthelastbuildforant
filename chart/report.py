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


def build(groups, min_train=252, test=21, fee_bps=1.0, slippage_bps=2.0, rotation_folder=None):
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
    return out


def rotation_panel(folder):
    """Stress-test spread and live-calendar replay of the ETF rotation rule, for the page's rotation section."""
    from .forward import ROTATION_RULE, replay_rotation
    from .robust import stress
    bars = {f.stem.upper(): load_csv(f) for f in sorted(pathlib.Path(folder).glob("*.csv"))}
    st = stress(bars, {"lookback": ROTATION_RULE["lookback"], "hold": 21, "top": ROTATION_RULE["top"]})
    rp = replay_rotation(bars)
    return {"rule": ROTATION_RULE, "stress": st,
            "replay": {k: rp[k] for k in ("periods", "completed_periods", "months_beat_basket", "cumulative")}}


PAGE = pathlib.Path(__file__).with_name("report_page.html")


def render_html(data):
    """The scorecard page with `data` embedded; `</` is escaped so the JSON can't close its script tag."""
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.read_text(encoding="utf-8").replace("__REPORT_JSON__", blob)
