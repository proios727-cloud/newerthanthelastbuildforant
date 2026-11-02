# Rule: SPY/QQQ intraday — opening-range breakout and gap fade

Fixed on 2026-11-02, **before any intraday result was seen**. Widening the grid after seeing results counts as curve fitting.

## Data
- **Primary:** TradingView 15-minute bars, regular hours only (09:30–16:00 ET), SPY and QQQ, 2026-01-02 → 2026-10-30.
  This is the deepest free 15-minute history the connected feeds give (ThetaData and Alpha Vantage intraday need paid plans).
- **Long history:** TradingView 1-hour bars, 2023-01-03 → 2026-10-30. Only the 60-minute opening range can be tested on it.
- **Validation:** each session's first open and last close are checked against the daily files in `chart/data/`.

## Mechanics (all strategies)
- One trade a day at most, long or short, sized at 100% of equity with no leverage.
- A signal is decided at a bar's **close**, and the trade fills at the **next bar's open**. No lookahead.
- A stop or target is checked on each later bar's high and low. **If both are touched in the same bar, the stop counts**
  (the conservative choice). If a bar opens through the stop, the fill is at that open.
- Every position closes at the **last bar's close** (the 15:45 bar on 15-minute data). Nothing is held overnight.
- No new entries after 14:00 ET.
- Costs are charged per side on notional. The base case is **1 bp fee + 1 bp slippage** per side. The cost ladder runs
  0, 1+1, 2+2 and 5+5 bp.

## Strategy A: opening-range breakout (`orb`)
- The opening range (OR) is the high and low of the first `or_min` minutes.
- **Long** on the first bar after the OR that closes above the OR high. **Short** on the first that closes below the OR
  low. Only the first breakout of the day is traded.
- **Stop:** the other side of the OR. **Risk (R)** is the distance from entry to stop.
- **Target:** `target_r` × R, or none (the trade is held to the close).
- **Relative-volume filter (optional):** trade only if the OR's volume is at least `rvol` × its average over the prior
  20 sessions.
- **Grid:** `or_min` ∈ {15, 30} on 15-minute bars (60 on 1-hour bars); `target_r` ∈ {1, 2, none}; `rvol` ∈ {off, 1.2}.
  That is 12 variants on 15-minute bars and 6 on 1-hour bars.

## Strategy B: opening gap fade (`gap_fade`)
- Gap = today's open ÷ the prior session's close − 1, computed only when the prior session is in the file.
- If |gap| ≥ `gap_pct`, **fade** it: short a gap up and buy a gap down, at the close of the first bar, filled at the open
  of the second.
- **Target:** the prior session's close (the gap filled). **Stop:** `stop_x` × the gap size beyond today's open, or none.
- **Grid:** `gap_pct` ∈ {0.25%, 0.5%, 1.0%}; `stop_x` ∈ {1, none}. That is 6 variants.

## Benchmark and claim
- **Benchmark:** cash (0%), with buy-and-hold over the same window shown for context. An intraday rule is flat every
  night, so the real question is whether its **average trade beats zero after costs**.
- **Claim needed for `candidate`:**
  1. Walk-forward (out-of-sample) return is positive at 1+1 bp.
  2. It survives 2+2 bp.
  3. The t-stat of the out-of-sample mean trade return is at least 2.
  4. At least 100 out-of-sample trades.
  5. The same parameters are positive on both SPY and QQQ, and on the 1-hour long history where they can be tested.
- **Multiple testing:** 12 + 6 + 6 variants × 2 symbols = 48 tests. With a 5% threshold, about 2 or 3 "passes" are
  expected by chance. A single variant passing in-sample proves nothing.

## Walk-forward
- Parameters are re-picked at the start of each calendar month by in-sample total return (at 1+1 bp) on **all earlier
  sessions**, with at least 40 sessions of history. The chosen variant then trades that month, and only those trades are
  out-of-sample.
