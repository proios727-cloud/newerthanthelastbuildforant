# chart: indicator engine + bar backtester

Original implementation. It is built only from published indicator definitions (Wilder 1978,
Appel's MACD, Bollinger's bands), not from any vendor's code. Pure stdlib Python, no dependencies.

## Data

- `Bar(ts, open, high, low, close, volume)`. Bars are in ascending `ts` order.
- `load_csv(path)` reads the columns `date|time|timestamp, open, high, low, close[, volume]`,
  case-insensitive. Rows must be strictly ascending, or it raises `ValueError`.

## Indicators

Each indicator returns a list the same length as its input, with `None` until it has warmed up.

| Fn | Definition | First value at index |
|---|---|---|
| `sma(x, n)` | mean of the last n | n−1 |
| `ema(x, n)` | α = 2/(n+1), seeded with sma(n) | n−1 |
| `rma(x, n)` | Wilder: α = 1/n, seeded with sma(n) | n−1 |
| `rsi(close, n=14)` | 100 − 100/(1+RMA(gain)/RMA(loss)); 100 when loss = 0 | n |
| `macd(close, 12, 26, 9)` | line = ema12−ema26; signal = ema9(line); hist = line−signal | line: slow−1; signal: slow+sig−2 |
| `bollinger(close, 20, 2)` | mid = sma; ± k·population stdev | n−1 |
| `true_range(bars)` | max(h−l, \|h−prev c\|, \|l−prev c\|); bar 0 = h−l | 0 |
| `atr(bars, 14)` | rma(true_range, n) | n−1 |

## Backtest

`backtest(bars, signals, fee_bps=0, slippage_bps=0, allow_short=False, start_cash=100_000, periods_per_year=252)`

- `signals[i]` ∈ {−1, 0, +1, None} is the target position decided at the **close of bar i**.
  None means hold. The engine **fills at the open of bar i+1**, so there is no lookahead.
  A signal on the last bar is ignored.
- −1 is clamped to 0 unless `allow_short`.
- The position is sized at 100% of equity, in fractional units. A buy fills at open·(1+slip) and a sell at open·(1−slip).
  The fee is fee_bps of the traded notional.
- Equity is marked at each bar's close.
- **Result:** `equity` curve, `trades` [(entry_ts, exit_ts, side, entry_px, exit_px, pnl)],
  and `stats`: total_return, max_drawdown (≤ 0), sharpe (per-bar returns · √periods_per_year,
  0 when there is no variance), n_trades, win_rate, exposure (the fraction of bars holding a position).
  A position still open on the last bar counts as an open trade marked at the last close.

## Strategies (signal builders)

- `sma_cross(close, fast, slow)`: +1 when sma_fast > sma_slow, else 0.
- `rsi_revert(close, n, lo, hi)`: +1 when rsi < lo, 0 when rsi > hi, otherwise hold.

## Oracle cases (tests/test_chart.py)

1. A constant series makes sma = ema = rma = the constant. Bollinger width is 0. RSI is 100 when there are no losses.
2. Hand-computed values: sma([1..5],3), ema([1..5],3) = [None,None,2,3,4], and RSI on a known short series.
3. A rising series with one buy signal at bar 0 fills at the open of bar 1. Equity at the last close equals the price ratio, net of fees.
4. No lookahead: changing bar i+1's close never changes the fill decided at bar i.
5. A losing round trip gives a negative pnl and max_drawdown < 0.
6. Shorts are ignored unless `allow_short`.
7. **Test-the-test:** a deliberately wrong expected value must make the comparison fail.

## Walk-forward (chart/sweep.py)

- `GRIDS`: sma_cross fast ∈ {3,5,8,10}, slow ∈ {15,20,30} (fast < slow); rsi_revert n ∈ {7,14}, lo ∈ {25,30,35}, hi ∈ {60,70}.
- `sweep(bars, strategy)` ranks every combo by Sharpe, breaking ties on total return.
- `walk_forward(bars, strategy, train_frac=0.7)` picks the best combo on `bars[:cut]` and reports it on `bars[cut:]`
  next to buy-and-hold on the same slice. Signals are computed on the full series because the indicators
  are causal. The test backtest starts flat at the first test bar, even if the train run ended long.
- Oracles: the chosen params equal `sweep(train)[0]`, and wrecking the test slice never changes the chosen params.

## Desk bridge (chart/scan.py)

`scan(paths, universe)` maps `data/<SYMBOL>.csv` to a universe symbol (with `-` or `_` → `/` for crypto), runs walk-forward
per strategy, and returns the Quant seat's `signal_list`. An entry is a **candidate** only when all of these hold:
the latest signal is long, the out-of-sample Sharpe is > 0, it beat buy-and-hold out of sample, and it made at least 2 out-of-sample trades.
Each rejection is listed in `why_not`. The scan never builds a preview or touches the ledger.
