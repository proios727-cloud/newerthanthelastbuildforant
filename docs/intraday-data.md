# Intraday data: what is available, and how to add more

## In this repo: `chart/data/intraday/`

| Folder | Symbols | Range | Bars | Source |
|---|---|---|---|---|
| `15m/` | SPY, QQQ | 2026-01-02 → 2026-10-30 | 5,434 each (209 full sessions, 26 bars each) | TradingView connector `mcp-tv-get-ohlcv`, format=columns |
| `1h/` | SPY, QQQ | 2023-01-03 → 2026-10-30 | 6,703 each (961 sessions, 8 of them half days) | same |

- Regular hours only, with timestamps in US/Eastern. Each bar is labelled with its open time.
- Written by `scripts/tv_ohlcv_to_csv.py` straight from the saved connector responses. No values were retyped or edited.
- **Checked against the daily files:** each session's first open and last close match `chart/data/<SYM>.csv` within
  15 bp in 1,942 of 1,950 symbol-day comparisons (both symbols, both intervals). The 8 exceptions are closing-auction days: index rebalances and the April 2025
  tariff swings.

## How deep each connector goes (checked 2026-11-02)

| Source | 1-minute | 5-minute | 15-minute | 30-minute | 1-hour | Cost |
|---|---|---|---|---|---|---|
| TradingView connector (`RH_TV_HFT`) | from 2026-10-12 | from 2026-07-27 | from 2026-01-02 | from 2025-01-02 | from 2023-01-03 | included |
| Robinhood `get_equity_historicals` | ~2026 only (older bars are gap-fill placeholders) | same | | | | included |
| ThetaData `stock_history_ohlc` | value plan or above | | | | | paid |
| Alpha Vantage `TIME_SERIES_INTRADAY` | premium only | | | | | paid |

To fetch more without filling the context, have a subagent call the connector and save the response, then run:
```bash
python3 scripts/tv_ohlcv_to_csv.py chart/data/intraday <saved-response.json> ...
```

## Free sources for longer history (outside this container)

This session's network blocks these hosts, so download them on your own machine and commit the CSVs. The loader needs
the columns `timestamp,open,high,low,close,volume`, with ISO timestamps in US/Eastern.

| Source | What you get free | Notes |
|---|---|---|
| **Alpaca Market Data, Basic plan** | 1-minute US stock bars, reportedly back to 2016, free API key | The IEX feed is free. Consolidated (SIP) bars older than 15 minutes are also available on the free plan. Check the current terms. Best free option for a multi-year 1-minute test. |
| **Polygon.io (now Massive), Basic plan** | 2 years of minute aggregates, 5 calls/min | Reports conflict on the free tier, so confirm it before relying on it. |
| **Yahoo Finance (yfinance)** | 1-minute for the last 7 days, 5–15-minute for 60 days, 1-hour for 730 days | Unofficial. Good for quick checks, not as a research record. |
| **Databento** | One-time free credit at sign-up | Exchange-grade data. The credit covers years of SPY/QQQ 1-minute bars. |

Sources: [Alpaca forum: stock history data](https://forum.alpaca.markets/t/stock-history-data/11642),
[free stock API comparison (QVeris)](https://qveris.ai/guides/stock-api-free-comparison/),
[pipegalera/intraday_data (1-minute S&P 500 via Alpaca free tier)](https://github.com/pipegalera/intraday_data),
[Eulerpool: historical intraday data](https://eulerpool.com/blog/historical-intraday-data).
