# Forward-test data feeds

The forward paper test (`scripts/forward_run.sh`) needs the day's bars for 21 funds after each close. Two feeds can supply
them, and both run the same script and write to the `shadow-data` branch under `chart-forward/`.

| Feed | How | When it runs |
|---|---|---|
| **API key** | `.github/workflows/chart-forward.yml` fetches with the `ALPHAVANTAGE_API_KEY` repo secret. | Weekdays 23:37 UTC. Without the secret it posts a notice and skips. |
| **Claude connector** (live since 2026-11-02) | A Claude scheduled task, "Chart forward feed (connector)", runs `scripts/forward_feed.sh start`, calls the Alpha Vantage connector once per listed fund, then runs `scripts/forward_feed.sh finish`. That saves tonight's results (`av_from_transcript.py --since`), runs `scripts/forward_run.sh`, pushes to `shadow-data` and prints a one-screen report. | Weekdays 19:41 New York time. It fires into the Claude session that set it up, because only that session holds the connector. |

**Use one feed at a time.** If the secret is added, disable the scheduled task. Otherwise both feeds append the same day,
and the second run is a no-op that only spends quota.

**The nightly run, step by step:**
1. `bash <(git show origin/claude/great-keller-rf23ab:scripts/forward_feed.sh) start` prints the 21 symbols.
2. One `TIME_SERIES_DAILY` call per symbol (`outputsize` compact, `datatype` csv, `return_full_data` true), **one at a
   time**. On a "25 requests per day" error, wait about a minute and retry that symbol once (see Quota below).
3. `scripts/forward_feed.sh finish` (from the same checkout) reports `saved`, `missing`, the doctor's problems, the open
   paper period and `decision_tonight`. On a decision night `/tmp/chart-feed/BRIEF.md` holds the brief.

`DRY_RUN=1 scripts/forward_feed.sh finish` does everything except the commit and the push.

**Monthly review.** On a decision night, `scripts/rotation_review.py` re-derives the picks from the stored bars and
checks the rule's settings, the paper tickets and the data, then writes a one-page pass/flag review with blank sign-off
lines (the `rotation-review` skill says how to read each flag). A green review is not an approval.

**Dashboard.** `finish` also writes `status.json`, `daily.json`, `holdings.json`, `ranking.json` and `review.json` to `/tmp/chart-feed/dash`
(`scripts/forward_dashboard.py`). The nightly session uploads each to the "Rotation forward test" dashboard
(https://claude.ai/artifact/MwqaBqfuJKoaefxeq2a7SW) and points the dataset of the same name at the new file. The
dashboard shows paper results against the basket by session, the current holdings and tickets, the momentum ranking,
data checks, the SPY regime flag, and the monthly review's checks for the last decision with its sign-off order
(analyst, Risk Officer, trader). The sign-offs are never filled from the feed.

**Limits of the connector feed:**
- **Quota:** 21 calls against the free tier's 25. The 25 count over a **rolling 24 hours**, not per calendar day, so a
  run that starts earlier or calls faster than the night before hits the cap before last night's calls expire (seen on
  2026-11-05). Waiting a minute frees one slot per call last night made in that minute. More than one call a second is
  also refused. A fund that still fails is listed under `missing`; the next night fills the gap, because each call
  returns the last 100 sessions.
- **Only tonight's results count.** `finish` passes the start time to `av_from_transcript.py --since`, so a failed fund
  shows as missing instead of quietly reusing an older night's bars.
- **No bars are typed by hand.** `av_from_transcript.py` copies the vendor's csv out of the session transcript, and
  `chart update --from-dir` merges only dates newer than each file's last bar.
- **Scheduled tasks can't carry connectors** in this organization: a task that starts a fresh session gets no
  Alpha Vantage tools. So the task resumes the original session. If that session is archived, recreate the task from
  the claude.ai routines page with the Alpha Vantage connector attached, using the same steps.
- **Depends on a Claude session running.** If one is missed, the next run fills the gap. The rotation record catches up
  within 5 sessions and flags the entry `late` (see `chart/forward.py`).
- `chart doctor --feed connector` skips the key check and still flags stale or lagging files.

Research only: neither feed previews, fills or places an order.

**Costs.** `ROTATION.json` scores each period before and after costs: 3 bp a side (the 1 bp fee and 2 bp slippage the
backtests charge), paid at each fill on the weight the decision trades (`traded`: 1.0 for the first fill, the sum of
weight changes after that). The basket pays one side once, at the first fill. The `_net` fields carry these figures into
the dashboard and the monthly review; the gross fields are unchanged.

**Missed-run alert.** `.github/workflows/forward-watchdog.yml` runs weekday mornings (09:47 New York in summer, 08:47 in
winter). It reads `shadow-data` and fails, so GitHub emails you, when the newest stored bar is more than 2 weekdays old
(two nightly runs missed) or one fund lags the rest. It needs no key and pushes nothing. A market holiday counts as a
weekday, so a run missed next to a holiday alerts one morning earlier.
