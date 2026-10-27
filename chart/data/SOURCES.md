# Price data sources

Daily bars for the desk's 8 equities, **2023-10-02 → 2026-10-26** (770 sessions each, identical dates).
Columns: `date,open,high,low,close,volume`. Prices are raw vendor prices except where adjusted below.

| Source | Rows | Notes |
|---|---|---|
| ThetaData `stock_history_eod` (national EOD report, 17:15 ET) | all symbols, 2023-10-02 → 2026-10-26, except QQQ after 2026-09-30 | Fetched in ~3-month chunks and written by script from the raw responses, not retyped |
| Alpha Vantage `TIME_SERIES_DAILY` | QQQ 2026-10-01 → 2026-10-26 (18 rows) | ThetaData returned a server error for that chunk twice. Opens can differ from ThetaData's by $0.20–0.70; closes match |
| `chart update` (Alpha Vantage, daily) | anything after 2026-10-26 | Appends only rows newer than the file's last date |

2026-10-27 was dropped from the ThetaData files: its EOD row was generated mid-evening and SPY's volume was about half the usual,
so it looked incomplete. The next `chart update` appends the final bar.

## Adjustments (code: `chart/adjust.py`)

| Symbol | Date | Change | Why |
|---|---|---|---|
| NVDA | before 2024-06-10 | OHLC ÷ 10, volume × 10 | 10-for-1 split; vendor prices are not split-adjusted |
| NVDA | 2024-06-10 | high 195.95 → 121.79 (max of open/close) | Bad print on a 120.45 → 121.79 day; true intraday high needs a paid plan to confirm |
| SPY | 2026-02-02 | low 69.005 → 689.63 (min of open/close) | Dropped digit at the vendor; re-fetch returned the same value |

## Checks

- `python3 -m chart validate chart/data/*.csv` passes for every file: ascending dates, OHLC order, no wick more than 15% beyond the
  open/close, no close move above 25% in a day.
- SPY, QQQ and NVDA: all 99 overlapping closes (2026-06-05 → 2026-10-26) match Alpha Vantage within $0.02.
- Every missing weekday is an NYSE closure, including 2025-01-09 (national day of mourning).
- AMD +23.7% on 2025-10-06 and the 2025-04-09 rally are real moves, kept unchanged.

# Research universe: `chart/data/etf/`

13 ETFs (11 Select Sector SPDRs plus TLT and GLD), **2023-10-02 → 2026-10-26**, from ThetaData EOD, written by script from the
raw responses. They are research data only, outside the desk universe. Scan them with `python3 -m chart scan chart/data/etf --all`.

| Change | Symbols | Why |
|---|---|---|
| OHLC ÷ 2, volume × 2 before 2025-12-05 | XLK, XLE, XLU, XLB, XLY | 2-for-1 splits; the close halves and volume doubles on 2025-12-05, and re-fetches are identical |
| Row removed: 2026-10-06 | XLF | Every price is 0.0002, timestamped 00:02 instead of ~17:15 |
| Row removed: 2026-10-05 | XLC | ~76 on ~0.2M shares between ~111 days on ~5M shares; re-fetch identical |

**Days ThetaData would not return** (the error "Wrong number of data fields" on every retry, including single-day requests) are
left as gaps, not filled from another vendor: XLK 10-05, XLE 10-06, XLV 10-08 and 10-09, XLP 10-08, XLC 10-08, TLT 10-08,
GLD 10-05, all in October 2026. A one-day gap barely moves a 3-year test. The basket rotation uses only dates every fund has
(766 of 770).
