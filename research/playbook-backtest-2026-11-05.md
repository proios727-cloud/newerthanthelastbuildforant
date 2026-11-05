# Playbook backtest — BTCUSDT 15m, 2026-05-09 → 2026-11-05 (180 days)

In-sample to 2026-08-25, out-of-sample after. Costs 22 bps round trip (fees 10 bps/side + 2 bps slippage), charged in R. BTC buy-and-hold: +0.4%.

| variant | trades IS | avg R IS | trades OOS | avg R OOS | win OOS | total R OOS | t OOS | max DD R (all) | avg R at 2× cost (all) | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| B0 breakout (live rule) | 158 | -0.947 | 123 | -1.024 | 25% | -125.9 | -8.22 | 276.5 | -1.790 | reject |
| B1 + volume ≥1.5× | 119 | -0.815 | 86 | -0.878 | 28% | -75.5 | -5.80 | 175.1 | -1.555 | reject |
| B2 + ADX ≥25 | 146 | -0.947 | 104 | -0.980 | 26% | -101.9 | -7.15 | 241.1 | -1.734 | reject |
| B3 + after squeeze (BB width bottom 20%) | 52 | -0.891 | 35 | -1.130 | 29% | -39.5 | -4.36 | 88.0 | -2.043 | reject |
| B4 + volume ≥1.5× + squeeze | 32 | -1.048 | 18 | -1.260 | 22% | -22.7 | -3.80 | 58.4 | -2.149 | reject |
| B5 + volume ≥1.5× + above EMA200 | 110 | -0.764 | 80 | -0.794 | 30% | -63.5 | -5.00 | 150.1 | -1.462 | reject |
| B6 B1 with 2×ATR target | 126 | -0.736 | 92 | -0.818 | 35% | -75.2 | -6.48 | 169.1 | -1.481 | reject |
| M0 mean reversion (live rule) | 279 | -0.732 | 166 | -0.630 | 39% | -104.5 | -6.29 | 312.8 | -1.408 | reject |
| M1 + ADX ≤20 | 19 | -1.011 | 13 | -0.356 | 62% | -4.6 | -1.34 | 24.2 | -1.562 | too few trades |
| M2 + RSI <25 | 181 | -0.674 | 104 | -0.605 | 38% | -63.0 | -4.43 | 188.7 | -1.338 | reject |
| M3 + ADX ≤20 + above EMA200 | 6 | -0.560 | 2 | -0.520 | 50% | -1.0 | -0.53 | 4.9 | -1.344 | too few trades |
| M4 + ADX ≤20 + no volume spike (≤2×) | 17 | -1.169 | 12 | -0.259 | 67% | -3.1 | -0.96 | 23.3 | -1.642 | too few trades |

12 variants were tested on the same data, so roughly one in 12 would look good by luck at 1 in 20 odds; a t-statistic of about 2.7 or more out-of-sample is the bar for trusting one.

Candidates: none.

## Gross vs net, by timeframe (same 12 variants)

| timeframe | history | median stop distance | cost per trade | best OOS net result with ≥15 OOS trades |
|---|---|---|---|---|
| 15m (live) | 180 days | 0.33% of price | ≈0.66R | M2 RSI<25: −0.605R (t −4.4) |
| 1h | 365 days | 0.86% | ≈0.26R | M2 RSI<25: −0.114R (t −0.6) |
| 4h | 730 days | 1.79% | ≈0.12R | M2 RSI<25: +0.001R (t +0.0); breakouts positive in-sample, negative out-of-sample |

Gross (before costs) the 15m breakout variants average −0.06 to −0.19R and mean reversion +0.02 to +0.07R: there is little or no edge to filter, and costs take ~0.66R of each trade.

## Verdict

No variant passes on any timeframe. On 15m the bot cannot be profitable at 0.1% taker fees regardless of how well Drex filters, because costs alone are about two-thirds of the risk per trade. A Drex filter cannot create edge that the setups don't have.
