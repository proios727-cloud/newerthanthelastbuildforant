"""Save every TradingView OHLCV connector result found in a session transcript as a JSON response file, verbatim.

Small connector results stay inside the transcript instead of being saved to disk. This writes each successful
mcp-tv-get-ohlcv result to OUTDIR/<SYMBOL>-<interval>-<n>.json so scripts/tv_ohlcv_to_csv.py can convert it.
    python3 scripts/tv_from_transcript.py TRANSCRIPT.jsonl OUTDIR [--since ISO_TIME]
"""
import json
import pathlib
import sys


def _text(content):
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    since = argv[argv.index("--since") + 1] if "--since" in argv else ""
    out = pathlib.Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    calls, n = set(), 0
    for line in open(argv[1]):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since and rec.get("timestamp", "") < since:
            continue
        msg = rec.get("message", {})
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get("type") == "tool_use" and c.get("name", "").endswith("mcp-tv-get-ohlcv"):
                calls.add(c["id"])
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                try:
                    body = json.loads(_text(c.get("content")))
                except json.JSONDecodeError:
                    continue
                if body.get("success") and "bars" in body:
                    n += 1
                    sym = body["symbol"].split(":")[-1]
                    dest = out / f"{sym}-{body['interval']}-{n}.json"
                    dest.write_text(json.dumps(body))
                    print(dest)


if __name__ == "__main__":
    main(sys.argv)
