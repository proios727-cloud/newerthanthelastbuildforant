# Kalshi line-movement replay — KXBTCD, last 60 days

Generated 2026-11-16 06:11 UTC. Research only: public data, no orders.

2000 markets from 1405 events (2026-10-30 → 2026-11-16), 94,982 candle decision points. Spread filter ≤ 10¢. Each rule: one trade per market at its first signal, pays the ask, Kalshi taker fee, held to settlement.

## Who forecasts better: the market price or the model?

Brier score (lower is better) over all decision points — market mid **0.1287**, lognormal model **0.1713**, always-50% 0.2500.

| market price bucket | points | avg price | actually settled YES |
|---|---|---|---|
| 0%–10% | 23,209 | 4.5% | 1.7% |
| 10%–20% | 11,807 | 14.7% | 10.4% |
| 20%–30% | 9,041 | 24.8% | 19.7% |
| 30%–40% | 7,936 | 34.8% | 30.8% |
| 40%–50% | 7,286 | 44.9% | 39.9% |
| 50%–60% | 6,833 | 54.9% | 51.1% |
| 60%–70% | 6,403 | 65.0% | 61.9% |
| 70%–80% | 6,243 | 75.0% | 73.1% |
| 80%–90% | 6,419 | 85.1% | 83.3% |
| 90%–100% | 9,805 | 95.3% | 94.7% |

Line movement vs what was left to win: correlation of the last candle's price move with (outcome − price) = **+0.000** over 92,559 points (positive = moves under-react, so following them pays; negative = moves over-react, so fading pays).

## Rules, walk-forward (threshold picked on earlier months only)

| rule | trades | win rate | avg P&L / contract | total $ per 1 contract | ROI on cost | t-stat | thresholds used |
|---|---|---|---|---|---|---|---|
| model_edge | 1952 | 33% | -5.06¢ | -98.83 | -13.8% | -5.38 | 2026-11:0.03 |
| momentum | 1716 | 54% | -1.95¢ | -33.50 | -3.6% | -1.85 | 2026-11:0.05 |
| fade | 1825 | 41% | -4.91¢ | -89.62 | -11.0% | -4.93 | 2026-11:0.03 |
| longshot | 0 | – | – | – | – | – | – |

## Every threshold, whole period (in-sample — for context, not for picking)

| rule | threshold | trades | win rate | avg P&L / contract | ROI | t-stat | first 60% avg | last 40% avg |
|---|---|---|---|---|---|---|---|---|
| model_edge | 0.03 | 1957 | 33% | -4.96¢ | -13.5% | -5.28 | -3.28¢ (1066) | -6.98¢ (891) |
| model_edge | 0.05 | 1888 | 32% | -4.99¢ | -13.8% | -5.23 | -3.81¢ (1035) | -6.43¢ (853) |
| model_edge | 0.08 | 1762 | 31% | -5.11¢ | -14.8% | -5.22 | -3.94¢ (979) | -6.58¢ (783) |
| model_edge | 0.12 | 1557 | 28% | -4.61¢ | -14.6% | -4.53 | -4.57¢ (889) | -4.68¢ (668) |
| model_edge | 0.18 | 1197 | 24% | -5.43¢ | -18.9% | -4.84 | -6.37¢ (725) | -4.01¢ (472) |
| momentum | 0.03 | 1830 | 59% | +1.14¢ | +2.0% | +1.14 | +0.01¢ (954) | +2.36¢ (876) |
| momentum | 0.05 | 1716 | 54% | -1.95¢ | -3.6% | -1.85 | -2.79¢ (887) | -1.06¢ (829) |
| momentum | 0.08 | 1515 | 51% | -3.00¢ | -5.7% | -2.61 | -3.18¢ (773) | -2.81¢ (742) |
| momentum | 0.12 | 1202 | 53% | -3.16¢ | -5.8% | -2.43 | +0.20¢ (607) | -6.59¢ (595) |
| fade | 0.03 | 1830 | 41% | -4.81¢ | -10.8% | -4.83 | -3.61¢ (954) | -6.11¢ (876) |
| fade | 0.05 | 1716 | 46% | -1.84¢ | -3.9% | -1.74 | -0.95¢ (887) | -2.78¢ (829) |
| fade | 0.08 | 1515 | 49% | -0.94¢ | -2.0% | -0.82 | -0.70¢ (773) | -1.20¢ (742) |
| fade | 0.12 | 1202 | 47% | -0.90¢ | -1.9% | -0.69 | -4.24¢ (607) | +2.51¢ (595) |
| longshot | 0.05 | 1858 | 98% | +0.69¢ | +0.7% | +1.96 | -0.05¢ (1015) | +1.59¢ (843) |
| longshot | 0.1 | 1940 | 94% | +1.12¢ | +1.2% | +2.17 | +0.12¢ (1055) | +2.32¢ (885) |
| longshot | 0.15 | 1974 | 90% | +0.17¢ | +0.2% | +0.26 | -1.30¢ (1071) | +1.92¢ (903) |

Notes: Kalshi settles on the CF Benchmarks BTC index, the model uses Binance BTCUSDT (a small basis). Fills at the quoted ask ignore size and queue; real fills on thin strikes will be worse. A |t-stat| under ~2 is indistinguishable from luck.
