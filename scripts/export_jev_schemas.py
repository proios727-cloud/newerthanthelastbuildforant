"""Export the JEV batteries in fund/battery.py to jev/schemas/<version>.json (the exact request body + code policy).

    python scripts/export_jev_schemas.py          # rewrite; tests/test_verify.py fails if the files drift from code
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import judge  # noqa: E402
from fund import battery  # noqa: E402

OUT = ROOT / "jev" / "schemas"


def schemas():
    client = judge.HttpClient("unused")
    return {
        battery.SCHEMA: {"version": battery.SCHEMA, "used_by": ["put30d-v1", "pcs12-v1"],
                         "state_inputs": ["symbol", "headlines (cleaned, <=20)", "market", "trade"],
                         "questions": client.payload({}, battery.QUESTIONS)["questions"],
                         "veto": [{"question": q, "rule": r, "bad_p_at_least": t} for q, r, t in battery.VETO],
                         "escalate_below": battery.ESCALATE_BELOW, "role": "veto-only; never sizes or places orders"},
        battery.TREND_SCHEMA: {"version": battery.TREND_SCHEMA, "used_by": ["trend-etf-v1 (buys only)"],
                               "state_inputs": ["asset", "order", "spec", "headlines (cleaned, <=20)"],
                               "questions": client.payload({}, battery.TREND_QUESTIONS)["questions"],
                               "veto": [{"question": q, "rule": r, "bad_p_at_least": t} for q, r, t in battery.TREND_VETO],
                               "role": "veto-only; sells, stops and kills never go to JEV"},
    }


def render(s):
    return json.dumps(s, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for v, s in schemas().items():
        (OUT / f"{v}.json").write_text(render(s), encoding="utf-8")
        print(OUT / f"{v}.json")
