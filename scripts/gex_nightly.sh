#!/usr/bin/env bash
# Nightly read-only GEX capture persistence (README "Nightly GEX capture"). Research only: reads a session transcript and
# writes files; places, previews, cancels or exercises no order.
#   SINCE=2026-11-18T01:40:00Z scripts/gex_nightly.sh [SYMBOL=SPY]
# After a Claude session made the READ-ONLY connector calls (see scripts/gex_plan.py), this converts them with
# rh_chain_from_transcript.py --since $SINCE into $GEX_DIR/chains, requires a chain for SYMBOL with >= 40 contracts, copies it
# to shadow-data gex-desk/chains/, runs gex_snapshot.py into gex-desk/ (gex.json, growing gex_log.jsonl), builds
# $GEX_DIR/dashboard.html (--gex), commits as chart-forward and pushes (3 tries, pull --rebase), prints one JSON line.
# Env: BASE (default claude/great-keller-rf23ab), GEX_DIR (default /tmp/gex-nightly), SINCE (required, exit 2 if missing),
# DRY_RUN=1 stages but does not commit or push. Failure to find a good chain exits 1 with nothing staged.
set -euo pipefail
SYM="${1:-SPY}"
BASE="${BASE:-claude/great-keller-rf23ab}"
G="${GEX_DIR:-/tmp/gex-nightly}"
[ -n "${SINCE:-}" ] || { echo "SINCE (ISO time the capture began) is required" >&2; exit 2; }
REPO="$(git rev-parse --show-toplevel)"

cleanup() {
  for w in "$G/code" "$G/data"; do
    [ -d "$w" ] && git -C "$REPO" worktree remove --force "$w" 2>/dev/null || true
  done
  git -C "$REPO" worktree prune
}
trap cleanup EXIT

git -C "$REPO" fetch -q origin "$BASE" shadow-data
cleanup
rm -rf "$G" && mkdir -p "$G"
git -C "$REPO" worktree add -q --detach "$G/code" "origin/$BASE"
git -C "$REPO" worktree add -q --detach "$G/data" origin/shadow-data

(cd "$G/code" && python3 scripts/rh_chain_from_transcript.py "" "$G/chains" --since "$SINCE") >&2 \
  || { echo "chain conversion failed; nothing committed or pushed" >&2; exit 1; }

chain="$(ls -t "$G/chains/$SYM"-*.json 2>/dev/null | head -1 || true)"
[ -n "$chain" ] || { echo "no $SYM chain since $SINCE; nothing committed or pushed" >&2; exit 1; }
n="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["contracts"]))' "$chain")"
[ "$n" -ge 40 ] || { echo "$SYM chain has only $n contracts (<40); nothing committed or pushed" >&2; exit 1; }

out="$G/data/gex-desk"
mkdir -p "$out/chains"
cp "$chain" "$out/chains/"
(cd "$G/code" && python3 scripts/gex_snapshot.py "$out/chains/$(basename "$chain")" --out "$out") >&2
(cd "$G/code" && python3 scripts/build_dashboard.py --gex "$chain" --out "$G/dashboard.html") >&2

day="$(TZ=America/New_York date +%Y-%m-%d)"
git -C "$G/data" add gex-desk
if [ -n "${DRY_RUN:-}" ]; then
  commit="dry run: $(git -C "$G/data" diff --cached --name-only | wc -l) files staged, not committed"
elif git -C "$G/data" diff --cached --quiet; then
  commit="nothing new"
else
  git -C "$G/data" -c user.name=chart-forward -c user.email=chart-forward@users.noreply.github.com \
    commit -qm "gex desk $day (nightly read-only capture)"
  for i in 1 2 3; do
    git -C "$G/data" push -q origin HEAD:shadow-data && break
    [ "$i" = 3 ] && { echo "push to shadow-data failed" >&2; exit 1; }
    git -C "$G/data" pull -q --rebase origin shadow-data
  done
  commit="$(git -C "$G/data" rev-parse --short HEAD)"
fi
python3 - "$out" "$commit" "$n" <<'PY'
import json, pathlib, sys
d, commit, n = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
g = json.loads((d / "gex.json").read_text())
print(json.dumps({"commit": commit, "symbol": g["symbol"], "spot": g["spot"], "asof": g["asof"], "contracts": n,
                  "net_gex": g["net_gex"], "regime": g["regime"], "king": g["king"], "call_wall": g["call_wall"],
                  "put_wall": g["put_wall"], "flip": g["flip"],
                  "log_lines": len((d / "gex_log.jsonl").read_text().splitlines())}))
PY
