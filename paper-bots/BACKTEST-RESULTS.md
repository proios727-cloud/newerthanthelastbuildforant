# Real-data crypto research results

Kraken public saved OHLC snapshot. Hypothetical fills, not account returns. Each asset/timeframe uses its own $1,000 simulation and a 10% maximum total entry-cost allocation. These results are not a joint portfolio. Fees 0.80% per side; adverse slippage reserve 0.05% per side. Alternative 2% cost-cap experiments are not the deployable default.

| Asset | Signal | Fixed hypothesis | Held-out net PnL | Trades | Sampled max drawdown |
|---|---|---|---:|---:|---:|
| BTC/USD | 60 min | ema_cross | $-1.09 | 2 | 0.24% |
| BTC/USD | 60 min | pullback | $-1.09 | 2 | 0.22% |
| BTC/USD | 60 min | breakout | $-4.52 | 3 | 0.55% |
| BTC/USD | 60 min | Buy-and-hold, same 10% cost budget | $-3.20 | — | — |
| BTC/USD | 240 min | ema_cross | $4.72 | 1 | 0.28% |
| BTC/USD | 240 min | pullback | $-12.79 | 6 | 1.59% |
| BTC/USD | 240 min | breakout | $-6.05 | 4 | 0.93% |
| BTC/USD | 240 min | Buy-and-hold, same 10% cost budget | $6.29 | — | — |
| SOL/USD | 60 min | ema_cross | $-12.28 | 5 | 1.31% |
| SOL/USD | 60 min | pullback | $-5.34 | 2 | 0.54% |
| SOL/USD | 60 min | breakout | $-5.40 | 2 | 0.57% |
| SOL/USD | 60 min | Buy-and-hold, same 10% cost budget | $-8.25 | — | — |
| SOL/USD | 240 min | ema_cross | $6.23 | 1 | 0.00% |
| SOL/USD | 240 min | pullback | $-13.74 | 7 | 1.58% |
| SOL/USD | 240 min | breakout | $-15.77 | 5 | 1.63% |
| SOL/USD | 240 min | Buy-and-hold, same 10% cost budget | $9.40 | — | — |

The 1h evaluation has 240 bars (about 10 days); the 4h evaluation has 240 bars (about 40 days). One profitable trade cannot establish an edge. Default 0.5% cost-cap variants placed zero trades because modeled round-trip costs are about 1.7%.

Replay uses completed signals and next-bar opens, conservative stop-first OHLC ordering, no impossible same-bar reentry after an intrabar exit, and forced end-of-window liquidation. It lacks historical book depth, queue position, exact spreads, venue minimum/precision and latency modeling. Drawdown is sampled at bar close, so intrabar drawdown can be worse. Runtime and historical warmup requirements differ. This is an initial comparison, not a validation certificate.

Recommendation: retain 4h trend as a research candidate and collect longer independently held-out data. Do not promote these results to live capital. Sports has engineering/fixture validation but no demonstrated historical profitable strategy record.
