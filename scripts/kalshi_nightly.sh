#!/usr/bin/env bash
# The nightly Kalshi paper scan (README "Kalshi desk scan"). Research only: public GET requests, no key, no orders.
#   scripts/kalshi_nightly.sh
# Fresh worktrees of the base branch ($KALSHI_DIR/code) and shadow-data ($KALSHI_DIR/data), runs
# `python3 -m kalshi.desk scan` into shadow-data's kalshi-desk/ (scan.json, kalshi_desk.json, paper_log.jsonl growing each
# night, scans/YYYY-MM-DD.json as a dated copy), builds $KALSHI_DIR/dashboard.html, commits as chart-forward and pushes
# shadow-data (3 tries with pull --rebase), prints one JSON summary line, and removes the worktrees (also on failure).
# Run from any checkout of the repo. BASE (default claude/great-keller-rf23ab) picks the code; KALSHI_DIR (default
# /tmp/kalshi-nightly) holds the worktrees; SERIES (default "KXBTC15M KXETH15M"); DRY_RUN=1 stages but does not commit or push.
# If the scan fails (network) nothing is committed or pushed and the exit status is non-zero.
set -euo pipefail
BASE="${BASE:-claude/great-keller-rf23ab}"
K="${KALSHI_DIR:-/tmp/kalshi-nightly}"
SERIES="${SERIES:-KXBTC15M KXETH15M}"
REPO="$(git rev-parse --show-toplevel)"

cleanup() {
  for w in "$K/code" "$K/data"; do
    [ -d "$w" ] && git -C "$REPO" worktree remove --force "$w" 2>/dev/null || true
  done
  git -C "$REPO" worktree prune
}
trap cleanup EXIT

git -C "$REPO" fetch -q origin "$BASE" shadow-data
cleanup
rm -rf "$K" && mkdir -p "$K"
git -C "$REPO" worktree add -q --detach "$K/code" "origin/$BASE"
git -C "$REPO" worktree add -q --detach "$K/data" origin/shadow-data

out="$K/data/kalshi-desk"
# shellcheck disable=SC2086
(cd "$K/code" && python3 -m kalshi.desk scan --series $SERIES --out "$out") >&2 \
  || { echo "kalshi scan failed; nothing committed or pushed" >&2; exit 1; }
day="$(TZ=America/New_York date +%Y-%m-%d)"
mkdir -p "$out/scans"
cp "$out/scan.json" "$out/scans/$day.json"
(cd "$K/code" && python3 scripts/build_dashboard.py --kalshi-scan "$out/scan.json" --out "$K/dashboard.html") >&2

git -C "$K/data" add kalshi-desk
if [ -n "${DRY_RUN:-}" ]; then
  commit="dry run: $(git -C "$K/data" diff --cached --name-only | wc -l) files staged, not committed"
elif git -C "$K/data" diff --cached --quiet; then
  commit="nothing new"
else
  git -C "$K/data" -c user.name=chart-forward -c user.email=chart-forward@users.noreply.github.com \
    commit -qm "kalshi desk $day (nightly paper scan)"
  for i in 1 2 3; do
    git -C "$K/data" push -q origin HEAD:shadow-data && break
    [ "$i" = 3 ] && { echo "push to shadow-data failed" >&2; exit 1; }
    git -C "$K/data" pull -q --rebase origin shadow-data
  done
  commit="$(git -C "$K/data" rev-parse --short HEAD)"
fi
python3 - "$out" "$commit" <<'PY'
import json, pathlib, sys
d, commit = pathlib.Path(sys.argv[1]), sys.argv[2]
scan = json.loads((d / "scan.json").read_text())
s = scan["summary"]
priced = [r for r in scan["rows"] if r.get("edge_c") is not None]
best = max(priced, key=lambda r: r["edge_c"]) if priced else None
print(json.dumps({"commit": commit, "as_of": scan["as_of"], "markets": s["markets"], "locks": s["locks"],
                  "best_ticker": best["ticker"] if best else None, "best_edge_cents": s.get("best_edge_c"),
                  "log_lines": len((d / "paper_log.jsonl").read_text().splitlines())}))
PY
