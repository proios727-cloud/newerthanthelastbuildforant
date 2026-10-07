---
name: gm-toxicity-mm
description: Build, audit or tune a market-making / HFT quoting system that prices BOTH inventory risk (Avellaneda-Stoikov) and adverse selection (Glosten-Milgrom), using PIN, VPIN and an ML toxicity score to drive an ACTIVE / WARNING / HALTED state machine, spread multipliers and dynamic position limits. Use whenever the user mentions Glosten-Milgrom, GM model, adverse selection, informed flow, order-flow toxicity, VPIN, PIN, Kyle's lambda, spread decomposition, Roll estimator, "why is my spread too tight", quoting engines, or wants to extend an Avellaneda-Stoikov bot (crypto, Kalshi, options, perps). Research/simulation only — never places orders.
---

# GM × A-S Toxicity-Aware Market Maker

Source framework: Ruuj (@RuujSs), "How To Use the GM Model To Build a Smarter HFT System", Oct 2 2026.

**Core idea:** effective spread = adverse selection + inventory + processing.
A-S prices inventory. GM prices information: `Spread = μ·(V_H − V_L)`, where μ = P(next order is informed).
A system that only runs A-S quotes too tight whenever informed flow is present.

## Workflow (run in order)

1. **Scope** — instrument, venue, tick/fee, data available (trades w/ side? L1 quotes? fills?). If no data, use `--demo`.
2. **Baseline decomposition** — `python scripts/gm_engine.py decompose --csv trades.csv`
   Roll effective spread, Kyle-λ adverse-selection share, residual inventory+processing. Report `as_fraction` by time-of-day.
3. **Live μ estimate** — VPIN on equal-volume buckets (default 50-bucket window). PIN only as daily sanity check (needs a full day).
4. **Toxicity score (optional)** — features: order imbalance, vol ratio, spread change, realized vol, momentum → GBM classifier → p∈[0,1]. Labels = forward adverse markout on fills; flag that label design is user-specific.
5. **State machine** — VPIN 0.70/0.90, toxicity 0.65/0.85 (warn/halt). WARNING: spread × (1 + 2·pressure), hold, no new risk. HALTED: pull quotes.
6. **Quote engine** — `r = mid − q·γσ²(T−t)`; `half = (½γσ²(T−t) + ½μ_base·V_range)·mult`.
7. **Position limits** — `base·(1 − 0.75·pressure)`, floor 1.
8. **Backtest / replay** — `python scripts/gm_engine.py simulate --demo` → P&L, fills, state transitions, markouts vs pure A-S.
9. **Log everything** — every state change and spread change to JSONL. Non-negotiable.

## Honesty rules
- VPIN's bulk-volume classification is contested — use it as one input, never sole halt trigger without validation.
- Prefer Kyle's λ estimated on **your own fills** (price impact) over imbalance-inferred μ when fills exist.
- Thresholds are defaults, not calibrated. Calibrate per instrument on held-out data; report it.
- Compare against pure A-S on the same tape; a GM layer that doesn't reduce adverse markout isn't earning its keep.
- Never execute. Output config, code, report; any go-live needs the user's explicit approval.

## Outputs
- `gm_report.json` (decomposition, VPIN stats, sim vs A-S), `gm_log.jsonl` (state transitions)
- `board.html`: replayable control board (state light, VPIN vs thresholds, decomposed half-spread, inventory vs dynamic limit, P&L vs pure A-S, transition log, threshold sliders). Runs the engine in-browser; no data leaves the page.

## Script reference
`scripts/gm_engine.py` — `gm_quotes`, `bayesian_update`, `pin_score`, `compute_vpin`, `build_toxicity_features`, `decompose_spread`, `MarketStateMonitor`, `GMASQuoteEngine`, `position_limit`, plus CLI `decompose` / `simulate`. CSV columns: `price,volume,side` (side ±1 optional; tick rule used if absent).
