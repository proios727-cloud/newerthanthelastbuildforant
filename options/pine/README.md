# Heatseeker Strategy - TradingView backtest + live replay

`heatseeker_strategy.pine` is the `strategy()` conversion of the desk's
heatseeker companion: same six setups, same gates, same tier sizing and
regime-conditional exits. It trades the **underlying as an options proxy** -
TV's strategy tester cannot model option premium P&L. The signal ledger
(`python -m options.ledger`) is the real record; this file is the visual
replay + live alert layer.

## Setup (5 minutes)

1. Open SPY or QQQ on a **5-minute** chart in TradingView.
2. Pine Editor -> paste `heatseeker_strategy.pine` -> Add to chart -> Save.
3. Run the desk's sync and fill the "GEX map" input group from its output:
   ```
   .venv\Scripts\python -m options.tv_sync SPY,QQQ
   ```
   - Set "Levels as-of date" to today's date (the Pine flags STALE after 36h).
   - Set "Earnings within 3 sessions" when true for the ticker.
4. Open **Strategy Tester** for the equity curve, win rate, profit factor,
   and the per-trade list. Use the **replay bar** to walk any past week.

## Reading the backtest honestly

- **Historical days before the sync tool existed use auto-estimate levels**
  (prior-day pivot as the flip proxy). Auto-estimate fails the MAP gate, so
  pre-sync days show fewer trades - by design. True-level replay starts from
  the first day you run `tv_sync` daily (it rides the desk's daily loop).
- Fills are TV's assumptions on the underlying with 1% commission; option
  premium, spread and theta are NOT modeled. Treat results as setup-quality
  evidence, not a P&L forecast.
- Gate-blocked signals are logged (`NO TRADE <setup> gate: RVOL ...` in the
  log) so gate calibration can be reviewed, not just trade outcomes.
- The same webhook line as v6 fires on confirmed bars for live use:
  `HEATSEEKER|SPY|FR|A+|...` -> feed to `options/ledger.py` via the bridge.

## Tier sizing

A+ and A trade `qtyFull` (default 100 underlying shares as the proxy);
B trades half. HX is always B. NO tier never enters.

## Doctrine links

- Setups and gates: the gex-vex-heatseeker skill (`references/setups.md`)
- Exits: the skill's `references/exit-policy.md` (+GEX scale-at-node, no
  runners; -GEX ATR+node trail, runner allowed; 15:45 flat)
- The board that produces the levels: `python -m options.gex_board SPY,QQQ`

Decision support only. This script never places real orders.