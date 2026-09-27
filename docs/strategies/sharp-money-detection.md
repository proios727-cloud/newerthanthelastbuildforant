---
title: Sharp Money Detection
type: concept
created: 2026-07-31
updated: 2026-07-31
tags: [sports-betting, signals]
---

# Sharp Money Detection

Four algorithms [[456cash]]'s sports betting module uses to flag professional ("sharp")
action in line movements, each with per-sport tunable thresholds:

1. **Reverse line movement** — the line moves *against* the betting majority (e.g. 70% of
   bets on Team A but the line moves toward Team B). Books are limiting exposure to sharps
   on the other side. NFL threshold: 2.0+ points.
2. **Steam moves** — rapid synchronized moves across 3+ sportsbooks within a short window
   (NFL: 2.5+ points inside 10 minutes). Signature of syndicates hitting multiple books
   before lines adjust.
3. **Early movement** — a >2% move within the first 2 hours after a line opens. Sharp
   money moves first; the public follows later.
4. **Volume/money anomaly** — money% exceeds bet% by >15%: fewer but much larger bets,
   i.e. concentrated professional capital.

Data: odds snapshots every 5 minutes from The Odds API across DraftKings, FanDuel,
BetMGM, Caesars, PointsBet, Bovada; alerts pushed over WebSocket.

Related: [[456cash]]. ([[src-2026-07-31-sports-betting-tracker]])
