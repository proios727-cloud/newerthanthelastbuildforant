"""Tests for the options discovery board: collector format, flow math,
setup states, board validator."""
import json
import math
import pathlib
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from options import gex_by_strike, gex_map, greeks, load_chain  # noqa: E402
from options.flow import contract_flows, discovery, premium_split  # noqa: E402
from options.setup_scan import scan  # noqa: E402


def _chain(spot=100.0, contracts=None):
    return {"symbol": "TEST", "source": "test", "spot": spot,
            "captured_at": "2026-10-08T10:00:00-04:00",
            "snapshot_date": "2026-10-08",
            "contracts": contracts or []}


def test_recorded_chain_format_compatibility():
    """The recorded Aug 3 chain must load and map through the same code path
    the live collector feeds."""
    chain = load_chain("SPY-2026-08-03T1506.json")
    m = gex_map(chain)
    assert m.net > 0  # that snapshot was positive gamma
    assert m.king == 755.0
    assert m.call_wall == 755.0
    assert m.put_wall == 748.0


def test_collector_contract_shape():
    """A contract produced by options.collector must carry every field
    gex_by_strike/flow need."""
    c = {"strike": 105.0, "option_type": "call", "expiration": "2026-10-09",
         "bid": 1.0, "ask": 1.2, "mark": 1.1, "iv": 0.2,
         "gamma": greeks(100, 105, 0.1, 0.2, "call").gamma,
         "open_interest": 500, "volume": 800, "bid_size": None, "ask_size": None,
         "delta": None, "theta": None, "vega": None}
    chain = _chain(contracts=[c])
    by = gex_by_strike(chain)
    assert 105.0 in by and by[105.0][0] > 0  # call gamma adds
    flows = contract_flows(chain)
    assert len(flows) == 1
    f = flows[0]
    assert f.fresh is True          # vol 800 >= oi 500
    assert f.vol_oi == pytest.approx(1.6)
    assert f.premium == pytest.approx(1.1 * 800 * 100)
    assert f.otm_distance == pytest.approx(0.05)  # call strike above spot


def test_flow_premium_split_and_flags():
    contracts = [
        {"strike": 90.0, "option_type": "put", "bid": 2, "ask": 2.2, "mark": 2.1,
         "iv": 0.3, "gamma": 0.05, "open_interest": 100, "volume": 50, "expiration": ""},
        {"strike": 110.0, "option_type": "call", "bid": 1, "ask": 1.1, "mark": 1.05,
         "iv": 0.3, "gamma": 0.04, "open_interest": 10, "volume": 30, "expiration": ""},
    ]
    chain = _chain(contracts=contracts)
    prem = premium_split(chain)
    assert prem["call_premium"] == pytest.approx(1.05 * 30 * 100)
    assert prem["put_premium"] == pytest.approx(2.1 * 50 * 100)
    assert prem["net_premium"] < 0  # puts dominate
    flows = contract_flows(chain)
    fresh = [f for f in flows if f.fresh]
    unusual = [f for f in flows if f.unusual]
    assert any(f.strike == 110.0 for f in fresh)   # 30 vol >= 10 oi, OTM
    assert any(f.strike == 110.0 for f in unusual)  # vol:oi 3.0 >= 1.0 OTM


def test_setup_scan_states_on_synthetic():
    """Positive gamma, spot at the king -> king ARMED, gap_fill gated by gap."""
    contracts = []
    for k in (98, 99, 100, 101, 102):
        for kind in ("call", "put"):
            gamma = 0.05 if kind == "call" else 0.05 if k != 100 else 0.04
            oi = 1000 if kind == "call" else 800
            contracts.append({"strike": float(k), "option_type": kind, "bid": 1,
                              "ask": 1, "mark": 1, "iv": 0.25, "gamma": gamma,
                              "open_interest": oi, "volume": 10, "expiration": ""})
    chain = _chain(spot=100.0, contracts=contracts)
    m = gex_map(chain)
    assert m.net > 0
    states = {s.setup: s for s in scan(chain, m, rvol=0.5, gap=-0.001)}
    assert states["king_rejection"].state == "ARMED"
    assert states["gap_fill"].state == "OFF"        # gap too small
    assert states["hedge_exhaustion"].state == "N/A"  # positive gamma
    states2 = {s.setup: s for s in scan(chain, m, rvol=0.5, gap=-0.01)}
    assert states2["gap_fill"].state == "ARMED"     # meaningful gap now


def test_board_validator_refuses_broken_snapshot(tmp_path):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
    import importlib
    bb = importlib.import_module("build_gex_board") if "build_gex_board" in sys.modules \
        else importlib.import_module("scripts.build_gex_board")
    bad = {"symbols": {"SPY": {"spot": 100}}}  # missing everything else
    assert bb.validate(bad), "validator must flag missing keys"
    good = {"symbols": {"SPY": {
        "spot": 100, "net_gex": 1e9, "regime": "positive_gamma", "walls": {},
        "bars": [{"strike": 100.0, "call": 5e8, "put": -2e8}],
        "flows": [], "setups": [], "premium": {}, "rvol": None, "note": "test"}}}
    assert not bb.validate(good), "valid snapshot must pass"
    html = bb.render(good)
    assert "GEX / FLOW DISCOVERY BOARD" in html
    assert "intelligence, not signals" in html