"""Save the Alpha Vantage daily bars a Claude session fetched through the connector as <SYMBOL>.csv files.

Connector results land in the session transcript, not on disk, and retyping 100 rows per fund invites errors. This reads
the transcript and writes each TIME_SERIES_DAILY csv result verbatim, so `chart update --from-dir` gets the vendor's
bytes. Only results that parse as daily bars are written; errors (rate limit, premium) are listed instead.
    python3 scripts/av_from_transcript.py OUTDIR [TRANSCRIPT.jsonl]   # default: the newest transcript under ~/.claude
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _transcript import newest_transcript, tool_results  # noqa: E402
from chart.update import parse_av_csv  # noqa: E402


def extract(lines):
    """{symbol: csv text} for the last good TIME_SERIES_DAILY result per symbol, and {symbol: error} for the rest."""
    good, bad = {}, {}
    for _, args, raw in tool_results(lines, lambda n: n.endswith("__TIME_SERIES_DAILY")):
        sym = args.get("symbol", "").upper()
        try:
            body = json.loads(raw)
            text = body["result"] if isinstance(body, dict) and "result" in body else raw
        except (json.JSONDecodeError, TypeError):
            body, text = None, raw
        try:
            parse_av_csv(text)
            good[sym] = text
            bad.pop(sym, None)
        except (ValueError, KeyError):
            if sym not in good:                   # a retry that failed doesn't undo an earlier good fetch
                err = body.get("error", {}).get("message") if isinstance(body, dict) else None
                bad[sym] = (err or raw)[:200]
    return good, bad


def main(argv):
    out = pathlib.Path(argv[1])
    src = pathlib.Path(argv[2]) if len(argv) > 2 else newest_transcript()
    good, bad = extract(src.read_text().splitlines())
    out.mkdir(parents=True, exist_ok=True)
    for sym, text in good.items():
        (out / f"{sym}.csv").write_text(text)
    print(json.dumps({"transcript": str(src), "saved": sorted(good), "errors": bad}, indent=2))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
