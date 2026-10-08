"""Ledger + resolver + report round-trip tests (no network)."""
import datetime as dt
import json
import pathlib
import sys
from datetime import timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from options import ledger as L  # noqa: E402
from options import resolve as R  # noqa: E402
from options import report as RP  # noqa: E402


def _bars(events):
    """events: list of (minutes_after, high, low, close) -> bars dict."""
    base = dt.datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)
    return {
        "t": [base + dt.timedelta(minutes=m) for m, _, _, _ in events],
        "high": [h for _, h, _, _ in events],
        "low": [l for _, _, l, _ in events],
        "close": [c for _, _, _, c in events],
    }


def test_append_and_rows_roundtrip(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = L.append({"ticker": "SPY", "setup": "FR", "source": "test",
                    "signal_price": 770.0, "stop": 768.0, "target": 775.0}, led)
    assert row["outcome"] is None and row["r"] is None
    rows = L.rows(led)
    assert len(rows) == 1 and rows[0]["setup"] == "FR"
    # corrupt line tolerated
    led.write_text(led.read_text() + "not json\n", encoding="utf-8")
    rows = L.rows(led)
    assert len(rows) == 2  # 1 real + 1 corrupt marker
    assert rows[-1]["setup"] == "corrupt_lines"


def test_webhook_parse():
    line = "HEATSEEKER|SPY|FR|A+|590.12|stop=587.4|target=595.0|rvol=2.1|regime=+GEX|vanna=aligned"
    rec = L.parse_webhook(line)
    assert rec == {
        "source": "tv-webhook", "ticker": "SPY", "setup": "FR", "tier": "A+",
        "signal_price": 590.12, "stop": 587.4, "target": 595.0, "rvol": 2.1,
        "regime": "+GEX", "vanna": "aligned",
    }
    assert L.parse_webhook("garbage") is None
    assert L.parse_webhook("HEATSEEKER|short") is None


def test_resolve_target_stop_scratch(tmp_path):
    # long setup: entry 770, stop 768, target 775
    row = {"ticker": "SPY", "setup": "FR", "source": "test", "ts": "2026-10-08T14:00:00+00:00",
           "signal_price": 770.0, "stop": 768.0, "target": 775.0}
    # target hit on bar 2
    b = _bars([(0, 770, 769, 770), (5, 776, 770, 775)])
    assert R.resolve_row(row, b) == ("target", 5.0 / 2.0, "target hit")
    # stop hit first
    b2 = _bars([(0, 770, 769, 770), (5, 770, 767, 768)])
    out, r, note = R.resolve_row(row, b2)
    assert out == "stop" and r == -1.0
    # short setup: entry 770, stop 772, target 765 -> target hit
    srow = {**row, "stop": 772.0, "target": 765.0}
    b3 = _bars([(0, 770, 769, 770), (5, 770, 764, 765)])
    assert R.resolve_row(srow, b3) == ("target", 5.0 / 2.0, "target hit")
    # short stopped
    b4 = _bars([(0, 770, 769, 770), (5, 773, 770, 772)])
    out, r, _ = R.resolve_row(srow, b4)
    assert out == "stop" and r == -1.0
    # nothing happened, < 26h -> open
    assert R.resolve_row(row, _bars([(0, 770, 769, 770)]))[0] == "open"


def test_resolve_all_marks_rows(tmp_path, monkeypatch):
    led = tmp_path / "l.jsonl"
    L.append({"ticker": "SPY", "setup": "FR", "source": "test",
              "ts": "2026-10-08T14:00:00+00:00",
              "signal_price": 770.0, "stop": 768.0, "target": 775.0}, led)
    L.append({"ticker": "QQQ", "setup": "KN", "source": "gex-board",
              "ts": "2026-10-08T14:00:00+00:00"}, led)
    bars = _bars([(0, 770, 769, 770), (5, 776, 770, 775)])
    monkeypatch.setattr(R, "_bars_since", lambda ticker, since: bars)
    resolved = R.resolve_all(L, path=led)
    outcomes = {(row["setup"]): outcome for _, row, outcome, _, _ in resolved}
    assert outcomes == {"FR": "target", "KN": "no-trade"}
    after = L.rows(led)
    assert after[0]["outcome"] == "target" and abs(after[0]["r"] - 2.5) < 1e-9
    assert after[1]["outcome"] == "no-trade"
    # idempotent: second run resolves nothing new
    assert R.resolve_all(L, path=led) == []


def test_weekly_report_renders(tmp_path):
    led = tmp_path / "l.jsonl"
    L.append({"ticker": "SPY", "setup": "FR", "source": "test",
              "ts": "2026-10-08T14:00:00+00:00", "signal_price": 770.0,
              "stop": 768.0, "target": 775.0, "outcome": "target", "r": 2.5}, led)
    md, per_setup = RP.render(L.rows(led), "2026-W41")
    assert "Options ledger weekly - 2026-W41" in md
    assert "| FR | 1 | 1 | 100% | +2.5 | NO" in md  # under-10 flagged as not evidence
    assert "not evidence" in md


def test_from_snapshot_appends_armed(tmp_path):
    led = tmp_path / "l.jsonl"
    snap = {"captured_at": "2026-10-08T14:53:00-04:00", "symbols": {"SPY": {
        "spot": 772.89, "regime": "negative_gamma",
        "setups": [
            {"setup": "king_rejection", "state": "ARMED", "reason": "spot at king node 773 (0.02%)"},
            {"setup": "air_pocket", "state": "OFF", "reason": "none"},
        ]}}}
    recs = L.from_snapshot(snap, "SPY", path=led)
    assert len(recs) == 1 and recs[0]["setup"] == "king_rejection"
    assert recs[0]["source"] == "gex-board"
    assert recs[0]["outcome"] is None