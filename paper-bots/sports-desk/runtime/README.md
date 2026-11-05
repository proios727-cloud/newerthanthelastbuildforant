# Pregame sports PAPER runner

A runnable Python-standard-library collector and simulated execution loop. No live-order API, betting account login, or LLM invocation exists in this runner. NFL/MLB binary team h2h mappings are supported only when manually verified. Other sports require equally explicit exhaustive outcomes and matching settlement definitions. Combos, live entries, scores, breaking news, weather, real-time injury integration and calibrated predictive models are not implemented. Existing PAPER positions have an independent book-based liquidation manager.

## Run

```sh
python runtime/bot.py --check --config runtime/config.example.json
python runtime/bot.py --once --fixture runtime/fixture.synthetic.json --config runtime/config.synthetic.json --db /tmp/sports-synthetic.sqlite --bankroll 1000
python runtime/bot.py --loop 300 --config runtime/config.local.json --bankroll 1000
python -m unittest discover -s runtime -p 'test_*.py' -v
```

Run from the sports-desk directory. Real data collection needs `ODDS_API_KEY` supplied securely in the environment. Copy the example config, map exact Kalshi ticker and Odds API event ID/outcome strings, explicitly enumerate complete sportsbook outcomes and reviewed independent bookmaker keys. Set `settlement_verified` and `fee_verified` true only after checking the notes against current venue documentation. Default examples are deliberately blocked. `--bankroll` is immutable for a given database; use a separate database for a different starting bankroll.

`--once` reads once. `--loop [SECONDS]` defaults to 300 seconds. Create `runtime/HALT` to stop further collections and simulated actions; remove it before a new run. The loop checks this file between cycles and within one second during idle waits. In-flight provider GET requests time out after 15 seconds; halt does not interrupt a currently running cycle.

Persistent SQLite tracks positions, fees, proportional entry-fee allocation on partial exits, action idempotency, cash, and per-day request reservations. At most one entry is permitted for an explicitly mapped ticker, including after closure; repeated scans do not compound entries. Entry spend including configured fee reserve is capped at 0.5% initial paper bankroll, aggregate open entry basis at 10%; available cash is checked under a database transaction. Independent desk account only. A simulated partial fill consumes displayed depth as a hypothesis; competing participants, execution delay, hidden liquidity and real fills are unobserved.

Default persistent daily cap is 100 Odds API requests, reserved before attempting each collection. Failures conservatively consume a reservation. Previously entered mappings collect book-only for position management and do not consume Odds API calls; this path can run without that provider key. This is a REQUEST cap, not a verified credit/cost counter: different provider markets/bookmaker counts may consume different credits, and other clients using the API key are outside this counter. GET-only Kalshi metadata and books are separate from this cap.

## Pricing and risk boundaries

Probabilities are no-vig h2h probabilities from each fresh complete bookmaker outcome set, then median across explicitly reviewed independent providers. Subtract a configured uncertainty margin. This is a heuristic hypothesis, not a fitted or calibrated confidence interval. Require conservative net edge at the actual size-weighted opposing-book ask. Closing uses size-weighted own-side bids, a profit target after proportional entry and exit reserves, or insufficient remaining heuristic edge. Partial exits persist; identical snapshots cannot repeatedly reuse the same depth for another partial exit. No simulated settlement exists. New entries are blocked during the final ten minutes before the persisted event start and after kickoff. Existing positions are forced to PAPER flatten during this window or after kickoff using fresh valid size-aware bids and verified fee reserves, even without a sportsbook feed or live forecast. A partial exit leaves an explicit remaining_unresolved quantity; stale, absent, closed or insufficient books flag an unresolved position and unavailable equity instead of a fabricated fill. Actual reschedules are not automatically reconciled with persisted kickoff.

Fee fields are REQUIRED explicit nonnegative per-contract conservative paper reserves, with a minimum supported $0.02 per side. There is no universal $0.02 actual exchange fee: series multiplier, maker/taker type, rounding, and contract size may change actual costs. Verify the selected reserve is conservative for the exact series. Recorded paper P&L subtracts this reserve, not exchange-confirmed fees. A future proper fee adapter should implement current per-series fee schedules and actual fill fees.

Kalshi REST books generally expose no reliable exchange book-generation timestamp. The runner distinguishes receipt timestamp from source timestamp. Missing source age **rejects by default**. `allow_receipt_only_book=true` explicitly permits a recent HTTP receipt but does not establish event freshness; label such paper runs accordingly. Market metadata update time is not substituted for book-generation time. No WebSocket sequence tracking or reconnect replay is implemented.

Odds source freshness uses each market's `last_update`, with a separate receipt check. The Odds API documents main-market in-play refresh at 40 seconds and historical snapshots at five minutes; it cannot establish subsecond edge capture. Entry forecasting is pregame only. Managing an existing PAPER liquidation after kickoff requires a valid book, not a live forecast. No promise that a quote remains executable after collection.

Incomplete depth prevents full liquidation equity from being shown. Missing rules, fees, source age, missing outcomes, duplicate outcome strings, insufficient books, live/started games, unknown event IDs, closed markets and unaffordable size reject instead of manufacturing values. A current valuation requires a validated open market, noncrossed spread within the configured maximum (default $0.03), and sufficient whole-position executable depth. Historical orders are not repriced at fictional executable levels.

## Settlement checklist for every explicit mapping

- NFL: overtime counted, potential ties, cancelled/postponed games, date windows, binary/nonbinary payouts and official source. A two-way sportsbook team line with tie voiding may not match Kalshi binary outcome settlement.
- NBA: full-game including overtime versus regulation-only; voids/cancellations. A three-way regulation market has a draw outcome and must not be normalized as two-way.
- MLB: listed pitchers versus action, minimum innings, suspended games and reschedules; venue-specific outcomes must match.
- Combo correlation and nonbinary leg payouts need their own simulator and adapter; not supported here.

Primary documentation: [Kalshi books](https://docs.kalshi.com/api-reference/market/get-multiple-market-orderbooks), [Kalshi series fee metadata](https://docs.kalshi.com/api-reference/market/get-series), [fee schedule](https://kalshi.com/docs/kalshi-fee-schedule.pdf), [Odds API V4](https://the-odds-api.com/liveapi/guides/v4/), [book coverage](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html), [refresh intervals](https://the-odds-api.com/sports-odds-data/update-intervals.html).

## Reuse your existing local environment file

The confirmed existing repo is proios727-cloud/newerthanthelastbuildforant. Its GitHub default branch contains a pure sportsbook line tracker but no credential file or live Odds API client was identified. Local venv/.env configuration may still exist on your computer; GitHub inspection cannot validate that local secret.

From this sports-desk folder, use:

```sh
python runtime/bot.py --env-file "/actual/path/to/newerthanthelastbuildforant/.env" --check-api
```

On Windows, use `py -3` instead of `python` if needed and pass the actual quoted Windows path. The read-only check calls the provider sports-list endpoint, which is documented as not counting against the usage quota. No trade is submitted. It prints connection status and available quota headers, never the key. A free account can be checked; no paid subscription is required for this diagnostic.

The loader accepts literal ODDS_API_KEY or THE_ODDS_API_KEY lines, optional quotes/export, and imports no other keys. It never evaluates interpolation, shell commands or other environment-file contents. Existing process environment wins, matching ordinary dotenv non-override behavior. Do not upload the .env, print its contents, or copy keys into chat. A venv is normally the Python dependency environment, while .env holds configuration, though your local project may arrange those differently.

If access succeeds, run the paper loop with the same --env-file plus your reviewed --config. Credential success alone does not verify market mapping, settlement compatibility, fees or profitability. Actual credential testing remains unavailable here until the local file is accessible in the running environment.
