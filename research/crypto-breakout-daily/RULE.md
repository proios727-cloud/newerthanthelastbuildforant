# Rule: ETH daily trend breakout as crash protection (risk filter)

Fixed on 2026-11-02, **before any daily data was fetched**. Suggested by `research/crypto-breakout/VERDICT.md`: on 4-hour
bars, the breakout halved ETH's worst drawdown but failed its holdout. This tests the **risk-filter** claim, not a
return claim, on data that study never saw.

## Rule (unchanged structure, daily bars, no tuning)
- **Engine:** `chart/breakout.py`, as committed. It is long or flat at 100% of equity.
- **Entry:** daily close above the highest high of the prior 20 days and above the 200-day EMA. It fills at the next
  day's open.
- **Exit:** a daily close below the lowest low of the prior 10 days (filled at the next open), or a stop at entry −
  2 × ATR(14).
- 20/10 is the textbook channel pair, not fitted here. It is the same as on 4-hour bars, and none of these numbers may
  change.
- **Costs:** 10 bp fee + 10 bp slippage per side; ladder 0, 5+5, 10+10, 25+25.

## Data
- Binance spot ETHUSDT (primary) and BTCUSDT (confirmation), daily bars from listing (2017) to 2026-11-01, from the
  TradingView connector.
- **The primary test window is listing → 2023-12-31.** That is data the 4-hour study never touched. 2024 onward is
  reported separately and labelled as already seen.

## Pass bar: "risk filter" (the repo's standard definition, `.claude/skills/strategy-vetting`), ETH, 2017–2023
1. Max drawdown at least **one third shallower** than buy and hold's.
2. CAGR ÷ max drawdown (Calmar) **at least** buy and hold's.
3. In the market at least **30%** of the time.
4. Still positive at 10+10 bp, with ≥ 30 trades.
5. **In each named crash, the strategy's loss is smaller than buy and hold's.** The crashes are the 2018 bear
   (2018-01-01 → 2018-12-31), the March 2020 crash (2020-02-15 → 2020-03-31) and the 2022 bear (2022-01-01 → 2022-12-31).

**Confirmation:** BTC over the same window must pass tests 1 and 2. If ETH passes and BTC doesn't, the result is
**ETH-only and not proven.**

A pass leads to a forward paper log of the regime flag only, not to trade alerts. A fail closes the 20/10 breakout
family on crypto.
