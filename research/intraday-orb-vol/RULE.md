# Rule (pre-registered, not yet tested): opening-range breakout on high-volatility days only

Fixed on 2026-11-02, **before any test data was obtained**. Suggested by `research/intraday-orb/VERDICT.md`: breakouts paid
only in 2025, the high-volatility year. Because the idea came from those results, it **must not be scored on any data that
study used** (SPY/QQQ 15-minute 2026, 1-hour 2023–26).

## Data (required)
- SPY and QQQ, **1-minute or 5-minute regular-hours bars, 2018-01-02 → 2022-12-30**, resampled to 15 minutes. That covers
  the 2018 Q4 sell-off, 2020 and 2022.
- Source and checks are logged in `docs/intraday-data.md`. Prices must pass the daily cross-check (`check_daily`) first.

## Rule
- Same mechanics, costs and walk-forward as `research/intraday-orb/RULE.md` (`chart/intraday.py`), with no changes.
- **Filter:** trade the breakout only when the **prior session's high−low range ÷ its close** is in the top third of the
  previous 60 sessions. It is computed from data available before the open.
- **Grid** (fixed): `or_min` ∈ {15, 30}; `target_r` ∈ {1, 2, none}; filter fixed at the top third. That is 6 variants ×
  2 symbols = 12 tests.

## Pass bar (all required, same as the parent study)
1. Walk-forward return > 0 at 1+1 bp, and > 0 at 2+2 bp.
2. Out-of-sample mean trade t-stat ≥ 2, with ≥ 100 out-of-sample trades.
3. Positive on both SPY and QQQ, and in at least 3 of the 5 years.

If it passes, the next step is a forward paper log and then an alert. If it fails, the opening-range breakout family is
closed for SPY/QQQ.
