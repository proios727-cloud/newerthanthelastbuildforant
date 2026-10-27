---
title: Options Greeks
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [options, greeks]
---

# Options Greeks

Sensitivities of an option's price, computed in [[456cash]] via Black-Scholes.

- **Delta (Δ)** — price change per $1 move in the underlying. 0→1 calls, −1→0 puts.
  Hedged away in [[gamma-scalping]] by trading the underlying.
- **Gamma (Γ)** — delta change per $1 move; always positive for long options, peaks near
  ATM. High gamma → frequent rehedging → the profit engine of [[gamma-scalping]]. Sharp
  gamma sign transitions across strikes mark flip zones (see [[king-nodes]]).
- **Vega (ν)** — price change per 1% IV move. Long low IV / short high IV is
  [[vega-reversion]]. Vega concentration in near-dated expirations flags IV-crush risk
  around earnings/events.
- **Theta (Θ)** — daily time decay; negative for long options. Harvested by
  [[theta-decay]] via short premium structures.
- **Rho (ρ)** — rate sensitivity; negligible for short-dated scalping.

Formulas used in [[456cash]]: Delta = N(d1); Gamma = n(d1)/(S·σ·√T); vega/theta/rho from
full Black-Scholes; IV solved by Newton-Raphson.
([[src-2026-07-31-options-scalping-backtest]], [[src-2026-07-31-456cash-greeks-heatmap]])
