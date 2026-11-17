# Kalshi line-movement replay — KXBTCD, last 60 days

Generated 2026-11-17 04:45 UTC. Research only: public data, no orders.

2000 markets from 13564 events (2026-10-30 → 2026-11-17), 95,256 candle decision points. Spread filter ≤ 10¢. Each rule: one trade per market at its first signal, pays the ask, Kalshi taker fee, held to settlement.

## Who forecasts better: the market price or the model?

Brier score (lower is better) over all decision points — market mid **0.1296**, lognormal model **0.1664**, always-50% 0.2500.

| market price bucket | points | avg price | actually settled YES |
|---|---|---|---|
| 0%–10% | 22,831 | 4.5% | 1.7% |
| 10%–20% | 11,905 | 14.7% | 11.1% |
| 20%–30% | 9,124 | 24.8% | 21.0% |
| 30%–40% | 8,015 | 34.9% | 32.2% |
| 40%–50% | 7,290 | 44.9% | 41.9% |
| 50%–60% | 6,895 | 55.0% | 52.7% |
| 60%–70% | 6,437 | 64.9% | 63.8% |
| 70%–80% | 6,298 | 74.9% | 74.1% |
| 80%–90% | 6,481 | 85.1% | 84.2% |
| 90%–100% | 9,980 | 95.3% | 94.8% |

Line movement vs what was left to win: correlation of the last candle's price move with (outcome − price) = **+0.001** over 92,835 points (positive = moves under-react, so following them pays; negative = moves over-react, so fading pays).

## Rules, walk-forward (threshold picked on earlier months only)

| rule | trades | win rate | avg P&L / contract | total $ per 1 contract | ROI on cost | t-stat | thresholds used |
|---|---|---|---|---|---|---|---|
| model_edge | 1951 | 34% | -4.68¢ | -91.34 | -12.8% | -4.93 | 2026-11:0.03 |
| momentum | 1729 | 54% | -1.35¢ | -23.30 | -2.5% | -1.29 | 2026-11:0.05 |
| fade | 1832 | 40% | -6.06¢ | -110.98 | -13.6% | -6.09 | 2026-11:0.03 |
| longshot | 0 | – | – | – | – | – | – |

## Every threshold, whole period (in-sample — for context, not for picking)

| rule | threshold | trades | win rate | avg P&L / contract | ROI | t-stat | first 60% avg | last 40% avg |
|---|---|---|---|---|---|---|---|---|
| model_edge | 0.03 | 1956 | 34% | -4.58¢ | -12.5% | -4.83 | -3.09¢ (1004) | -6.16¢ (952) |
| model_edge | 0.05 | 1884 | 33% | -4.39¢ | -12.2% | -4.57 | -3.43¢ (972) | -5.42¢ (912) |
| model_edge | 0.08 | 1750 | 31% | -4.49¢ | -13.1% | -4.56 | -3.45¢ (917) | -5.63¢ (833) |
| model_edge | 0.12 | 1538 | 29% | -3.71¢ | -12.1% | -3.63 | -3.71¢ (839) | -3.71¢ (699) |
| model_edge | 0.18 | 1151 | 24% | -4.53¢ | -16.6% | -4.00 | -4.94¢ (677) | -3.94¢ (474) |
| momentum | 0.03 | 1837 | 60% | +1.38¢ | +2.4% | +1.39 | -0.13¢ (901) | +2.83¢ (936) |
| momentum | 0.05 | 1729 | 54% | -1.35¢ | -2.5% | -1.29 | -2.45¢ (838) | -0.31¢ (891) |
| momentum | 0.08 | 1517 | 53% | -1.87¢ | -3.5% | -1.64 | -1.46¢ (722) | -2.25¢ (795) |
| momentum | 0.12 | 1203 | 54% | -2.59¢ | -4.8% | -2.00 | +0.50¢ (560) | -5.28¢ (643) |
| fade | 0.03 | 1837 | 40% | -5.95¢ | -13.4% | -5.99 | -4.37¢ (901) | -7.48¢ (936) |
| fade | 0.05 | 1729 | 46% | -3.33¢ | -7.1% | -3.18 | -2.17¢ (838) | -4.42¢ (891) |
| fade | 0.08 | 1517 | 47% | -2.96¢ | -6.1% | -2.60 | -3.30¢ (722) | -2.64¢ (795) |
| fade | 0.12 | 1203 | 46% | -2.32¢ | -5.0% | -1.79 | -5.39¢ (560) | +0.36¢ (643) |
| longshot | 0.05 | 1852 | 98% | -0.09¢ | -0.1% | -0.25 | -0.50¢ (955) | +0.35¢ (897) |
| longshot | 0.1 | 1936 | 94% | +0.46¢ | +0.5% | +0.87 | -0.28¢ (994) | +1.24¢ (942) |
| longshot | 0.15 | 1971 | 90% | -0.12¢ | -0.1% | -0.17 | -1.18¢ (1008) | +0.99¢ (963) |

Notes: Kalshi settles on the CF Benchmarks BTC index, the model uses Binance BTCUSDT (a small basis). Fills at the quoted ask ignore size and queue; real fills on thin strikes will be worse. A |t-stat| under ~2 is indistinguishable from luck.
