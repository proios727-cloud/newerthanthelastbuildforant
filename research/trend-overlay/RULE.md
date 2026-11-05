# Rule: desk-level trend overlay (fixed 2026-10-28, before any results were run)

**Rule:**
- Hold the index ETF while its month-end close is above its N-month average of month-end closes; otherwise hold cash.
- It decides at the close of the last weekly bar of each month and fills at the next weekly open.
- 100% in or 100% out, no leverage.

**Assets:**
- **Primary:** SPY.
- **Secondary:** QQQ and IWM, the desk's other index funds.
- **Not searched, used as out-of-sample markets:** the 9 sector SPDRs with history from 1999.

**Data:**
- Weekly total-return bars from `chart/data/weekly_desk/` and `chart/data/weekly/`, 1999 (IWM 2000) → 2026-10-23.
- The first decision comes after N months of history.

**Cash yield:** 0%, which is conservative because it understates the overlay. A flat 2% is shown as a labelled sensitivity,
not as data. Free rate history only starts in 2024 (ThetaData) and the Alpha Vantage quota was spent. Replace both with a
T-bill ETF (BIL, from 2007) when it can be fetched.

**Benchmark:** buy-and-hold of the same fund, total return.

**Claim:** it qualifies as a **risk filter** on the scan's rule:
- a worst drawdown at least ⅓ shallower than holding;
- a Calmar ratio at least holding's;
- invested at least 30% of the time;
- 3+ round trips.

It is not expected to beat holding on return.

**Grid, fixed now:**
- N = 6, 8, **10**, 12 months. 10 is the primary setting.
- All four are reported, and none is picked after the fact.

**Robustness:**
- **Decision week:** the last weekly bar of the month, or the first, second or third.
- **Costs:** 1 + 2 bp, and 10 + 10 bp per side.
- **Stress windows:** 2000–02 dot-com, 2008, 2011, 2015–16, 2018 Q4, 2020, 2022.

**Multiple testing:** 4 lengths × 3 funds = 12 primary tests, plus 9 sector funds at N = 10.

_Update 2026-10-29: BIL weekly history was fetched; the real-cash run is in VERDICT.md. The rule and grid are unchanged._
