# Decision: how to paper-trade the ETF rotation rule

**Rule:** rank the 13 research ETFs (11 Select Sector SPDRs, TLT, GLD) by 60-session return, then hold the top 3 that are up, in
equal weight. It decides at the close of the first session of each month and fills at the next open
(`python3 -m chart forward rotation-record`).

**Status: research, paper only.** Nothing here places an order. Any live use still goes through the desk's analyst →
Risk Officer → trader → `EXECUTE` path.

## The evidence

| Test | Rule | Equal-weight basket | Source |
|---|---|---|---|
| Stress test, all 21 rebalance days, Oct 2024 → Oct 2026, 1+2 bp | median **+13.8%/yr** (worst +8.0%) | +9.7%/yr | `chart stress` |
| Same, 10+10 bp | median +12.0%/yr | +9.6%/yr | `chart stress` |
| **Live calendar replay**, first session of each month, Jan 2024 → Oct 2026, before costs | **+15.2%/yr** | +13.5%/yr | `chart forward rotation-replay` |
| Live calendar replay: worst month-end drawdown | −7.5% | −5.7% | same |
| Live calendar replay: months ahead of basket | 17 of 33 | | same |

**Turnover:** it changes about 1.2 of its 3 holdings a month. That costs about **0.3%/yr at 1+2 bp** and **1.9%/yr at
10+10 bp**, so the edge after costs ranges from about **+1.4 points a year** down to **about zero**.

**Caveats:** this is one 3-year window and one market regime. The rule was chosen on the stress-test window, so the
replay isn't fully out of sample. Older regimes (2018, 2020, 2022) need paid historical data.

## Options

| | A. Separate sleeve with its own limits | B. Inside the existing desk caps |
|---|---|---|
| Size | e.g. 20% of NAV, 3 × ~6.7% | 3 × 5% = **15% of NAV** (the per-position cap) |
| Code changes | sleeve-aware limits in `fund/risk.py` and `desk.json`, plus tests | add the 13 ETFs to the `desk.json` universe (each in its own group); no risk-engine change |
| Risk rules | new rules to review and test | the existing, tested rules apply unchanged |
| Expected effect on NAV (if the replay edge holds) | ≈ +0.3 points/yr vs holding the basket | ≈ +0.2 points/yr vs holding the basket |
| What it buys | room to scale later | forward evidence at low engineering and rule risk |

## Recommendation: B, paper only

The edge is thin and cost-sensitive. It doesn't justify writing new risk rules or a looser sleeve. Paper-trading it inside
the existing 5% caps gives the forward record that matters, with no change to the tested risk engine. Revisit option A only
if 6+ months of forward results stay ahead of the basket after costs.

**To proceed with B:** add the ETFs to `desk.json` → `fund.universe` (asset `equity`, one group per fund), then let the
daily `chart-forward` job log decisions. Both need the `ALPHAVANTAGE_API_KEY` repository secret. The universe change is
yours to approve because it changes what the desk may trade.
