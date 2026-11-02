# Nightly question-sharpening run (instructions for the scheduled Claude session)

The worker already ran `review.py` at 00:00 UTC and pushed results to the `reviews` branch:
`reviews/latest.md`, `reviews/latest-packet.json`, `reviews/paper.json`, `reviews/tuned.json`.

## Steps
1. `git fetch origin reviews main && git checkout main && git pull`
2. Read `origin/reviews:reviews/latest.md` and `latest-packet.json`. If the report date is not today (UTC), or it is missing, stop and report that the worker did not publish.
3. **Change nothing** if any holds:
   - fewer than 20 scored regime calls, or
   - regime accuracy ≥ 60% and no `confident_regime_misses` with p ≥ 0.7, and TAKE/SKIP replay shows TAKE avg R ≥ SKIP avg R, or
   - questions.json was already changed in the last 24h (`git log -1 --format=%cI -- questions.json`).
4. Otherwise make **one** focused rewrite in `questions.json`:
   - Use the misses packet: what did the confident wrong calls have in common (candle/book numbers)? Tighten the criterion text that let them through.
   - Edit only `instructions` text and criterion descriptions. Never rename questions or labels; never touch code, thresholds, risk limits or mode.
   - Bump `version` by exactly 1.
5. Validate: `python check_questions.py --bump` and `python tests/test_pipeline.py` must both pass. If either fails, `git checkout questions.json` and stop.
6. Append an entry to `QUESTIONS_CHANGELOG.md`: date, new version, evidence (counts, accuracy, example candle_t values), what changed and why.
7. Commit both files to `main` with message `questions vN: <one-line reason>` and push. Render auto-deploys; the next candle uses vN, and every log line records it.
8. Reply with a 3-line summary: accuracy / TAKE-vs-SKIP R / what changed (or "no change: <reason>").
