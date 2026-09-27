---
title: Theta Decay (short premium)
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [options, strategy, income]
---

# Theta Decay

Sell premium and collect time decay: short OTM strangles / iron condors at 1–2 DTE, exit
at 50% max profit or expiration. Profits when price stays between the short strikes.

- **Edge:** time-value erosion ([[options-greeks|theta]]) in range-bound markets.
- **Risks:** gap moves through a short strike; profits capped, losses aren't (condor wings cap them).
- **Best in:** stable, mean-reverting, low-vol environments.
- **In [[456cash]]:** 40% of the combined ensemble; the backtests' best performer —
  claimed 22–30% return, Sharpe 1.4–1.8, 65–72% win rate, −5–8% max drawdown (data caveat
  in [[overview]]).

Related: [[gamma-scalping]] (mirror-image exposure), [[vega-reversion]].
([[src-2026-07-31-options-scalping-backtest]])
