# Rule: two variants of the ETF rotation rule (fixed 2026-11-05, before any results were run)

**Live rule (the reference):**
- Rank the basket by 60-session total return.
- Hold the top 3 with positive momentum, in equal weight.
- Decide at the close of the first session of each month and fill at the next open.
- Vetted in `docs/rotation-sleeve.md`.

**Variants, the whole grid, fixed now:**

| Variant | Lookback | Holds | Weekly equivalent |
|---|---|---|---|
| **A** | 120 sessions (about 6 months) | top 3 | 24 weeks |
| **B** | 60 sessions | top 2 | 12 weeks |

Everything else matches the live rule: the same basket, timing, positive-momentum filter and equal weight. No other
lookbacks or holding counts will be run.

**Data:** total-return bars only.
- **Daily:** `chart/data/etf_tr/`, 13 funds.
- **Weekly:** `chart/data/weekly/`, the 11-fund basket from Nov 2004 and the 13-fund basket from Jul 2018.

**Benchmarks:**
- The live rule, run on the same data.
- The equal-weight basket.

**Claim:** a variant is worth shadow-logging only if it improves on the live rule, after 3 bp a side, in both
long-history baskets, in one of two ways:
- a higher CAGR with a worst drawdown no deeper than the live rule's; or
- a worst drawdown at least 3 points shallower, at a CAGR cost of 0.5 points a year or less.

It must also not lose to the live rule in the median rebalance day of the daily stress test. Beating only the basket is not
enough, because the live rule already does that job.

**Robustness:**
- **Daily stress:** `chart stress` on every rebalance day.
  - Report the median and the worst day.
  - Run the cost ladder (1+2, 10+10 and 25+25 bp).
  - Run the remove-one-fund rows.
- **Long history:** `chart.longrun.run`, broken out by stress window: 2008, 2011, 2015–16, 2018 Q4, 2020 and 2022.

**Multiple testing:** 2 variants × 2 baskets is 4 long-history tests, plus 2 daily stress runs. With so few tests,
a pass is not chance by construction. But a one-basket or one-regime pass still counts as a fail.
