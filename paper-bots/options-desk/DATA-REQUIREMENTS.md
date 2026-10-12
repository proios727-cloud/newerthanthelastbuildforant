# Options premium backtest data and strategy evidence

Scope: buy SPY/QQQ calls outright, test weekly1–7 calendar DTE separately from0DTE, and sell the same observed contract for premium gains. No uncovered short calls, live orders, broker login, or real funding are implemented.

## Existing repository audit

The existing options/data/chains folder contains four SPY chain records: July31 close, and Aug3 captures at09:43,10:12 (put-only) and11:06 Eastern. Source labels attribute them to Robinhood; this attribution was not independently authenticated against exchange history. They contain four same-call matches between09:43 and11:06. No QQQ history, complete minute underlying bars, full premium path or weekly sequence was found in that folder.

The file audit/repository_data_audit.json compares earlier asks with later bids for exact matching calls. This is endpoint arithmetic, not a strategy backtest or an actual trade. The first snapshot precedes09:45 ORB readiness; the missing interval cannot tell whether a20-minute0DTE time exit, stop, target or intervening drawdown occurred. Losing paths and realistic fills cannot be reconstructed from the selected endpoints. Do not claim a win rate or weekly return from them.

## Required inputs

- Completed, timestamped SPY/QQQ minute OHLCV bars, with source and session identity.
- Exact expired call symbols/root/strike/expiration/multiplier, historical bid/ask/sizes and quote timestamps. Greek-based filtering needs contemporaneous externally supplied delta.
- Correct matching session calendar including early closes; strategy decisions may use only information published by decision time.
- Explicit fees, latency/spread assumptions, capital and exposure policy.

The engine's canonical input schema is documented in README.md. JSON/CSV fixtures can exercise logic; real performance requires observed underlying plus option paths. Midpoints, trade highs and theoretical Black–Scholes prices are not interchangeable with executable historical bids/asks. GEX/OI can be tested as a later feature only with historically available data and explicit dealer-position assumptions.

## Provider routes verified from official documentation

| Provider | Usable data | Access boundary |
|---|---|---|
| Massive | /v3/quotes/{optionsTicker}, historical bid/ask/sizes/SIP timestamps | Individual Options Advanced supports quote endpoint; lower individual tiers do not. Current exact total was not verified. |
| Databento OPRA | CBBO-1m from April1 2013;1s and event schemas from March28 2023 | Get a dataset-specific historical cost estimate before buying; current license/plan total not confirmed here. |
| Cboe DataShop |1-minute NBBO quote intervals, sizes, optional Greeks; ETF underlying bid/ask; history since2012 | Narrow symbols/date selection pricing must be quoted. Minute sampling does not reveal within-minute stop/target order. |
| Alpha Vantage | HISTORICAL_OPTIONS is a dated daily chain | Current documented function is premium; daily chains do not supply intraday premium paths. Existing key does not establish paid entitlement. |

The Odds API is the sports feed; it does not replace an equity-options history provider. No provider plan was purchased or authenticated. The cheapest useful purchase should be a limited SPY/QQQ historical sample whose exact estimate is reviewed first, not an assumed unlimited subscription.

## Initial fixed hypotheses

Opening-range15-minute breakout with session VWAP/EMA trend and relative volume; VWAP reclaim; prior20-bar momentum breakout. Run fixed premium target variants and time/stop exits, then compare net after fees across weekly and0DTE separately. Parameters are hypotheses, not an established edge. Evaluate rolling chronological holdouts by trading day, untouched final data, quote-fill capacity, calibration where probabilities are modeled, drawdown, full-premium losses, win/loss distribution and net account returns. Do not select parameters solely because they maximize one week's profit.

## OpenAI role

Current official documentation describes GPT-6.1 Sol as a cost-efficient model for complex coding/reasoning and recommends measuring quality on the actual task. It does not establish options forecasting profitability. Models can propose hypotheses, inspect code/data and explain failures. Deterministic event replay controls contract selection timing, fills, sizing and accounting. No OpenAI API credentials or inference calls are required by this backtester. Any later model feature needs a separate ablation against the numeric baseline and timestamped source provenance; agent agreement is not a statistical confidence interval.

## References

- https://massive.com/docs/rest/options/trades-quotes/quotes
- https://databento.com/blog/opra-improvements-coming-soon
- https://databento.com/docs/examples/options/option-spreads
- https://datashop.cboe.com/option-quote-intervals/
- https://www.alphavantage.co/documentation/#historical-options
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://developers.openai.com/api/docs/guides/model-selection
