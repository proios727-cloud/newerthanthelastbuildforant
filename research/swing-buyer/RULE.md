# Swing buyer — pre-registered rule (paper mode)

Registered 2026-11-12 at the owner's request. Decision support only: nothing here places, previews or reviews an order.
The owner enters any pick by hand. The rule is written before the first run; changes are amendments below, never edits.

## Account limits
- **Single long calls only** (no spreads: the owner's account is not cleared for them yet).
- **Max $200 per trade** (ask × 100 ≤ 200). One new pick per day at most.

## Universe (fixed)
NFLX, PFE, INTC, F, SOFI, BAC, T, CSCO, KO, VZ — liquid names whose ~0.45-delta monthly call can fit under $2.00.

## Inputs per ticker, each trading day (about 10:45 ET)
- 260 daily bars, spot, next earnings date.
- One expiry: closest to 30 days out within 21–45 days (the earlier on a tie).
- Calls from 5% below spot to 10% above, with bid/ask, delta, IV and open interest.

## Filters (all must pass)
1. **Uptrend:** close > 20-day SMA > 50-day SMA.
2. **Cheap options:** at-the-money IV / 20-day realized vol ≤ 1.00 (buy premium only when it is cheap).
3. **No earnings** on or before expiry.
4. **A contract that fits:** call with delta 0.30–0.60, ask between $0.50 and $2.00, open interest ≥ 500,
   bid/ask spread ≤ 10% of mid (or ≤ $0.05 under $0.50). Of those, the delta closest to 0.45.

## Ranking
score = 20-day return (%) ÷ IV/RV. Highest score is the day's pick; the next is the backup. A ticker with an open pick
is skipped.

## Exits (paper, marked daily at the bid)
- **Take profit:** bid ≥ 1.6 × entry ask (+60%).
- **Stop:** bid ≤ 0.5 × entry ask (−50%).
- **Time exit:** at 10 days to expiry, whatever the result.

## Logging
- `research/swing-buyer/picks.jsonl`: one line per pick; a close is a new line with `close_of`.
- `research/swing-buyer/<date>/swing_screen.csv`: every ticker with its result or failed filter.
- Append-only. Never edit or delete a line.
