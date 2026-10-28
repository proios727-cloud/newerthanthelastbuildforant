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

## Variants tested: no change to the rule

Two changes were tested to widen the thin after-cost edge. Each was scored from all 21 rebalance days and on the
live-calendar replay (`chart stress --buffer N` / `--trend N`; the scorecard's rotation panel shows the same table).

| Variant | CAGR median, 1+2 bp | 10+10 bp | Drawdown median | Trades | Replay vs basket | Replay drawdown |
|---|---|---|---|---|---|---|
| **Adopted rule** | **+13.8%** | **+12.0%** | −12.7% | 31 | **+49.4% vs +43.1%** | −7.5% |
| Hysteresis: keep a fund while it ranks in the top 4 | +10.4% | +8.8% | −13.5% | 28 | +34.0% | −10.6% |
| Hysteresis: top 5 | +8.0% | +6.6% | −14.1% | 27 | +30.9% | −10.0% |
| Basket below its 150-day average → cash | +12.2% | +10.5% | −9.7% | 28 | +46.0% | −6.7% |
| Basket below its 200-day average → cash | +12.7% | +10.8% | −12.7% | 31 | +39.2% | −7.5% |

- **Hysteresis is rejected.** It saves only about 3 trades in two years, and holding fading funds longer costs 3–6
  points a year. The month-to-month swaps are where the rule's return comes from.
- **The trend filter is not adopted.** At 150 days it trims the median drawdown from −12.7% to −9.7%, at a cost of about
  1.5 points a year. At 200 days it helps nothing. A gain that depends on the filter length is fitting, and this window
  holds no bear market to test a trend filter on. Revisit it with older data.

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

**What the job produces each month:** on the first session of the month, `chart forward rotation-tickets` turns the
decision into paper tickets (`rotation_tickets.jsonl` on `shadow-data`). It sizes buys at the 5% position cap of
`starting_nav` in whole shares, with a limit 0.5% above the decision close. It sells only funds leaving the top 3, with a
limit 0.5% below, and leaves kept funds alone. The tickets are review material for analyst → Risk Officer → trader. Nothing
is previewed or sent. `chart doctor` runs first and fails the job if the key is missing or bars are more than 3 weekdays
old, so a missed month is visible.
