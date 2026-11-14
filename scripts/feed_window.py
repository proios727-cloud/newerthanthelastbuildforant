"""When tonight's first Alpha Vantage call may go, for the connector feed (scripts/forward_feed.sh, docs/forward-feed.md).

The free tier allows 25 calls per rolling 24 hours, and the feed makes 21 a night, so a call made before the call it
replaces from last night is 24 hours old is refused. Starting the night's calls MARGIN seconds after last night's first
call turned 24 hours old keeps every call clear of the window. Last night's first call time comes from
chart-forward/FEED_RUN.json on shadow-data, which `forward_feed.sh finish` writes.
    python3 scripts/feed_window.py FEED_RUN.json OUT [MARGIN]    # writes the time to OUT and prints a one-line note
"""
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

MARGIN = 180


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def fetch_after(prev, now, margin=MARGIN):
    """(time the first call may go, reason). `prev` is last night's FEED_RUN.json contents, or None."""
    last = (prev or {}).get("fetch_after")
    if not last:
        return now, "no earlier run recorded"
    return max(now, _parse(last) + timedelta(days=1, seconds=margin)), f"last night's first call {last}"


def main(argv):
    prev_path, out = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    margin = int(argv[3]) if len(argv) > 3 else MARGIN
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    when, why = fetch_after(prev, now, margin)
    out.write_text(when.strftime("%Y-%m-%dT%H:%M:%SZ"))
    print(f"fetch after: {out.read_text()} (wait {int((when - now).total_seconds())} s; {why})")


if __name__ == "__main__":
    main(sys.argv)
