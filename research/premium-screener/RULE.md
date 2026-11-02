# Rule: daily premium-selling screener (defined risk)

Fixed on 2026-11-02, before any screener output was seen. Decision support only: it lists candidate spreads; the user
places every order by hand.

## Why this can work, and how it fails
Options usually price in more movement than follows. Implied volatility tends to sit above the realized volatility that
comes after it (the volatility risk premium). Selling defined-risk spreads when that gap is wide collects that premium.
The cost is a payoff with many small wins and occasional large losses, concentrated in gaps and crashes. Hence: defined
risk only, a hard stop, and no positions through earnings.

## Universe (fixed)
SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMD, TSLA, META, AMZN, GOOGL, AVGO, NFLX, PLTR, GLD. These are the most liquid
optionable names on Robinhood, where spreads are tight enough for realistic fills.

## Inputs, per ticker, each trading day
- Daily bars, 260 sessions, from the TradingView connector:
  - **RV20:** annualized close-to-close realized volatility over 20 sessions;
  - **trend:** close vs SMA50 and SMA200.
- Option chain (Robinhood, read-only), from the expiry closest to 38 days out within 30–45 days: puts and calls within
  ±15% of spot, with bid/ask, delta, IV and open interest.
  - **IV30:** the average implied volatility of the two at-the-money options (nearest-strike call and put).
- Earnings date (Robinhood earnings calendar).

## Filters (all required)
1. **IV30 ÷ RV20 ≥ 1.20.** Premium is rich relative to recent movement.
2. **No earnings** between today and the expiry.
3. **Liquidity at the short strike:** open interest ≥ 500, and bid/ask spread ≤ 10% of mid (≤ $0.05 when mid < $0.50).
4. **Credit ≥ 25% of the spread width,** priced at the natural fill: short-leg bid − long-leg ask.

## Structure
- **Trend up** (close > SMA50 > SMA200): **put credit spread.**
- **Trend down** (close < SMA50 < SMA200): **call credit spread.**
- **Otherwise:** **iron condor** (both).
- **Short strike:** the option with delta nearest 0.20.
- **Long strike:** the nearest listed strike about 2.5% of spot further out. Width = the distance between strikes.
- **Max loss** = width − credit. **Return on risk** = credit ÷ max loss. Approximate **probability of expiring worthless**
  = 1 − |short delta|.

## Ranking
Score = (IV30 ÷ RV20) × return on risk. Show the top 5 that pass every filter; list the rest with the filter they failed.

## Exit plan (every pick carries it)
- **Take profit** when the spread can be bought back for 50% of the credit.
- **Stop** when the spread costs 2× the credit to close (a loss of 1× credit).
- **Time exit:** close at 21 days to expiry, whatever the P&L.
- **Never roll to avoid a loss,** and never hold through an earnings date.

## Forward log
Each top-5 pick is appended to `research/premium-screener/picks.jsonl` with its legs, the natural credit and the time
logged. A daily re-quote marks each open pick to market (closing at the natural debit: short ask − long bid) and records
the first exit rule hit. That record is the only evidence: historical option quotes aren't available to backtest with.

**Judge after 30 closed picks:** win rate, average win vs average loss, and total P&L in units of max risk. Below
breakeven after costs → stop.
