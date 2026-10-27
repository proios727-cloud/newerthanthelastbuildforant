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

`scan(paths, universe)` maps `chart/data/<SYMBOL>.csv` to a universe symbol (with `-` or `_` → `/` for crypto), runs walk-forward
per strategy, and returns the Quant seat's `signal_list`. An entry is a **candidate** only when all of these hold:
the latest signal is long, the out-of-sample Sharpe is > 0, it beat buy-and-hold out of sample, and it made at least 2 out-of-sample trades.
Each rejection is listed in `why_not`. The scan never builds a preview or touches the ledger.

## Rolling walk-forward (chart/sweep.py `rolling_walk_forward`)

- After `min_train` bars (default 40), the remaining bars are cut into `test`-bar blocks (default 10). Before each block,
  parameters are re-picked on bars [0, t0) (anchored) or on the last `min_train` bars (`anchored=False`).
- Indicators warm up on all history up to the bar being scored. Parameters are scored only inside their training range.
- Every block's out-of-sample signals are stitched into **one continuous backtest**, so positions carry across block
  boundaries. The first block is seeded with the position its parameters already held.
- Reported: the stitched stats, buy-and-hold over the same span, per-block return vs hold, `windows_beat_hold`,
  `param_sets_used` (a lower count means steadier choices), and the latest signal and parameters.
- Oracle: changing bars after block k leaves the parameters **and returns** of blocks before k unchanged, and does change later results.

## More strategies (chart/strategies.py)

| Name | Rule (decided at close, filled next open) |
|---|---|
| `rsi_dip_trend` | Long when RSI(n) < lo **and** close > SMA(trend); flat when RSI > hi or the trend breaks |
| `macd_trend` | Long while MACD line > signal **and** close > SMA(trend) |
| `bollinger_revert` | Long on a close below the lower band; flat at the middle band |
| `donchian_breakout` | Long on a close above the prior n-bar high; flat on a close below the prior exit_n-bar low |

## Basket rotation (chart/rotate.py)

- Align symbols on their common dates. Every `hold` bars, rank the symbols by `lookback`-bar return. Hold the leader if its
  return is > 0, else hold cash. Switches fill at the next open with fees and slippage on both legs.
- Benchmark: equal-weight buy-and-hold of the basket from the first test bar's next open.
- `rotate.rolling` uses the same block protocol and per-block scoring as the single-symbol rolling walk-forward.

## Candidate rule (chart/scan.py)

An entry is a candidate only when **all** of these hold: the latest signal is long (or holds a symbol, for the basket), the
stitched out-of-sample Sharpe is > 0 **and at least buy-and-hold's Sharpe over the same span** (so a higher return bought with
more risk doesn't count), it beat buy-and-hold over the whole out-of-sample span, it beat buy-and-hold in at least half the
test blocks, and it made at least 3 out-of-sample trades.

## Data validation (chart/validate.py)

`python3 -m chart validate FILE... [--ref REF]` fails on: dates not strictly ascending, a non-positive price, low > min(open, close),
high < max(open, close), a high/low more than 15% beyond the open/close (a bad print), a close moving more than 25% in a day, or, with `--ref`, an overlapping close more than $0.02 away
from the reference vendor's close.

## Forward paper test (chart/forward.py, chart/update.py)

- `chart update` appends Alpha Vantage daily bars dated after each file's last row. It never rewrites history and skips crypto.
- `chart forward record` scans and appends one JSON line per as-of date to `ledger/signals.jsonl` (or `--log`). It runs after
  the close, before the next open, so the signal is fixed before the market can grade it. Re-running the same day is a no-op.
- `chart forward report` scores every logged long signal from the **next open** to the close 1, 5 and 10 sessions later, with
  the number of signals and the hit rate. Horizons that haven't elapsed are not counted.
- `.github/workflows/chart-forward.yml` runs this every weekday at 21:37 UTC and keeps the data, log and report on the `shadow-data`
  branch under `chart-forward/`. It needs the `ALPHAVANTAGE_API_KEY` repository secret.

## Risk-filter rule (chart/scan.py `_risk_verdict`)

A second, separate verdict per entry asks whether the strategy is worth running **on top of holding**, as a way to cut risk.
`risk_filter` is true only when **all** hold: the out-of-sample max drawdown is at least a third shallower than buy-and-hold's
over the same span, its Calmar ratio (CAGR ÷ |max drawdown|) is at least buy-and-hold's, it was invested at least 30% of the
time (so sitting in cash doesn't count as risk control), Sharpe > 0, and at least 3 out-of-sample trades. Rejections are listed in
`risk_why_not`. Stats now include `cagr` and `calmar`; each entry carries a `hold` block with the same fields for buy-and-hold.
`chart scan --all` scans every CSV in a folder (research mode), not only the desk universe.
