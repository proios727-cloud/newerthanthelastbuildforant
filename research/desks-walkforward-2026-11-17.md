# Niche desk walk-forward — 4h candles, fit 180d → trade next 30d unseen, rolled forward

Costs 12 bps per side. Long-only spot, no leverage. Only unseen test slices are counted. `fixed` = the desk's default setting for the whole span (no tuning).


## BTCUSDT  (2020-02-05 → 2026-11-17, 6.8 years unseen)

| desk | walk-fwd CAGR | max DD | Sharpe | fixed CAGR | fixed DD | win windows | setting churn | in market | entries/yr |
|---|---|---|---|---|---|---|---|---|---|
| trend | +21.5% | 73.0% | 0.67 | +37.3% | 51.2% | 40% | 49% | 58% | 5 |
| volgate_trend | +20.8% | 51.7% | 0.78 | +26.7% | 48.9% | 42% | 40% | 57% | 3 |
| pullback | +1.8% | 45.8% | 0.20 | +2.6% | 34.7% | 28% | 68% | 18% | 20 |
| breakout | +30.4% | 68.5% | 0.90 | +26.3% | 62.8% | 41% | 46% | 48% | 9 |
| range_revert | -4.9% | 38.8% | -0.32 | -3.4% | 29.5% | 20% | 38% | 3% | 8 |
| shock_rebound | -5.8% | 44.5% | -0.26 | -0.5% | 24.8% | 16% | 35% | 3% | 6 |
| **ensemble (equal weight)** | +12.4% | 43.2% | 0.69 | – | – | – | – | 80% | 8 |
| buy & hold | +32.8% | 77.0% | 0.78 | – | – | – | – | 100% | 0 |

## ETHUSDT  (2020-02-05 → 2026-11-17, 6.8 years unseen)

| desk | walk-fwd CAGR | max DD | Sharpe | fixed CAGR | fixed DD | win windows | setting churn | in market | entries/yr |
|---|---|---|---|---|---|---|---|---|---|
| trend | +31.1% | 73.8% | 0.76 | +48.4% | 63.2% | 40% | 41% | 51% | 4 |
| volgate_trend | +25.8% | 59.9% | 0.79 | +36.2% | 52.0% | 39% | 37% | 58% | 3 |
| pullback | +5.1% | 63.0% | 0.32 | +10.2% | 33.3% | 33% | 60% | 17% | 18 |
| breakout | +50.0% | 54.8% | 1.07 | +58.7% | 46.6% | 39% | 41% | 42% | 8 |
| range_revert | +3.6% | 28.1% | 0.29 | -1.8% | 24.1% | 37% | 44% | 5% | 12 |
| shock_rebound | +3.0% | 31.5% | 0.25 | -3.4% | 25.8% | 19% | 37% | 3% | 6 |
| **ensemble (equal weight)** | +23.5% | 39.7% | 0.95 | – | – | – | – | 76% | 9 |
| buy & hold | +38.7% | 81.1% | 0.81 | – | – | – | – | 100% | 0 |

## SOLUSDT  (2021-09-15 → 2026-11-17, 5.2 years unseen)

| desk | walk-fwd CAGR | max DD | Sharpe | fixed CAGR | fixed DD | win windows | setting churn | in market | entries/yr |
|---|---|---|---|---|---|---|---|---|---|
| trend | +6.0% | 83.8% | 0.43 | +10.4% | 77.8% | 38% | 34% | 54% | 5 |
| volgate_trend | +19.0% | 49.7% | 0.63 | +9.1% | 56.3% | 29% | 50% | 44% | 4 |
| pullback | +8.4% | 60.1% | 0.40 | +4.4% | 54.3% | 30% | 52% | 16% | 20 |
| breakout | +30.6% | 77.0% | 0.75 | +44.7% | 63.2% | 38% | 40% | 36% | 8 |
| range_revert | -11.0% | 56.3% | -0.72 | -4.1% | 30.6% | 27% | 50% | 3% | 7 |
| shock_rebound | +0.6% | 24.9% | 0.13 | +1.9% | 7.5% | 22% | 27% | 2% | 7 |
| **ensemble (equal weight)** | +14.6% | 45.6% | 0.63 | – | – | – | – | 78% | 9 |
| buy & hold | -13.8% | 96.6% | 0.31 | – | – | – | – | 100% | 0 |
