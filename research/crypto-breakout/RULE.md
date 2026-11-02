# Rule: BTC/ETH 4-hour trend breakout (TextToQuant)

Fixed on 2026-11-02, **before either run**. The free TextToQuant plan has 3 backtests left for the life of the account,
so this spends exactly 2: one rule on two assets. A failure on either one counts.

## Why this rule
- The SPY/QQQ intraday study (`research/intraday-orb/`) found that costs ate the edge on 15-minute and 1-hour bars.
  Binance spot costs about 10 bp a side, so 1-hour crypto churn would be worse. **4-hour bars** are the shortest
  timeframe where a trend-following trade plausibly earns more than its round-trip cost.
- Trend-following (time-series momentum) is the best-documented edge in crypto. A breakout with a long-trend filter is
  its simplest form. This is a swing rule (trades last days), not a day-trading rule.

## Rule (identical for both assets)
- **Market:** Binance spot BTCUSDT and ETHUSDT, 4-hour bars, the last 3 years (the plan's maximum).
- **Entry (long only):** the 4-hour close is above the highest high of the prior 20 bars **and** above the 200-bar EMA.
- **Exit:** a close below the lowest low of the prior 10 bars, or a 2 × ATR(14) stop.
- **Costs:** the platform's fee and slippage settings, left on (not zero). If the parse comes back with zero fees, set
  0.1% fee per side before running.
- No parameter changes after seeing a result. Nothing else is run.

## Pass bar (all required, on both assets)
1. At least 30 trades, and no "zero fees" honesty flag.
2. Positive net return **and** a better return-to-max-drawdown ratio than buying and holding the coin over the same window.
3. Positive in the platform's out-of-sample checks (holdout split and walk-forward), not only in the full sample.
4. TextToQuant badge: DEPLOY. Anything else counts as "not proven".

**Pass on both → forward paper log, then alert. Pass on one → not proven. Fail on both → reject.**

## Amendment, 2026-11-02, before any own-engine data was fetched
TextToQuant's parse made the exit unreachable (`VERDICT.md`), so the same rule is run in `chart/breakout.py`. The entry,
exit and stop are **unchanged**. Only the execution details below are new.

- **Data:** Binance spot BTCUSDT and ETHUSDT 4-hour bars from the TradingView connector, all 24 hours, as far back as
  the feed goes.
- **Fills:** a signal at bar i's close fills at bar i+1's open. The 10-bar-low exit compares the close with the lowest
  low of the 10 bars **before** bar i, which is the TextToQuant bug, fixed.
- **Stop:** fixed at entry fill − 2 × ATR(14) as of the signal bar. It is checked on each later bar's low. A bar that
  opens below the stop fills at its open.
- **Sizing:** 100% of equity, long or flat, with no leverage, so the result compares directly with buy and hold.
- **Costs:** 10 bp fee + 10 bp slippage per side (base case). Ladder: 0, 5+5, 10+10, 25+25 bp.
- **No parameters are fitted,** so there is no walk-forward. Out-of-sample checks instead:
  - the **final third** of each history, a holdout no one has looked at;
  - **every calendar year** separately;
  - **the other coin.**

**Pass bar, on both coins:** at least 30 trades; positive net return at 10+10 bp; return ÷ max drawdown above buy and
hold's; positive in the final-third holdout; positive in more than half of the calendar years.
