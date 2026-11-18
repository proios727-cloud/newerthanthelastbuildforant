#!/usr/bin/env bash
# The Claude connector feed's nightly run in two steps around the fetch (docs/forward-feed.md). Research only: it never
# previews, fills or places an order.
#   scripts/forward_feed.sh start    # fresh worktrees of the base branch and shadow-data, stamp the start time, list symbols
#   ... the Claude session calls Alpha Vantage TIME_SERIES_DAILY once per listed symbol ...
#   scripts/forward_feed.sh finish   # save tonight's results, run the forward test, commit and push shadow-data, report,
#                                    # and write the dashboard's files to $FEED_DIR/dash, the review to $FEED_DIR/REVIEW.md
#                                    # and the weekly digest to $FEED_DIR/DIGEST.md
# Run from any checkout of the repo. BASE (default claude/great-keller-rf23ab) picks the code; FEED_DIR (default
# /tmp/chart-feed) holds the worktrees between the two steps. DRY_RUN=1 runs everything but the commit and push.
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
  ;;
finish)
  [ -f "$F/since" ] || { echo "run '$0 start' first" >&2; exit 2; }
  cd "$F/code"
  python3 scripts/av_from_transcript.py "$F/incoming" --since "$(cat "$F/since")" > "$F/saved.json" || true
  scripts/forward_run.sh "$F/data" --from-dir "$F/incoming" > "$F/run.log" 2>&1
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
doctor = json.loads((d / "DOCTOR.json").read_text())
out = {"commit": commit, "saved": len(saved["saved"]), "missing": [s for s in want if s not in saved["saved"]],
       "fetch_errors": saved["errors"], "doctor_ok": doctor["ok"], "doctor_problems": doctor["problems"]}
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
  echo "usage: $0 start|finish" >&2; exit 2 ;;
esac
