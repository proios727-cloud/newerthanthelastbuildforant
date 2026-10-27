---
title: Vega Reversion (IV mean reversion)
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [options, strategy, volatility]
---

# Vega Reversion

Trade implied volatility as a mean-reverting series: long options when IV < 25th
percentile, short when IV > 75th percentile; exit when IV reverts to its mean.

- **Edge:** IV percentile extremes tend to revert, especially around earnings cycles.
- **Risks:** IV keeps expanding/contracting against the position; regime shifts.
- **Best around:** pre/post-earnings and volatility events.
- **In [[456cash]]:** 20% of the combined ensemble; weakest claimed stats of the three —
  15–22% return, Sharpe 1.0–1.3, 48–55% win rate, −10–15% max drawdown (data caveat in
  [[overview]]).

Related: [[options-greeks|vega]], [[theta-decay]], [[gamma-scalping]].
([[src-2026-07-31-options-scalping-backtest]])
