# Forward-test data feeds

The forward paper test (`scripts/forward_run.sh`) needs the day's bars for 21 funds after each close. Two feeds can supply
them, and both run the same script and write to the `shadow-data` branch under `chart-forward/`.

| Feed | How | When it runs |
|---|---|---|
| **API key** | `.github/workflows/chart-forward.yml` fetches with the `ALPHAVANTAGE_API_KEY` repo secret. | Weekdays 23:37 UTC. Without the secret it posts a notice and skips. |
| **Claude connector** (live since 2026-11-02) | A Claude scheduled task, "Chart forward feed (connector)", calls the Alpha Vantage connector once per fund, saves the results with `scripts/av_from_transcript.py`, runs `scripts/forward_run.sh SHADOW --from-dir DIR` and pushes to `shadow-data`. | Weekdays 19:41 New York time. |

**Use one feed at a time.** If the secret is added, disable the scheduled task. Otherwise both feeds append the same day,
and the second run is a no-op that only spends quota.

**Limits of the connector feed:**
- **Quota:** 21 calls against the free tier's 25 a day. A failed fund is retried once at most; anything left is filled the
  next day, because each call returns the last 100 sessions.
- **No bars are typed by hand.** `av_from_transcript.py` copies the vendor's csv out of the session transcript, and
  `chart update --from-dir` merges only dates newer than each file's last bar.
- **Depends on a Claude session running.** If one is missed, the next run fills the gap. The rotation record catches up
  within 5 sessions and flags the entry `late` (see `chart/forward.py`).
- `chart doctor --feed connector` skips the key check and still flags stale or lagging files.

Research only: neither feed previews, fills or places an order.
