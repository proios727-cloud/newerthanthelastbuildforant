---
title: King Nodes
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [options, dealer-positioning, levels]
---

# King Nodes

[[456cash]]'s term for significant price levels overlaid on the Greeks heatmap:
underlying spot (◆ blue), resistance (▲ red), support (▼ green), and the ATM pivot
(◆ yellow). Auto-detected by the heatmap's data service.

Used to identify:
- **Gamma flip zones** — where position deltas reverse; visually, sharp color transitions
  between strikes and large opposite-sign ATM positions on call vs put sides.
- **High-probability reversal areas** and expected-direction barriers.
- **Volatility magnets** — concentrated [[options-greeks|gamma]] near a level implies
  volatility around it; consolidation near a king node often precedes a move.

Reading the skew: positive skew concentrated in resistance levels suggests bullish
pressure building into supply; skew in support levels suggests bearish pressure onto demand.

Related: [[options-greeks]], [[gamma-scalping]].
([[src-2026-07-31-456cash-greeks-heatmap]])
