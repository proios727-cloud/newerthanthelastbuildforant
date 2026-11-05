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

# Long history: `chart/data/weekly/`

The same 13 ETFs as **weekly** bars from Alpha Vantage `TIME_SERIES_WEEKLY_ADJUSTED` (free tier), written by script from the raw
responses. Daily history this long (`TIME_SERIES_DAILY` with `outputsize=full`) is a premium feature. Each file starts at the
fund's first full week: XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV and XLY in 1999-11, TLT in 2002-08, GLD in 2004-11, XLRE in
2015-10, and XLC in 2018-06. All end on **2026-10-23**, the last complete week.

- **Total return.** Open, high and low are scaled by adjusted close ÷ close, and close is the adjusted close. That folds in
  dividends and the 2025-12-05 splits. The daily files are price-only, so a daily basket misses about 1.9% a year of dividends
  (TLT 4.3%, XLRE 3.3%, XLE 3.1%, XLU 2.9%, XLP 2.7%, GLD 0%; Jan 2024 → Oct 2026).
- **Checked against the daily files.** The newest 59 weekly closes match the daily closes on the same dates, within 0.2%. The
  only exceptions are pre-split raw prices of the five funds that split in Dec 2025, and adjusted closes handle those.
- **Validator flags are real events, kept as is:** the 2008 crash weeks (XLE −26%, XLF +31% and +33%), the 24 Aug 2015 flash
  crash, and March 2020. The validator's 15% wick and 25% move limits are tuned for daily bars.
- Use: `python3 -m chart longrun` (see `chart/longrun.py`).

# Total return: `chart/data/tr/`, `chart/data/etf_tr/`, `chart/data/weekly_desk/`

- **Daily total-return copies** of the 8 desk equities and 13 ETFs. They are generated, not edited:
  `python3 -m chart dividends chart/data chart/data/tr` and `... chart/data/etf chart/data/etf_tr`. Each is a standard
  back-adjustment: bars before an ex-date are scaled by (1 − dividend / previous close), so the latest prices stay as
  traded. Use these for research verdicts. The raw folders stay the source for live prices, tickets and limits.
- **`chart/data/meta/dividends.csv`** lists 241 dividends in the daily span, taken from the "dividend amount" column of
  Alpha Vantage's weekly adjusted series. Amounts are raw per share. Dividends before the splits in `chart/adjust.py` are
  divided by the split ratio when loaded. `ex_date` is the first session of the week the dividend falls in; a real
  ex-date can be up to 4 sessions later (SPY's falls on Fridays). Yearly totals are exact.
- **Check:** every weekly close from Nov 2023 to Oct 2026 matches Alpha Vantage's adjusted close within 0.08%
  (mean 0.01%) for all 18 symbols that paid dividends.
- **`chart/data/weekly_desk/`:** weekly total-return bars for SPY, QQQ, IWM, AAPL, MSFT, NVDA, AMD and TSLA, built the same way as
  `chart/data/weekly/`, 1999 (IWM 2000) → 2026-10-23. They match the daily total-return files within 0.03%. **TSLA**
  (from 2010-07) was added on 2026-10-29. Its weekly closes match the daily total-return file exactly.

# Cash: `chart/data/cash/BIL.csv`

SPDR 1–3 Month T-Bill ETF, weekly total return (Alpha Vantage weekly adjusted), 2007-06-08 → 2026-10-23, built the same way
as `chart/data/weekly/`. It is used as the return on cash when the trend overlay is out of the market
(`chart overlay --cash chart/data/cash/BIL.csv`). Average 1.4% a year over the span, near zero in 2009–15 and 2020–21.
