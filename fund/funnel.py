"""Funnel observability: count stage transitions from ledger/events.jsonl.

Stages tracked (event kind -> funnel stage):
  scan_hit      -> Scanned          (a strategy signal was observed)
  thesis        -> Thesis written   (analyst logged a thesis - model or stub note)
  risk_pass     -> Risk-passed      (risk.check returned PASS)
  preview       -> Previewed        (a preview was built and queued)
  fill          -> Filled (paper)   (approved with EXECUTE, paper fill landed)

counts() reads the whole event log; day(date) filters to one fund-day.
Every number the board shows comes from these observed events - nothing estimated.
"""
import json
import pathlib
from collections import Counter

from . import clock
from .config import ROOT
from .ledger import parse_ts

EVENTS = ROOT / "ledger" / "events.jsonl"

KIND_TO_STAGE = {
    "scan_hit": "Scanned",
    "thesis": "Thesis written",
    "risk_pass": "Risk-passed",
    "preview": "Previewed",
    "fill": "Filled (paper)",
}


def _events(day=None):
    if not EVENTS.exists():
        return
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if day is not None:
            ts = ev.get("ts")
            if not ts or clock.fund_day(parse_ts(ts)) != day:
                continue
        yield ev


def counts(day=None):
    """{stage: count} from the event log. Day filter optional."""
    c = Counter()
    for ev in _events(day):
        stage = KIND_TO_STAGE.get(ev.get("kind"))
        if stage:
            c[stage] += 1
    return {stage: c.get(stage, 0) for stage in KIND_TO_STAGE.values()}


def log_stage(kind, **data):
    """Append a funnel stage event (called by the loop/propose layers)."""
    EVENTS.parent.mkdir(exist_ok=True)
    payload = {"ts": clock.now().isoformat(), "kind": kind, **data}
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")