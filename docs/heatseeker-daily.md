# Heat Seeker daily runbook

Two scheduled runs build a forward record of Heat Seeker signals on SPY and QQQ. Each run starts in a fresh session, so it
follows this file step by step. Nothing here places, previews or cancels an order.

- **Journal:** `research/heatseeker/signals.jsonl` (schema in the `chart/signals.py` docstring)
- **Dashboard:** https://claude.ai/artifact/C37dRtDvnSMj8VEfps11Xz ("Heat Seeker signals" tab; datasets `hs_levels`,
  `hs_today`, `hs_signals`)
- **Skill:** `gex-vex-heatseeker` (its `scripts/gex_map.py` builds the map)

## 0. Setup (both runs)

1. Skip the run if today is not an NYSE trading day (weekend or holiday). Say so and stop.
2. Check out the work branch:
   ```bash
   git fetch origin heatseeker-log || true
   git checkout -B heatseeker-log origin/heatseeker-log 2>/dev/null || git checkout -B heatseeker-log origin/claude/laughing-goldberg-9td62l
   ```
   Once the pull request that adds `chart/signals.py` is merged, base a new `heatseeker-log` on the default branch
   instead.
3. Run `python3 -m unittest discover -s tests`. If it fails, stop and report; don't log signals from broken code.

## 1. Morning run (about 10:15 ET)

1. **Collect the chains** with a subagent, read-only, as in the skill's Step 1(b). For SPY and QQQ:
   - `get_equity_quotes`
   - `get_option_chains`
   - `get_option_instruments` for today's expiry, the next one and the Friday weekly, with strikes within ±3% of spot
   - `get_option_quotes`, 20 ids per call
   The subagent must not write files or retype numbers.
2. **Turn its transcript into chain files.** The transcript is the agent's `output_file`.
   ```bash
   python3 scripts/rh_chain_from_transcript.py <subagent transcript.jsonl>
   ```
   Force-add the new `options/data/chains/*.json` files (`git add -f`).
3. **Build the maps** with `gex_map.py <chain> --compare-flow` for each ticker.
4. **Write the signals** following the skill's Steps 2–4 and `references/setups.md`:
   - Regime first.
   - Only setups that belong to the regime.
   - Every gate applied: map confidence (drift < 0.15%), RVOL ≥ 1.4 as `trigger.rvol_min`, no entries in the first
     15 minutes, and none in the last 10.
   - Conditional triggers only, each with:
     - a `kind` (one of `close_above`, `close_below`, `reject_below`, `reject_above`);
     - a `level`, plus `after` (the log time, rounded up to the next quarter hour) and `before` (`15:00`);
     - a stop with its basis;
     - a target at the next node;
     - a tier;
     - the near-0.50-delta contract for the nearest expiry with ≥ 1 day left, with its bid and ask from the chain file.
   - Log a no-trade line for any ticker whose gates fail, naming the gate. Append one JSON line per signal to the journal.
     Never edit or delete an earlier line.
5. **Fetch today's bars so far.** Use `mcp-tv-get-ohlcv` with `AMEX:SPY` and `NASDAQ:QQQ`, interval `15m`,
   `format=columns`, and `date_from` = `date_to` = today. Call it directly; the results are small.
6. **Score the journal and write the dashboard files:**
   ```bash
   python3 scripts/tv_from_transcript.py <this session's transcript> /tmp/hs_bars --since <today>T
   python3 scripts/tv_ohlcv_to_csv.py --merge chart/data/intraday /tmp/hs_bars/*.json
   python3 scripts/heatseeker_dash_data.py /tmp/hs_dash --chains <today's SPY chain> <today's QQQ chain>
   ```
   This session's transcript is the newest `.jsonl` under `~/.claude/projects/<project>/`.
7. **Update the dashboard** (step 3 below), then commit and push (step 4).

## 2. After-close run (about 16:25 ET)

1. Fetch today's full session of 15-minute bars for SPY and QQQ (as in step 1.5).
2. Merge them, then rebuild the dashboard files with the chains from this morning's run:
   ```bash
   python3 scripts/tv_ohlcv_to_csv.py --merge chart/data/intraday /tmp/hs_bars/*.json
   python3 scripts/heatseeker_dash_data.py /tmp/hs_dash --chains <today's chains>
   ```
   Check that every one of today's signals now has a final outcome: target, stop, close, not triggered or no trade.
3. Update the dashboard (step 3) and push (step 4).
4. Report in two or three lines:
   - today's signals and outcomes;
   - the running totals of signals, triggered trades and total R;
   - any run that failed.

## 3. Updating the dashboard

For each of `hs_levels.csv`, `hs_today.csv` and `hs_signals.csv` in `/tmp/hs_dash`:
1. Upload the file with the Artifact tool, one file per call: `url` = the dashboard, `asset: true`, `file_path` = the file.
2. Read `datasets/<id>` with ArtifactData `get` to learn its `version`.
3. Run ArtifactData `update` on `datasets/<id>` with `if_version`, setting:
   - `source.url` to the new `/_blob/...`;
   - `source.name` to the file name;
   - `updated` to `{at: <now ISO>, by: "Heat Seeker scheduled run"}`.
4. Don't change the page file `files/index.html`.

Afterwards, read `data/users/me` doc `check` (up to 5 reads). If it reports `failed`, say what it lists; don't try to fix
the page from a scheduled run.

## 4. Commit

- Commit only the journal, new chain files and merged bar CSVs.
- Push to `heatseeker-log`, with up to 4 retries on network errors.
- Don't open a pull request for daily log updates.
- Never force-push.
