"""Save every TradingView OHLCV connector result found in a session transcript as a JSON response file, verbatim.

Small connector results stay inside the transcript instead of being saved to disk. This writes each successful
mcp-tv-get-ohlcv result to OUTDIR/<SYMBOL>-<interval>-<n>.json so scripts/tv_ohlcv_to_csv.py can convert it.
    python3 scripts/tv_from_transcript.py TRANSCRIPT.jsonl OUTDIR [--since ISO_TIME]
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _transcript import tool_results  # noqa: E402


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    since = argv[argv.index("--since") + 1] if "--since" in argv else ""
    out = pathlib.Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(argv[1]) as f:
        for _, _, raw in tool_results(f, lambda name: name.endswith("mcp-tv-get-ohlcv"), since):
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if body.get("success") and "bars" in body:
                n += 1
                dest = out / f"{body['symbol'].split(':')[-1]}-{body['interval']}-{n}.json"
                dest.write_text(json.dumps(body))
                print(dest)


if __name__ == "__main__":
    main(sys.argv)
