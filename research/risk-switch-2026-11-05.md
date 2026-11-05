# Regime risk switch backtest — BTCUSDT 15m, 2025-11-05 → 2026-11-05 (365 days)

Stand-in regime from the v3 question's own criteria (no Drex calls). Costs 12 bps per side on traded notional. Out-of-sample = last 40%.

| policy | return (all) | max drawdown | Sharpe | return OOS | max DD OOS | rebalances | fees $ | time in market |
|---|---|---|---|---|---|---|---|---|
| Buy and hold | -21.0% | 45.6% | -0.31 | +27.9% | 13.6% | 1 | 12 | 100% |
| Trend filter (EMA20>EMA50, 0/100%) | -57.8% | 59.9% | -2.77 | -22.3% | 26.5% | 669 | 5,045 | 50% |
| Regime risk switch | -68.5% | 69.7% | -6.00 | -29.2% | 31.6% | 2685 | 6,279 | 37% avg |

Stand-in regime mix: {'TRENDING': 3156, 'CHOPPY': 30008, 'PANIC': 1875}. Ending exposure for the switch: 50%.

## Slower clocks (same year; every variant tested is listed)

| policy | return (all) | max DD | return OOS | max DD OOS | trades | fees $ |
|---|---|---|---|---|---|---|
| Buy and hold | −21.0% | 45.6% | +27.9% | 13.6% | 1 | 12 |
| Trend filter, 4h EMA20/50, min hold 4h | −6.0% | 24.2% | +12.0% | 9.8% | 40 | 413 |
| Regime switch, 4h EMAs, min hold 4h | −41.3% | 41.7% | −11.3% | 13.9% | 1,252 | 4,184 |
| Trend filter, daily EMA20/50, min hold 4h | −5.7% | 12.3% | +5.7% | 12.3% | 6 | 67 |
| Regime switch, daily EMAs, min hold 4h | −43.6% | 44.0% | −18.3% | 19.1% | 1,233 | 3,881 |
| Trend filter, 4h EMAs, min hold 1 day | −10.4% | 27.8% | +12.3% | 9.6% | 40 | 401 |
| Regime switch, 4h EMAs, min hold 1 day | −17.2% | 21.0% | −2.0% | 7.1% | 428 | 1,852 |
| Trend filter, daily EMAs, min hold 1 day | −5.7% | 12.3% | +5.7% | 12.3% | 6 | 67 |
| Regime switch, daily EMAs, min hold 1 day | −20.7% | 22.4% | −1.7% | 6.1% | 426 | 1,611 |

## PANIC-only exit on the daily trend core

| policy | return (all) | max DD | return OOS | max DD OOS | trades | fees $ |
|---|---|---|---|---|---|---|
| Daily trend filter (no regime) | −3.1% | 12.3% | +5.7% | 12.3% | 6 | 68 |
| + PANIC exit, 4h cool-off | −2.9% | 10.2% | +4.9% | 9.1% | 132 | 1,572 |
| + PANIC exit, 1-day cool-off | +0.3% | 11.4% | +7.6% | 11.4% | 90 | 1,113 |

(The no-regime row differs from the table above by a few hundred extra warm-up candles.)

## Verdict

- Resizing on every regime call loses: the regime flips too often and fees dominate.
- A slow daily trend filter is where the risk control comes from: max drawdown 12% vs 46% for buy-and-hold in a down year, at the cost of lagging rallies.
- A PANIC-only exit with a 1-day cool-off adds a small, uncertain improvement on a rule-based stand-in. It is now paper-traded live with the real Drex PANIC probability ("core" sleeve in the bot) to see whether Drex's PANIC call does better than the stand-in.
- 3 + 8 + 2 variants were tried; treat any single number here as provisional.
