# Verdict: invalid run, rule not tested

**Neither TextToQuant run tested the rule in `RULE.md`, because its exit could never fire.** Do not read these numbers
as evidence for or against trend breakouts.

| Run (TextToQuant id) | Trades | Return | Max DD | Buy & hold | Grade | What happened |
|---|---|---|---|---|---|---|
| BTCUSDT 4h, 2023-11-02 → 2026-11-02 (`9c974ac7`) | 1 | +52.2% | −38.9% | +121.1% | none (too few trades) | One trade held for 6,542 of 6,577 bars and closed only when the data ran out. This is buy-and-hold, not the rule. |
| ETHUSDT 4h, same window (`d09eeff1`) | 4 | +5.4% | −32.3% | +24.3% | F (18/100) | Every exit was the ATR stop or the end of the data. The 10-bar-low exit never triggered. |

Costs were on: 10 bp fee and 0.1% slippage per side. Sizing was 1% equity risk per trade (the parser's default).

## Why the exit was unreachable
In the parsed strategy, the **entry** compares the close with the highest high of the 20 bars *before* the current one
(`shift: 1`). The **exit** compares the close with a 10-bar `range_low` that *includes* the current bar. A bar's close is
never below its own low, so "close crosses below the 10-bar low" can never be true. That left only the 2 × ATR stop, and
on BTC it was never touched.

## Against the pass bar
It fails the bar's first test (≥ 30 trades) on both assets. But the failure comes from the parser, not the market, so the
honest verdict is **not tested** rather than reject.

## Budget
The free plan's lifetime allowance had 3 backtests. These runs used 2, so **1 is left**, and it never renews. One run
covers one asset, so the both-asset test in `RULE.md` can no longer be completed on this plan.

## Next step
Run the same rule, unchanged, in this repo's own engine (`chart/`) on Binance 4-hour bars from the TradingView connector.
It is free, has no run limit, uses the exit exactly as written, and can test both assets plus a longer history.
