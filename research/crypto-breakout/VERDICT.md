# Verdict: BTC/ETH 4-hour trend breakout

**Reject.** In this repo's own engine the rule fails the pre-registered pass bar on both coins. Both lost money in the
final-third holdout, the period nobody had looked at. Do not alert on it or trade it.

- **BTC:** made +12.6% against buy and hold's +85.3%. It lost on return per unit of drawdown, in the holdout, and in 2 of 3
  years.
- **ETH:** better. It made +68.6% while buy and hold was flat, and it halved the worst drawdown (−32% vs −68%). But it lost
  10.2% in the holdout, and its average trade is not statistically distinguishable from zero (t = 1.0).
- **Costs decide it.** At 25+25 bp, BTC loses 24% and ETH's edge shrinks to +1%.

Rule, pass bar and amendment were all fixed before any data was seen: `RULE.md`. Code: `chart/breakout.py`, tests:
`tests/test_breakout.py`. Run it with `python3 -m chart breakout chart/data/crypto/4h/*.csv`. Full tables:
`results_own_engine.md`.

## Evidence (own engine, 4-hour bars, 2024-01-01 → 2026-11-01, 10 bp fee + 10 bp slippage per side)

| | BTC strategy | BTC hold | ETH strategy | ETH hold |
|---|---|---|---|---|
| Total return | +12.6% | +85.3% | **+68.6%** | −0.3% |
| CAGR | +4.3% | +24.3% | +20.2% | −0.1% |
| Max drawdown | −31.2% | −53.4% | **−32.2%** | −68.0% |
| CAGR ÷ max DD | 0.14 | **0.45** | **0.63** | 0.00 |
| Holdout, 2025-11-21 → | −12.0% | −5.5% | −10.2% | −15.9% |
| 2024 | +35.6% | +121.3% | +50.9% | +46.3% |
| 2025 | −7.4% | −6.3% | +19.0% | −11.0% |
| 2026 (to Nov 1) | −10.3% | −10.6% | −6.1% | −23.4% |
| Trades · win rate · t | 72 · 32% · 0.46 | | 68 · 31% · 1.00 | |
| Time in market | 25% | 100% | 27% | 100% |
| Cost ladder 0 / 5+5 / 10+10 / 25+25 | +52 / +28 / +13 / −24% | | +118 / +92 / +69 / +1% | |

## Against the pass bar (all required, on both coins)

| Test | BTC | ETH |
|---|---|---|
| ≥ 30 trades | pass (72) | pass (68) |
| Positive at 10+10 bp | pass | pass |
| CAGR ÷ max DD above buy and hold's | **fail** | pass |
| Positive in final-third holdout | **fail** | **fail** |
| Positive in more than half the years | **fail** (1 of 3) | pass (2 of 3) |

## What it is and isn't
- **It behaves as a risk filter, not a return engine.** It is in the market about a quarter of the time and sidesteps
  most of each crash. That is why ETH held up in its bad years. It does not capture enough of the up-moves to beat holding
  BTC in a bull market.
- **Only 2.8 years of 4-hour data were available** (the connector's history starts on 2024-01-01). That covers one bull
  leg and one long decline. That is too short to call the ETH result an edge.

## The TextToQuant runs
The two TextToQuant runs did not test the rule. The parser made the exit unreachable, so BTC's single trade was just buy
and hold.

| Run (id) | Trades | Return | Buy & hold | Grade | Problem |
|---|---|---|---|---|---|
| BTCUSDT 4h (`9c974ac7`) | 1 | +52.2% | +121.1% | none | Exit compared with a 10-bar low that includes the current bar; held 6,542 of 6,577 bars |
| ETHUSDT 4h (`d09eeff1`) | 4 | +5.4% | +24.3% | F | Same parse; only the ATR stop could fire |

The free plan has **1 lifetime backtest left.**

## What would change the verdict
- Daily bars from 2017 on (the TradingView daily feed goes back to listing) for a longer test of the ETH risk-filter
  behaviour. That needs a new, pre-registered daily rule, because the 4-hour parameters can't be re-tuned on this data.
- A cost assumption below 5+5 bp (maker fees, a VIP tier) helps both coins. But it doesn't fix the holdout.
