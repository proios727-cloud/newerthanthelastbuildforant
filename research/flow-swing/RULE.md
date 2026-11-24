# Flow-confirmed swing call — pre-registered rule (paper mode)

Registered 2026-11-24 at the owner's request, before any signal was logged. Decision support only: nothing here places,
previews or reviews an order. The owner enters any pick by hand. Changes are amendments below, never edits.

## Why
On 2026-11-24 chip names fell 9-12% while option flow leaned hard to calls (AMD calls 14x vs puts 4.6x volume/OI) and
price bounced within the hour. One day is an anecdote. This rule logs the same setup every day so 30 signals can be
judged with the strategy-vetting skill instead of by memory.

## Limits
- Single long calls only, ask × 100 <= $200 (ask $0.50-$2.00). One signal per day.

## Signal (all must pass) — `options/flow_swing.py`
1. **Flow leans calls:** on the fallback flow board (`scripts/fallback_board.py`, contracts expiring after today and
   within 30 days, strikes ±12%), average call volume/OI >= 2.0 × average put volume/OI.
2. **Broad, not one strike:** at least 10 call contracts traded above their open interest.
3. **Price confirms:** the stock is >= 1.0% above its day low when the board is built (at or after 11:00 ET).
Ranking: call/put ratio, highest first. The next one is the backup.

## Contract — needs a quoted Robinhood chain
Call expiring 14-30 days out, delta 0.30-0.50 (closest to 0.40), ask $0.50-$2.00, open interest >= 500, spread <= 10% of
mid. With no quoted chain (Robinhood offline) the signal is logged as a **candidate**, not a trade: no price is invented.

## Exits (paper, marked at the bid)
Take profit at bid >= 1.6 × entry ask; stop at bid <= 0.5 × entry ask; time exit 7 days before expiry.

## Logging
`research/flow-swing/signals.jsonl`, one line per day (`paper pick`, `candidate …` or `no signal`). Append-only.

## Review
After 30 paper picks (candidates do not count), run the strategy-vetting skill on the results. Keep, change or drop the
rule on that evidence only.
