---
name: nba-edge-scan
description: Scan every open Kalshi NBA market (moneyline, spreads, totals, team totals, 1st half, player points/rebounds/assists/threes/PRA/steals/blocks) for locks, prices off their own ladder, and gaps against the no-vig sportsbook consensus, net of Kalshi fees. Use when the user asks for the best NBA bets, props, spreads, lines or totals on Kalshi, wants Kalshi compared with DraftKings/FanDuel, or asks what's live tonight. Read-only; never places orders.
---

# NBA Edge Scan

Kalshi's NBA book is efficient most nights: the honest answer is often "no edge". This skill
says that plainly instead of dressing up favourites as picks.

## Run

```bash
python skills/nba-edge-scan/scripts/nba_edge_scan.py                 # today + tomorrow (US Eastern)
python skills/nba-edge-scan/scripts/nba_edge_scan.py --dates 26NOV05 26NOV06
python skills/nba-edge-scan/scripts/nba_edge_scan.py --live           # games in progress: locks + book only
```

Needs `api.elections.kalshi.com` in the network allowlist (public GETs, no key). For the
sportsbook comparison set `ODDS_API_KEY` (The Odds API, free tier is enough for a few runs a
day) and allow `api.the-odds-api.com`. Without the key the book check is skipped and says so.

## Checks, most to least trustworthy

1. **Locks**: on one ladder, a higher rung's YES bid above a lower rung's YES ask. Buy YES low
   plus NO high: the pair pays at least $1. Report `gain_after_fees` and the size available.
2. **Book edges**: Kalshi price vs the median no-vig price across US books, only at the same
   line (moneyline, exact spread, exact total), minus Kalshi's taker fee
   (`ceil(0.07·C·P·(1−P))`). Edges under 2¢ are noise in practice; say so.
3. **Off-curve leads** (pregame only): rungs 4¢+ off a normal curve fitted to the ladder. A
   lead, not a pick: player stats are skewed and the fit is symmetric.

## Reporting

- Lead with locks and book edges. If both are empty, say there is no edge and show the main
  lines (the rung nearest 50¢ for spread and total, plus moneylines) so the user has the board.
- Spreads, totals and props usually post on game day; earlier there are only moneylines.
- Live games: prices already contain score and clock. Never call a live favourite a "pick".
- Give tickers and the price to pay; never place orders.
