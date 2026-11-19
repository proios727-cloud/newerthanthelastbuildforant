#!/usr/bin/env bash
# The Claude connector feed's nightly run in steps around the fetch (docs/forward-feed.md). Research only: it never
# previews, fills or places an order.
#   scripts/forward_feed.sh start    # fresh worktrees of the base branch and shadow-data, stamp the start time, list symbols,
#                                    # and work out when the first call may go (scripts/feed_window.py)
#   scripts/forward_feed.sh wait     # sleep until then (at most WAIT_CAP seconds, default 1200; exits 3 if still shut)
#   ... the Claude session calls Alpha Vantage TIME_SERIES_DAILY once per listed symbol ...
#   scripts/forward_feed.sh missing  # save what AV returned, then print one `backup: SYM from YYYYMMDD to YYYYMMDD` line per symbol
#                                    # still missing, for the ThetaData stock_history_eod backup calls (docs/forward-feed.md)
#   ... the session calls mcp__ThetaData__stock_history_eod for each line printed ...
#   scripts/forward_feed.sh finish   # save tonight's results, run the forward test, commit and push shadow-data, report,
#                                    # and write the dashboard's files to $FEED_DIR/dash, the review to $FEED_DIR/REVIEW.md
#                                    # and the weekly digest to $FEED_DIR/DIGEST.md
# Run from any checkout of the repo. BASE (default claude/great-keller-rf23ab) picks the code; FEED_DIR (default
# /tmp/chart-feed) holds the worktrees between the two steps. DRY_RUN=1 runs everything but the commit and push.
# MARGIN (default 180) is how many seconds past 24 hours after last night's first call tonight's first call waits;
# `finish` records tonight's times in chart-forward/FEED_RUN.json for tomorrow's `start`.
set -euo pipefail
BASE="${BASE:-claude/great-keller-rf23ab}"
F="${FEED_DIR:-/tmp/chart-feed}"
REPO="$(git rev-parse --show-toplevel)"

case "${1:-}" in
start)
  git -C "$REPO" fetch -q origin "$BASE" shadow-data
  for w in "$F/code" "$F/data"; do [ -d "$w" ] && git -C "$REPO" worktree remove --force "$w"; done
  git -C "$REPO" worktree prune
  rm -rf "$F" && mkdir -p "$F/incoming"
  git -C "$REPO" worktree add -q --detach "$F/code" "origin/$BASE"
  git -C "$REPO" worktree add -q --detach "$F/data" origin/shadow-data
  date -u +%Y-%m-%dT%H:%M:%SZ > "$F/since"
  echo "started $(cat "$F/since") on $BASE @ $(git -C "$F/code" rev-parse --short HEAD)"
  echo "symbols: $(cd "$F/code" && ls chart/data/*.csv chart/data/etf/*.csv | xargs -n1 basename | sed 's/\.csv$//' | tr '\n' ' ')"
  python3 "$F/code/scripts/feed_window.py" "$F/data/chart-forward/FEED_RUN.json" "$F/fetch_after" "${MARGIN:-180}"
  ;;
wait)
  [ -f "$F/fetch_after" ] || { echo "run '$0 start' first" >&2; exit 2; }
  left=$(( $(date -u -d "$(cat "$F/fetch_after")" +%s) - $(date -u +%s) ))
  cap="${WAIT_CAP:-1200}"
  if [ "$left" -gt "$cap" ]; then
    # Capped: the window is still shut, so keep the stored time; run 'wait' again before any call.
    echo "first call due in $left s; waiting only $cap s" >&2
    sleep "$cap"
    echo "not yet: first call due at $(cat "$F/fetch_after"); run 'scripts/forward_feed.sh wait' again" >&2
    exit 3
  fi
  if [ "$left" -gt 0 ]; then sleep "$left"; fi
  date -u +%Y-%m-%dT%H:%M:%SZ > "$F/fetch_after"     # the time the calls really start, recorded by finish
  echo "fetch from $(cat "$F/fetch_after")"
  ;;
missing)
  [ -f "$F/since" ] || { echo "run '$0 start' first" >&2; exit 2; }
  cd "$F/code"
  python3 scripts/av_from_transcript.py "$F/incoming" --since "$(cat "$F/since")" > "$F/saved.json" || true
  to="$(TZ=America/New_York date +%Y%m%d)"
  none=1
  for s in $(ls chart/data/*.csv chart/data/etf/*.csv | xargs -n1 basename | sed 's/\.csv$//'); do
    [ -f "$F/incoming/$s.csv" ] && continue
    stored="$F/data/chart-forward/data/$s.csv"; [ -f "$stored" ] || stored="$F/data/chart-forward/etf/$s.csv"
    [ -f "$stored" ] || { echo "backup: $s has no stored bars in chart-forward" >&2; continue; }
    from="$(tail -n 1 "$stored" | cut -d, -f1 | tr -d -)"
    echo "backup: $s from $from to $to"; none=0
  done
  if [ "$none" = 1 ]; then echo "backup: none"; fi
  ;;
finish)
  [ -f "$F/since" ] || { echo "run '$0 start' first" >&2; exit 2; }
  cd "$F/code"
  python3 scripts/av_from_transcript.py "$F/incoming" --since "$(cat "$F/since")" > "$F/saved.json" || true
  python3 scripts/theta_from_transcript.py "$F/incoming" --since "$(cat "$F/since")" --check-dir "$F/data/chart-forward" > "$F/backup.json" || true
  scripts/forward_run.sh "$F/data" --from-dir "$F/incoming" > "$F/run.log" 2>&1
  first="$(cat "$F/fetch_after" 2>/dev/null || cat "$F/since")"    # tonight's first call, for tomorrow's start
  printf '{"started": "%s", "fetch_after": "%s", "finished": "%s"}\n' "$(cat "$F/since")" "$first" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$F/data/chart-forward/FEED_RUN.json"
  git -C "$F/data" add chart-forward
  if [ -n "${DRY_RUN:-}" ]; then
    commit="dry run: $(git -C "$F/data" diff --cached --name-only | wc -l) files staged, not committed"
  elif git -C "$F/data" diff --cached --quiet; then
    commit="nothing new"
  else
    git -C "$F/data" -c user.name=chart-forward -c user.email=chart-forward@users.noreply.github.com \
      commit -qm "chart forward $(TZ=America/New_York date +%Y-%m-%d) (connector feed)"
    for i in 1 2 3; do
      git -C "$F/data" push -q origin HEAD:shadow-data && break
      [ "$i" = 3 ] && { echo "push to shadow-data failed" >&2; exit 1; }
      git -C "$F/data" pull -q --rebase origin shadow-data
    done
    commit="$(git -C "$F/data" rev-parse --short HEAD)"
  fi
  python3 - "$F" "$commit" <<'PY'
import json, pathlib, sys
f, commit = pathlib.Path(sys.argv[1]), sys.argv[2]
code, d = f / "code", f / "data" / "chart-forward"
want = sorted(p.stem for p in [*(code / "chart/data").glob("*.csv"), *(code / "chart/data/etf").glob("*.csv")])
saved = json.loads((f / "saved.json").read_text()) if (f / "saved.json").stat().st_size else {"saved": [], "errors": {}}
bk = f / "backup.json"
backup = json.loads(bk.read_text()) if bk.exists() and bk.stat().st_size else {"saved": [], "rejected": {}}
doctor = json.loads((d / "DOCTOR.json").read_text())
got = set(saved["saved"]) | set(backup["saved"])
out = {"commit": commit, "saved": len(saved["saved"]), "backup": backup["saved"], "backup_rejected": backup["rejected"],
       "missing": [s for s in want if s not in got], "fetch_errors": saved["errors"], "doctor_ok": doctor["ok"], "doctor_problems": doctor["problems"]}
rot = d / "ROTATION.json"
if rot.exists():
    periods = json.loads(rot.read_text()).get("periods", [])
    if periods:
        p = periods[-1]
        out["period"] = {k: p[k] for k in ("decided", "from", "to", "picks", "rule", "basket")}
log = d / "rotation.jsonl"
newest = max((data["newest_bar"] for data in doctor["data"].values()), default="")
if log.exists() and log.read_text().strip():
    last = json.loads(log.read_text().strip().splitlines()[-1])
    out["decision_tonight"] = last.get("as_of") == newest
print(json.dumps(out, indent=2))
PY
  # Keep tonight's brief outside the worktrees so the session can quote it on a decision night, and write the
  # forward-test dashboard's five files (status, daily, holdings, ranking, review) to $F/dash for upload.
  [ -f "$F/data/chart-forward/BRIEF.md" ] && cp "$F/data/chart-forward/BRIEF.md" "$F/BRIEF.md"
  python3 "$F/code/scripts/forward_dashboard.py" "$F/data/chart-forward" "$F/dash" >/dev/null
  python3 "$F/code/scripts/rotation_review.py" "$F/data/chart-forward" "$F/REVIEW.md" || true   # exit 1 = a flag to read
  python3 "$F/code/scripts/forward_digest.py" "$F/data/chart-forward" "$F/DIGEST.md" || echo "digest failed" >&2   # the Friday report; never blocks cleanup
  cd "$REPO"
  git -C "$REPO" worktree remove --force "$F/data"
  git -C "$REPO" worktree remove --force "$F/code"
  ;;
*)
  echo "usage: $0 start|wait|missing|finish" >&2; exit 2 ;;
esac
