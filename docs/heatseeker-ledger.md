# Heatseeker signal ledger

Forward log of every GEX/VEX signal — taken or not. Historical GEX cannot be
reconstructed, so this log is the only valid evaluation of the setups.
Format per entry: timestamp ET | ticker | setup | regime | map source/confidence |
level | contract + bid/ask at signal | entry/stop/target | tier | failed gate if no-trade.

---

## 2026-08-04 07:55 ET | SPY | GAP FILL (conditional, premarket) | +GEX aligned
- Map: RH-reconstructed, 61 contracts 0DTE ±3%, OI overnight-fresh, greeks from 8/3 close.
  Flow cross-check drift 0.01% (yesterday's volume) — STABLE.
- Spot 760.61 pre-market (+0.39% gap from 757.67 close). Flip 755.62 (−0.66%).
  King 759, call wall 761 (directly overhead), put wall 757. Net GEX +$1.21B/1%.
  Air pockets below: 750–753, 744–749 (below the flip — only live if regime breaks).
- Conditional trigger (not an entry — premarket, RVOL unknowable): after 09:45 ET,
  rejection at/below 761 with RVOL ≥ 1.4 → short toward 759 then 757.67 (prior close).
  Candidate contract: SPY 2026-08-04 758P (yesterday close 1.57, 1–2¢ spread; RE-QUOTE at
  trigger — pre-market marks are stale). ~3 contracts fit $541 BP at expected ~1.00–1.30.
- Invalidation: 15-min acceptance above 761 → stand down (no breakout chase in +GEX);
  gap-fill thesis dies below flip 755.62 (regime change — different playbook).
- Tier: conditional B until RVOL + alignment gates confirm at trigger; A if both pass.
- NO TRADE as of logging — premarket gate (no entries before 09:45).
