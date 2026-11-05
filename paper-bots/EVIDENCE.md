# Engineering results and strategy evidence

As of 11 October 2026. Engineering verification is not evidence of profitable trading.

## Prior confirmed engineering results

The initial eve agent production build and TypeScript check passed. All 19 numerical tests passed:

| Area | Cases | What was verified |
|---|---:|---|
| Executable depth | 2 | Opposing-bid complements, Decimal weighted cost, insufficient/stale depth rejection |
| Edge gate | 5 | Fees/slippage, cost vs payout, invalid/missing inputs, stale/future timestamps, wide/crossed books |
| Paper accounting | 5 | Net partial/final exits, invalid fills, oversell rollback, DB-failure rollback, restart persistence |
| Probability | 4 | No-vig normalization/completeness declaration and aligned correlated simulation outcomes |
| Sizing | 3 | Fractional Kelly, position/exposure caps, invalid inputs and negative edge |

No historical BTC/SOL or sports profitability backtest has yet been run for this build. No forward real-market paper-trading track record exists. The Freqtrade strategy passed syntax checks only; its runtime/backtest is not verified. Any synthetic dollar gain in demos only verifies arithmetic.

## External references

| Reference | Evidence | Limitation |
|---|---|---|
| [AFT 2025 arbitrage paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2025.27) | Authors estimate around $40M extracted from historical on-chain prediction-market orders/executions | Historical aggregate study, not this bot's returns or evidence of current fillable opportunities |
| [Official weather leaderboard](https://polymarket.com/leaderboard/weather/all/profit) | Retrieved platform snapshot showed gopfan2 +$317,221 and ColdMath +$134,264 weather category PnL | Platform-reported; strategy/model/capital and independently audited realized cash returns not established |
| [Weather bot backtest](https://github.com/mifisher/kalshi-weather-bot) | Author reports about 950 historical-quote simulated trades, 14 months/four stations, roughly -3 to -4 cents/trade after fees | Self-reported replay; explicitly negative results, not an endorsed edge |
| [Freqtrade backtesting](https://docs.freqtrade.io/en/stable/backtesting/) | Official reproducible backtest tooling with fees and detailed candles | Tooling, not a profitable strategy; our baseline has not been run |
| [Nick Rae bot audit](https://nickrae.net/blog/kalshi-weather-bot.html) | Firsthand report of attractive paper results failing live/market-relative validation | Individual account; illustrates failure, not independent audit |

## Separate operation

crypto-desk and sports-desk are independent roots with separate configuration, credential field guides, database, logs, and commands. They do not share a coordinator or a bankroll. Common numerical code is copied into each project so each can be moved and launched alone. Paper bankroll initialization takes a chosen positive amount; it does not deposit cash or connect an exchange account.

Monitor status includes paper cash, open cost basis, realized PnL, fees, liquidation equity/unrealized PnL only when fresh marks are provided, and sampled peak/drawdown. Watch mode refreshes the local database; it does not gather data or execute trades. Continuous quote collection, calibrated models, rules/fee integration, agent-worker wiring, real-market paper replay, credentials and production access controls remain incomplete.
