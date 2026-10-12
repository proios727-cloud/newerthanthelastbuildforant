# Runnable public-data paper crypto desk

No Node, LLM, exchange key or deposit is required. Python 3.10+ standard library is sufficient. This runtime collects public Kraken BTC/USD and SOL/USD OHLC, AssetPairs minimums/precision and top bid/ask, calculates a deterministic completed 1h EMA20/50 crossover with completed daily rising EMA50, and manages an isolated SQLite simulated account. It cannot transmit real orders. Market/quote collection and both pair diagnostics succeeded in this environment; that does not establish an edge.

**The default 0.5% estimated round-trip cost cap blocks every entry at the configured 0.8% per-side taker estimate.** Flat paper P&L under those defaults means the cost gate declined trading, not profitable performance. The fee is an explicit research estimate based on the current lowest Kraken tier; confirm actual account fees before any future implementation. Changing fees to make a test profitable is invalid. The standalone strategy uses a 4% fixed stop and 72-hour time exit, differing from the earlier Freqtrade ATR hypothesis.

From `separate-desks/crypto-desk/`:

```bash
python runtime/bot.py --check --config runtime/config.example.json
python runtime/bot.py --once --bankroll 1000 --config runtime/config.example.json
python runtime/bot.py --loop --interval 60 --config runtime/config.example.json
python runtime/bot.py --health
python -m unittest discover -s runtime/tests -v
python runtime/backtest.py
# Repeat exact saved public historical dataset without fetching again:
python runtime/backtest.py --fixture runtime/results/source_snapshot.json
```

`--bankroll` initializes immutable **simulated** USD capital; omit it on restart. `--db` selects an isolated account file; default `runtime/state/paper.sqlite`. `--health` reads saved status and its age; it does not verify that a loop is currently alive. `--loop --interval` must exceed 15 seconds. One process locks each DB (Unix flock; Windows msvcrt, Windows path untested here). Create `runtime/HALT` to block all simulated fills and stop the polling loop; remove it and restart the loop to resume. One-shot halted accounts can still report available quotes and missing marks. Ctrl+C stops polling. A missing/stale feed prevents entries and never values an unmarked position as zero.

Settings in `config.example.json` are hypotheses: 10% maximum total entry basis shared across BTC/SOL, one open position, 0.5% modeled stop-risk budget including estimated round-trip expenses, estimated per-side fee/slippage, 4% stop, 72-hour maximum age, quote/source age limits. Numeric risk/exposure/cost ceilings reject unsafe configuration increases. Live trading/funding readiness is **not established**. Runtime public AssetPairs minimum quantity/cost and quantity precision are enforced; these can reject small paper trades. Ordinary fills use simulated ask plus adverse slippage on entry and bid minus adverse slippage on exit, charging fees on both sides. Top quotes have no verified depth/queue/fill guarantee; no liquidity-driven realized return claim is made. Spot simulation has no futures funding rate or leverage.

Quote timestamps mean **local HTTP receipt**, checked against HTTP Date and request duration, not a verified order-book event timestamp. Candle times are source candle-open times; only candles closed by the signal boundary qualify. Public OHLC returns at most 720 bars and includes a current unclosed bar; the runtime excludes it, rejects gaps, requires 250-candle warmup, and separately checks daily availability at hourly signal close.

SQLite stores whitelisted raw public observations, decisions, fills, risk settings, status and feed-failure types. Never place secrets in fixtures/config. Observation source is explicit. `--fixture FILE` requires JSON `{ "now": <epoch>, "observations": { "BTC/USD": <observation>, "SOL/USD": <observation> } }` with each observation labelled `SYNTHETIC_FIXTURE`; synthetic results are not live validation. Tests construct this schema. Private keys/tokens are not accepted. Logs are ordinary local audit records, not independently tamper-proof.

Candle claims persist **before** entering: a crash after claiming can skip a trade rather than duplicate it. Account fills and position metadata are separate commits; a crash between them produces a position whose metadata is missing. The next fresh-quote tick simulates liquidation with both fees, labelled `missing_position_metadata`, rather than guessing a stop or original time. Replay tests verify claim/restart and missing-metadata recovery. This favors avoiding duplicate exposure over exactly-once processing.

## Historical research findings

The4h EMA candidate can now be forward tested separately:

```bash
python runtime/bot.py --check --config runtime/config.4h-research.json
python runtime/bot.py --loop --interval 60 --bankroll 1000 --db runtime/state/4h-research.sqlite --config runtime/config.4h-research.json
```

This explicit `research_only: true` profile permits a2% estimated cost ceiling; ordinary profiles retain the0.5% maximum. Both modes remain strictly PAPER ONLY, and fees stay0.8% per side. The dedicated database avoids mixing1h/4h histories. The source interval is verified against the configured60/240 minutes. The4h forward variant uses250 closed candles of warmup and a4% stop/72h time exit; historical replay uses50-bar warmup and an8% take-profit, so forward results are a distinct hypothesis, not reproduction of the single profitable historical trade. Profile identity is reported in status; the research flag does not authorize live funding or orders.

`runtime/results/source_snapshot.json` contains public Kraken data actually retrieved; `backtest_report.json` contains all fixed variants and per-bar net equity for charting. Each BTC/SOL asset has separate $1,000 hypothetical capital; no combined portfolio return is claimed. The final third is chronological holdout, with EMA cross/pullback/breakout thresholds fixed before scoring. Models are compared to cash and fee-adjusted 10%/100% buy-and-hold. Data are bounded to about30 days of1h and120 days of4h, with shorter scored periods after warmup.

Research-only 2% cost-cap variants allow trading at1.7% assumed round-trip costs; runtime default remains0.5%. All1h holdout variants lost money after costs. The4h EMA version made about+$4.72 BTC /+$6.23 SOL on one trade each, below exposure-matched buy-and-hold; other4h variants lost money. This is **not positive overall evidence** and is too short/small to justify real funding. Historical replay uses next-open entries, a4% stop/8% target, stop-first if both touched, 72-hour time exit and50-bar warmup, rather than pretending it exactly reproduces the250-bar runtime. Spread/depth history, queue, latency and venue minimum handling are absent from that historical replay. Profit metrics include fees and assumed adverse slippage, not taxes. Drawdown is sampled per bar; intra-bar equity drawdown may be larger.

Official API references: https://docs.kraken.com/api/docs/rest-api/get-ohlc-data/ , https://docs.kraken.com/api/docs/rest-api/get-ticker-information/ , https://docs.kraken.com/api/docs/rest-api/get-tradable-asset-pairs/ . Fee reference: https://www.kraken.com/features/fee-schedule .
