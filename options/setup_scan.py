"""Setup scanner: the six heatseeker setups as structure-derived STATES.

This reads the GEX map and, where applicable, flow/gap context, and labels each
setup ARMED / WATCH / OFF / N-A. It never emits a trade signal: the doctrine
requires live intraday confirmations (e.g. RVOL >= 1.4 on the breaking 5m bar,
failed retest) that this scan cannot observe from delayed structure data. The
board shows 'needs live confirm' on every ARMED row for exactly that reason.

Setups (from the heatseeker skill):
  flip_break        spot below the flip, close enough to be live (<0.5%)
  flip_reclaim      spot recently below the flip but back above it
  gap_fill          positive gamma + meaningful gap open vs prior close
  king_rejection    spot within 0.3% of the king node
  air_pocket        a GEX valley between spot and the wall
  hedge_exhaustion negative gamma + RVOL low (dealers not forced yet) -> WATCH
"""
from dataclasses import dataclass

FLIP_LIVE_PCT = 0.5      # flip within 0.5% of spot = live rather than theoretical
KING_NEAR_PCT = 0.3
GAP_MEANINGFUL_PCT = 0.4  # gaps smaller than this are noise
POCKET_MAX_BARS = 6      # an air pocket must sit within this many strikes


@dataclass
class SetupState:
    setup: str
    state: str          # ARMED | WATCH | OFF | N/A
    reason: str


def _pct(a, b):
    return abs(a - b) / b * 100 if b else 0.0


def net_by_strike(chain, by_strike_gex):
    return {s: call + put for s, (call, put) in by_strike_gex.items()}


def scan(chain, gex_map, rvol=None, gap=None):
    """List[SetupState] for the six setups, in canonical order."""
    spot = chain["spot"]
    net = net_by_strike(chain, {s: v for s, v in _by_strike(chain, gex_map).items()})
    states = []

    # 1. flip break / 2. flip reclaim (mutually exclusive live states)
    if gex_map.flip is not None:
        dist = _pct(spot, gex_map.flip)
        if spot < gex_map.flip:
            if dist <= FLIP_LIVE_PCT:
                st = "ARMED"
                states.append(SetupState("flip_break", st,
                    f"spot {spot:.2f} below flip {gex_map.flip:.0f} ({dist:.2f}%); needs live confirm"))
                states.append(SetupState("flip_reclaim", "WATCH",
                    f"watch for a reclaim of {gex_map.flip:.0f}"))
            else:
                states.append(SetupState("flip_break", "OFF",
                    f"flip {gex_map.flip:.0f} is {dist:.2f}% away"))
                states.append(SetupState("flip_reclaim", "OFF", "price well below flip"))
        else:
            states.append(SetupState("flip_break", "OFF", f"price above flip {gex_map.flip:.0f}"))
            if dist <= FLIP_LIVE_PCT:
                states.append(SetupState("flip_reclaim", "WATCH",
                    f"holding above flip {gex_map.flip:.0f} by {dist:.2f}%"))
            else:
                states.append(SetupState("flip_reclaim", "OFF", "price well above flip"))
    else:
        states.append(SetupState("flip_break", "N/A", "no flip in the chain"))
        states.append(SetupState("flip_reclaim", "N/A", "no flip in the chain"))

    # 3. gap fill (positive gamma + gap)
    if gex_map.net > 0 and gap is not None and abs(gap * 100) >= GAP_MEANINGFUL_PCT:
        states.append(SetupState("gap_fill", "ARMED",
            f"positive gamma, gap {gap*100:+.2f}% open; needs live confirm"))
    elif gex_map.net > 0:
        states.append(SetupState("gap_fill", "OFF",
            f"positive gamma but gap {gap*100:+.2f}% too small" if gap is not None
            else "positive gamma; gap unavailable"))
    else:
        states.append(SetupState("gap_fill", "N/A", "negative gamma regime"))

    # 4. king node rejection
    if gex_map.king is not None:
        dist = _pct(spot, gex_map.king)
        if dist <= KING_NEAR_PCT:
            states.append(SetupState("king_rejection", "ARMED",
                f"spot at king node {gex_map.king:.0f} ({dist:.2f}%); needs live confirm"))
        else:
            states.append(SetupState("king_rejection", "OFF",
                f"king {gex_map.king:.0f} is {dist:.2f}% away"))
    else:
        states.append(SetupState("king_rejection", "N/A", "no king node"))

    # 5. air pocket: valley between spot and the relevant wall
    pocket = _find_pocket(chain, net, spot, gex_map)
    if pocket:
        states.append(SetupState("air_pocket", "WATCH" if pocket["ahead_of"] == spot else "OFF",
            f"low-gamma pocket {pocket['lo']:.0f}-{pocket['hi']:.0f} toward {pocket['wall']:.0f}"))
    else:
        states.append(SetupState("air_pocket", "OFF", "no low-gamma pocket within range"))

    # 6. hedge exhaustion (negative gamma + volume state)
    if gex_map.net < 0:
        if rvol is not None and rvol < 1.0:
            states.append(SetupState("hedge_exhaustion", "WATCH",
                f"negative gamma, RVOL {rvol:.2f} low - dealers not yet forced"))
        elif rvol is not None:
            states.append(SetupState("hedge_exhaustion", "ARMED",
                f"negative gamma with RVOL {rvol:.2f}; needs live confirm"))
        else:
            states.append(SetupState("hedge_exhaustion", "WATCH",
                "negative gamma; RVOL unavailable"))
    else:
        states.append(SetupState("hedge_exhaustion", "N/A", "positive gamma regime"))

    return states


def _by_strike(chain, gex_map):
    from . import gex_by_strike
    return gex_by_strike(chain)


def _find_pocket(chain, net, spot, gex_map):
    """Look for consecutive strikes with |net GEX| under 10% of the king's,
    between spot and the nearest wall. Returns {lo, hi, wall, ahead_of} or None."""
    strikes = sorted(net)
    if not strikes:
        return None
    king_abs = max(abs(net[s]) for s in strikes) or 1.0
    floor = king_abs * 0.10
    for direction in ("up", "down"):
        wall = gex_map.call_wall if direction == "up" else gex_map.put_wall
        if wall is None:
            continue
        path = [s for s in strikes if (spot < s < wall)] if direction == "up" \
            else [s for s in strikes if (wall < s < spot)]
        if len(path) < 2 or len(path) > POCKET_MAX_BARS + 4:
            continue
        run = []
        for s in path:
            if abs(net[s]) <= floor:
                run.append(s)
            else:
                if len(run) >= 2:
                    return {"lo": run[0], "hi": run[-1], "wall": wall, "ahead_of": spot}
                run = []
        if len(run) >= 2:
            return {"lo": run[0], "hi": run[-1], "wall": wall, "ahead_of": spot}
    return None