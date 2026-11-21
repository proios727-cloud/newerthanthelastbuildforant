"""Read connector results out of a Claude session transcript (JSON Lines), shared by the *_from_transcript scripts.

Connector results land in the transcript, not on disk; these scripts save them verbatim instead of retyping numbers.
"""
import datetime
import json
import pathlib


def newest_transcript(root=pathlib.Path.home() / ".claude" / "projects"):
    files = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"no transcript under {root}")
    return files[-1]


def text(content):
    """A tool result's content (a string or a list of text blocks) as one string."""
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def _instant(stamp):
    """An ISO time as an aware datetime, or None if it does not parse. A bare time counts as UTC."""
    try:
        t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _before(stamp, since, since_t):
    """True if `stamp` is earlier than `since`. Compares instants, so 00:42:57.184Z is not before 00:42:57Z."""
    t = _instant(stamp)
    if t is None or since_t is None:
        return stamp < since
    return t < since_t


def tool_results(lines, match, since=""):
    """Yield (tool name, tool input, result text) for each tool result whose tool name satisfies `match(name)`.
    `since` skips transcript records stamped before that ISO time."""
    calls = {}
    since_t = _instant(since) if since else None
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and _before(rec.get("timestamp", ""), since, since_t):
            continue
        msg = rec.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and match(c.get("name", "")):
                calls[c["id"]] = (c["name"], c.get("input", {}))
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                name, args = calls[c["tool_use_id"]]
                yield name, args, text(c.get("content"))
