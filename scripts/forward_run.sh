#!/usr/bin/env bash
# One forward-test run against a shadow-data checkout: seed missing CSVs, append the day's bars, log signals and the
# rotation rule, write the reports. Shared by .github/workflows/chart-forward.yml (API key feed) and the Claude connector
# feed (docs/forward-feed.md). Research only: it never previews, fills or places an order. Pushing is the caller's job.
#   scripts/forward_run.sh SHADOW_CHECKOUT                 # fetch with ALPHAVANTAGE_API_KEY
#   scripts/forward_run.sh SHADOW_CHECKOUT --from-dir DIR  # read DIR/<SYMBOL>.csv saved by the connector feed
set -euo pipefail
D="$1/chart-forward"
FROM=() FEED=key
if [ "${2:-}" = "--from-dir" ]; then FROM=(--from-dir "$3"); FEED=connector; fi
mkdir -p "$D/data" "$D/etf"
for f in chart/data/*.csv; do [ -e "$D/data/$(basename "$f")" ] || cp "$f" "$D/data/"; done
for f in chart/data/etf/*.csv; do [ -e "$D/etf/$(basename "$f")" ] || cp "$f" "$D/etf/"; done
python -m chart update "$D/data" "${FROM[@]}"
python -m chart update "$D/etf" --all "${FROM[@]}"
python -m chart validate "$D"/data/*.csv "$D"/etf/*.csv > "$D/VALIDATE.json" || echo "validation problems: see VALIDATE.json"
python -m chart forward record "$D/data" --log "$D/signals.jsonl"
python -m chart forward report "$D/data" --log "$D/signals.jsonl" > "$D/REPORT.json"
python -m chart forward rotation-record "$D/etf" --log "$D/rotation.jsonl"
if [ -s "$D/rotation.jsonl" ]; then
  python -m chart forward rotation-report "$D/etf" --log "$D/rotation.jsonl" > "$D/ROTATION.json"
  python -m chart forward rotation-tickets "$D/etf" --log "$D/rotation.jsonl" --tickets "$D/rotation_tickets.jsonl"
fi
# Defensive variant logged alongside on paper: the same rule, in cash while the basket is below its 200-session average.
python -m chart forward rotation-record "$D/etf" --trend 200 --log "$D/rotation_trend200.jsonl"
if [ -s "$D/rotation_trend200.jsonl" ]; then
  python -m chart forward rotation-report "$D/etf" --log "$D/rotation_trend200.jsonl" > "$D/ROTATION_TREND200.json"
fi
python -m chart overlay "$D/data/SPY.csv" --status > "$D/OVERLAY.json"     # regime flag, information only
python -m chart doctor "$D/data" "$D/etf" --feed "$FEED" > "$D/DOCTOR.json" || true
if [ -s "$D/rotation.jsonl" ]; then
  python -m chart forward rotation-brief "$D/etf" --log "$D/rotation.jsonl" --tickets "$D/rotation_tickets.jsonl" \
    --trend-log "$D/rotation_trend200.jsonl" --doctor "$D/DOCTOR.json" --overlay "$D/OVERLAY.json" > "$D/BRIEF.md"
fi
