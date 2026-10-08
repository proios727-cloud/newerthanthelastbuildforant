"""Integration test: one scripted loop day, end to end through the funnel.

Fake clock + monkeypatched collectors so no network is needed:
  carry signal fires -> risk PASS (sized) -> preview queued -> approve with
  EXECUTE -> paper fill lands in ledger -> funnel counts increment.

Also asserts through the loop: stale quotes refused, exits bypass halts.
"""
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fund import clock, config, funnel, risk  # noqa: E402
from fund.ledger import Ledger, parse_ts  # noqa: E402
from fund.propose import propose  # noqa: E402
from strategies.s1_carry import signal as carry  # noqa: E402

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)  # crypto trades 24/7; equity open too (08:00 ET)
Q = {"price": 83000.0, "bid": 82990.0, "ask": 83010.0, "ts": NOW.isoformat()}
FUNDING = {"rate_8h": 0.00008, "ts": NOW.isoformat()}  # above the 0.005%/8h floor


class FakeCollectors:
    """Monkeypatch target: deterministic quotes + funding, no network."""
    store = {"quotes": {}, "funding": {}}

    @staticmethod
    def quote(symbol, cfg):
        return dict(Q) if symbol == "BTC/USD" else None

    @staticmethod
    def get_stored_quote(symbol):
        return FakeCollectors.store["quotes"].get(symbol)

    @staticmethod
    def funding_rate(symbol):
        return dict(FUNDING) if symbol == "BTC/USD" else None

    @staticmethod
    def mark_all(cfg, symbols=None):
        return {"BTC/USD": dict(Q)}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """Isolated ledger/previews + faked collectors, real desk.json config."""
    monkeypatch.setattr("data.collectors.quote", FakeCollectors.quote)
    monkeypatch.setattr("data.collectors.get_stored_quote", FakeCollectors.get_stored_quote)
    monkeypatch.setattr("data.collectors.funding_rate", FakeCollectors.funding_rate)
    monkeypatch.setattr("data.collectors.mark_all", FakeCollectors.mark_all)
    # funnel log to tmp so counts are clean
    monkeypatch.setattr(funnel, "EVENTS", tmp_path / "events.jsonl")
    monkeypatch.setattr("fund.propose.collectors", FakeCollectors)
    cfg = config.load()
    L = Ledger(cfg.starting_nav)
    previews = tmp_path / "previews.json"
    return cfg, L, previews, tmp_path


def test_full_loop_day(fresh):
    """Signal -> proposal -> EXECUTE -> fill -> funnel counts -> receipt data."""
    cfg, L, previews, tmp = fresh

    # 1. strategy emits a signal with the faked funding
    sigs = carry.signals(cfg)
    assert sigs, "funding 0.008%/8h should fire the carry signal"
    sig = sigs[0]
    assert sig["symbol"] == "BTC/USD" and sig["side"] == "sell"
    assert sig["conviction"] > 0

    # 2. propose: risk sizes it against a fresh (faked) quote
    before = funnel.counts()
    pv = propose(sig, L, cfg, previews, now=NOW)
    assert pv["status"] == "awaiting_approval"
    assert pv["qty"] * 83000 <= 0.05 * cfg.starting_nav * 1.01  # sized to the 5% cap

    # 3. EXECUTE approval -> paper fill
    from fund import preview as preview_mod
    rec = preview_mod.approve(pv, cfg.approval_word, L, cfg, NOW)
    assert rec["symbol"] == "BTC/USD"
    funnel.log_stage("fill", symbol="BTC/USD", id=pv["id"])
    assert L.qty("BTC/USD") < 0, "carry sells (shorts) the perp"
    assert L.fills, "paper fill landed in the ledger"

    # 4. funnel counts incremented across the day
    after = funnel.counts()
    assert after["Scanned"] >= 1
    assert after["Risk-passed"] >= 1
    assert after["Previewed"] >= 1
    assert after["Filled (paper)"] >= 1
    assert after["Scanned"] > before["Scanned"]


def test_wrong_word_refused(fresh):
    cfg, L, previews, tmp = fresh
    sig = {"symbol": "BTC/USD", "side": "sell", "qty_hint": 0.05,
           "conviction": 0.5, "reason": "t", "strategy": "s1_carry"}
    pv = propose(sig, L, cfg, previews, now=NOW)
    from fund import preview as preview_mod
    with pytest.raises(preview_mod.GateError):
        preview_mod.approve(pv, "execute", L, cfg, NOW)  # lowercase must fail


def test_stale_quote_refused(fresh):
    """A quote older than max_quote_age_sec must not produce a preview."""
    cfg, L, previews, tmp = fresh
    old = dict(Q)
    old["ts"] = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc).isoformat()
    FakeCollectors.store["quotes"]["BTC/USD"] = old
    # both stored AND live paths must be stale: live fetch returns the old quote too
    def stale_quote(symbol, cfg2):
        return dict(old)
    import data.collectors as colls
    orig_quote = colls.quote
    colls.quote = stale_quote
    import fund.propose as propose_mod
    propose_mod.collectors.quote = stale_quote
    try:
        sig = {"symbol": "BTC/USD", "side": "sell", "qty_hint": 0.05,
               "conviction": 0.5, "reason": "t", "strategy": "s1_carry"}
        with pytest.raises(Exception):
            propose(sig, L, cfg, previews, now=NOW)
    finally:
        colls.quote = orig_quote
        propose_mod.collectors.quote = orig_quote
    FakeCollectors.store["quotes"].pop("BTC/USD", None)


def test_exit_bypasses_day_loss_halt(fresh):
    """Once the day-loss halt trips, exits still pass; new entries veto."""
    cfg, L, previews, tmp = fresh
    # open a short first
    sig = {"symbol": "BTC/USD", "side": "sell", "qty_hint": 0.05,
           "conviction": 0.5, "reason": "t", "strategy": "s1_carry"}
    pv = propose(sig, L, cfg, previews, now=NOW)
    from fund import preview as preview_mod
    preview_mod.approve(pv, cfg.approval_word, L, cfg, NOW)
    # force a day loss beyond the halt
    L.day = {"date": clock.fund_day(NOW), "start_nav": L.nav() * 1.10}  # ~ -9% day
    o_exit = risk.Order("BTC/USD", "buy", abs(L.qty("BTC/USD")) * 0.5, 83000, NOW,
                        bid=Q["bid"], ask=Q["ask"])
    v = risk.check(o_exit, L, cfg, NOW)
    assert v.passed and v.reducing, "exits must bypass the day-loss halt"
    o_new = risk.Order("BTC/USD", "sell", 0.001, 83000, NOW, bid=Q["bid"], ask=Q["ask"])
    v2 = risk.check(o_new, L, cfg, NOW)
    assert not v2.passed and v2.rules[0][0] == "day_loss_halt", "new entries must halt"


def test_unknown_strategy_refused(fresh):
    cfg, L, previews, tmp = fresh
    sig = {"symbol": "BTC/USD", "side": "sell", "qty_hint": 0.05,
           "conviction": 0.5, "reason": "t", "strategy": "not_a_strategy"}
    with pytest.raises(ValueError):
        propose(sig, L, cfg, previews, now=NOW)