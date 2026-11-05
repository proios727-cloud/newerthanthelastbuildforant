---
title: Gamma Scalping
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [options, strategy, volatility]
---

# Gamma Scalping

"Buy dips, sell rips" with a long ATM straddle. Long gamma from the straddle means delta
grows as the underlying moves; rehedging that delta locks in realized-volatility profits.

- **Edge:** realized vol > implied vol paid for the straddle.
- **Risks:** directional drift, gap moves, and theta bleed while waiting.
- **Best in:** choppy, volatile markets with frequent small moves.
- **In [[456cash]]:** entry on high-IV ATM straddle, exit after gamma profits with RSI
  neutral; 40% of the combined ensemble. Backtest claims 18–25% annual return, Sharpe
  1.2–1.5, 52–58% win rate, −8–12% max drawdown — but see the data caveat in [[overview]].

Related: [[options-greeks]], [[theta-decay]] (the opposite posture — short gamma, long theta).
([[src-2026-07-31-options-scalping-backtest]])
