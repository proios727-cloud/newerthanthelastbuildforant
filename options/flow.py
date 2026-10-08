"""Flow panel: premium traded, vol:OI, and the unusual-activity discovery ranking.

Honesty rules:
- Premium per contract = mark * volume * 100. Mark is the yfinance mid when
  live, else last trade. Delayed data; the board labels it.
- vol:OI compares today's volume against OI from the prior close (that is what
  free data gives). FRESH means volume >= OI: positioning that did not exist
  yesterday. UNUSUAL = vol:OI >= 1.0 on an OTM contract.
- The discovery score ranks attention, not edge. It is a discovery feed, not a
  signal.
"""
from dataclasses import dataclass


def _otm_distance(strike, spot, kind):
    if kind == "call":
        return (strike - spot) / spot
    return (spot - strike) / spot


@dataclass
class ContractFlow:
    strike: float
    kind: str
    expiry: str
    volume: int
    oi: int
    vol_oi: float
    premium: float
    otm_distance: float
    mark: float
    fresh: bool
    unusual: bool
    score: float


def contract_flows(chain):
    """List[ContractFlow] for contracts with any volume, sorted by score desc."""
    spot = chain["spot"]
    out = []
    for c in chain["contracts"]:
        vol, oi = c.get("volume") or 0, c.get("open_interest") or 0
        if vol <= 0:
            continue
        mark = c.get("mark") or 0.0
        premium = mark * vol * 100
        vol_oi = vol / oi if oi > 0 else None
        otm = _otm_distance(c["strike"], spot, c["option_type"])
        fresh = oi > 0 and vol >= oi
        unusual = (vol_oi is not None and vol_oi >= 1.0 and otm > 0.001)
        # discovery score: premium (log-ish scale) x vol:OI freshness
        vol_oi_s = min(vol_oi, 5.0) if vol_oi is not None else 0.25
        score = (premium ** 0.5) * vol_oi_s
        out.append(ContractFlow(
            strike=c["strike"], kind=c["option_type"], expiry=c.get("expiration", ""),
            volume=vol, oi=oi, vol_oi=vol_oi, premium=premium,
            otm_distance=otm, mark=mark, fresh=fresh, unusual=unusual, score=score,
        ))
    out.sort(key=lambda f: f.score, reverse=True)
    return out


def premium_split(chain):
    """{call_premium, put_premium, net_premium} dollars traded today."""
    call = put = 0.0
    for c in chain["contracts"]:
        vol = c.get("volume") or 0
        if vol <= 0:
            continue
        p = (c.get("mark") or 0.0) * vol * 100
        if c["option_type"] == "call":
            call += p
        else:
            put += p
    return {"call_premium": call, "put_premium": put, "net_premium": call - put}


def discovery(chain, top=12, only_unusual=False):
    flows = contract_flows(chain)
    if only_unusual:
        flows = [f for f in flows if f.unusual]
    return flows[:top]


def otm_walls(chain, by_strike_gex):
    """OTM-ish framing for the board: the strikes above/below spot holding the
    largest call/put GEX. by_strike_gex: {strike: (call_gex, put_gex)}."""
    spot = chain["spot"]
    above = {s: v[0] for s, v in by_strike_gex.items() if s > spot and v[0] > 0}
    below = {s: -v[1] for s, v in by_strike_gex.items() if s < spot and v[1] < 0}
    call_wall = max(above, key=above.get) if above else None
    put_wall = max(below, key=below.get) if below else None
    return call_wall, put_wall