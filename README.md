# regime-bot — BTC regime-switching paper bot (Binance data + Drex decisions)

One cycle per closed candle (default 15m):

| Step | What happens | File |
|---|---|---|
| 1 | Pull closed BTCUSDT candles + 5,000-level order book from `data-api.binance.vision` (public, no account) | `binance.py` |
| 3 | Render chart + depth into one PNG; Drex tags **TRENDING / CHOPPY / PANIC** with probabilities | `snapshot.py`, `drex.py` |
| 4 | Playbook: breakout (TRENDING), mean reversion (CHOPPY), hands off + flatten (PANIC) | `strategies.py` |
| 5–6 | One Drex call per signal: **TAKE p**, who controls the book, entry **MARKET / LIMIT / WAIT** | `questions.json` |
| 7 | Hard risk gate: probability thresholds, 0.5% risk/trade, 20% notional cap, 1 position, 10 trades/day, 2% daily loss halt, loss cooldown | `risk.py` |
| 8 | Nightly review: regime calibration, TAKE/SKIP replay, bounded threshold tuning, misses packet for question rewrites | `review.py` |
| 9 | Paper fills, phone pings (ntfy), hash-chained audit log | `broker.py`, `notify.py`, `journal.py` |

**Fail-closed:** if Drex errors, no new trade is opened on that candle; the error is logged.

## Setup
```
pip install -r requirements.txt
export NACE_API_KEY=nace_sk_...        # full key, not the masked preview
export BOT_NTFY_TOPIC=your-private-topic   # optional: install the ntfy app and subscribe
```
Network must allow: `data-api.binance.vision`, `console.nace.ai`, `ntfy.sh` (if pings on).

## Run
```
python bot.py --once      # one cycle
python bot.py             # forever (paper)
python review.py          # nightly; writes state/reports/review-<date>.md
python tests/test_pipeline.py   # live-data test with a stub Drex
```
Any `Config` field can be overridden with `BOT_<FIELD>` (e.g. `BOT_INTERVAL=5m`, `BOT_TAKE_THRESHOLD=0.7`).

## Outputs (`state/`)
- `decisions.jsonl` — every regime call, signal, gate verdict, order, fill, exit, error; each line hash-chained (`journal.verify`)
- `snapshots/<candle>.png` — exact image Drex saw (sha256 in the log)
- `paper.json` — equity, position, day counters
- `tuned.json` — thresholds changed by the review (logged as `tune` events)
- `reports/` — nightly review + misses packet

## Question versioning
`questions.json` carries a `version`; every log line records which version produced it, so the review can compare versions. The nightly Claude session reads the misses packet, edits the question criteria, and bumps the version.

## Deploy (Render)
`render.yaml` defines one `worker` (Starter plan) with a 1 GB disk at `/var/data` for logs, snapshots and paper state.
Secrets set in the Render dashboard: `NACE_API_KEY`, `GITHUB_TOKEN` (fine-grained, Contents read/write on this repo only), `BOT_NTFY_TOPIC`.

## Nightly loop
- 00:00 UTC — the worker runs `review.py`, auto-tunes the TAKE threshold (±0.05 max) and pushes the report to the `regime-bot-reviews` branch.
- ~01:00 UTC — a scheduled Claude session follows `NIGHTLY_REVIEW.md`: reads the misses, rewrites at most one set of question wording, validates with `check_questions.py --bump` + tests, commits to the `regime-bot` branch. Render redeploys. History: `QUESTIONS_CHANGELOG.md` + git log.

## Not included (deliberate)
Live order execution. Paper only until the paper week is reviewed; live needs exchange keys, a host that Binance serves (api.binance.com returns 451 from US/cloud IPs), and an explicit go-ahead.

## Run on GitHub Actions (no Render needed)
Workflow `.github/workflows/regime-bot.yml` (on the repo's default branch, since scheduled workflows only run from there) runs `python bot.py --hours 5.25` in back-to-back shifts; an hourly trigger keeps the next shift queued.
State (log, paper account, snapshots) is stored on the `regime-bot-state` branch after every shift; nightly reviews go to `regime-bot-reviews`.
Repo secrets: `NACE_API_KEY` (required), `BOT_NTFY_TOPIC` (optional). The built-in `GITHUB_TOKEN` handles publishing.
