"""Backup feed: save ThetaData end-of-day bars a Claude session fetched as <SYMBOL>.csv files in Alpha Vantage's csv format.
Alpha Vantage stays primary: a symbol that already has OUTDIR/<SYMBOL>.csv is never overwritten.
    python3 scripts/theta_from_transcript.py OUTDIR [TRANSCRIPT.jsonl] [--since ISO] [--check-dir CHART_FORWARD_DIR]
Reads mcp__ThetaData__stock_history_eod results. With --check-dir, a symbol is saved only if its close agrees within 0.1%
with the stored bar (CHART_FORWARD_DIR/data|etf/<SYMBOL>.csv) on every date both have, and at least one date overlaps.
Prints {"saved", "skipped_primary", "rejected", "errors"} as JSON.
"""
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _transcript import newest_transcript, tool_results  # noqa: E402
from chart.update import parse_av_csv  # noqa: E402

TOL = 0.001


def to_av_csv(raw):
    """Alpha Vantage style csv text from a stock_history_eod result; raises ValueError if no usable bar."""
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ValueError(raw[:200])
    rows = body.get("response") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        err = body.get("error") if isinstance(body, dict) else None
        raise ValueError((json.dumps(err) if err else raw)[:200])
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        day = str(r.get("created") or r.get("last_trade") or "")[:10]
        try:
            o, h, lo, c = (float(r[k]) for k in ("open", "high", "low", "close"))
            v = int(float(r.get("volume") or 0))
        except (KeyError, TypeError, ValueError):
            continue
        if len(day) != 10 or c == 0:
            continue
        out.append((day, o, h, lo, c, v))
    if not out:
        raise ValueError("no usable bars")
    lines = ["timestamp,open,high,low,close,volume"]
    for day, o, h, lo, c, v in sorted(out, reverse=True):
        lines.append(f"{day},{o!r},{h!r},{lo!r},{c!r},{v}")
    text = "\r\n".join(lines) + "\r\n"
    parse_av_csv(text)
    return text


def extract(lines, since=""):
    """({symbol: csv text}, {symbol: error}); the last good result per symbol wins and a later failure doesn't undo it."""
    good, bad = {}, {}
    for _, args, raw in tool_results(lines, lambda n: n.endswith("__stock_history_eod"), since=since):
        sym = args.get("symbol", "").upper()
        try:
            good[sym] = to_av_csv(raw)
            bad.pop(sym, None)
        except ValueError as e:
            if sym not in good:
                bad[sym] = str(e)[:200]
    return good, bad


def stored_closes(check_dir, sym):
    for sub in ("data", "etf"):
        p = pathlib.Path(check_dir) / sub / f"{sym}.csv"
        if p.exists():
            with p.open(newline="") as f:
                return {r["date"][:10]: float(r["close"]) for r in csv.DictReader(f)}
    return None


def check(text, stored):
    """None if the close agrees with the stored bars on all shared dates (and there is one), else the reason."""
    if stored is None:
        return "no stored csv to check against"
    shared = [(d, c, stored[d[:10]]) for d, _, _, _, c, _ in parse_av_csv(text) if d[:10] in stored]
    if not shared:
        return "no overlap date with stored bars"
    bad = [f"{d} {c:g} vs stored {s:g}" for d, c, s in shared if abs(c - s) > TOL * abs(s)]
    return ("close mismatch > 0.1%: " + "; ".join(bad)) if bad else None


def main(argv):
    args, since, check_dir = list(argv[1:]), "", None
    for flag in ("--since", "--check-dir"):
        if flag in args:
            i = args.index(flag)
            val = args[i + 1]
            del args[i:i + 2]
            if flag == "--since":
                since = val
            else:
                check_dir = val
    out = pathlib.Path(args[0])
    src = pathlib.Path(args[1]) if len(args) > 1 else newest_transcript()
    good, errors = extract(src.read_text().splitlines(), since)
    out.mkdir(parents=True, exist_ok=True)
    saved, skipped, rejected = [], [], {}
    for sym, text in sorted(good.items()):
        if (out / f"{sym}.csv").exists():
            skipped.append(sym)
            continue
        if check_dir is not None:
            why = check(text, stored_closes(check_dir, sym))
            if why:
                rejected[sym] = why
                continue
        (out / f"{sym}.csv").write_text(text)
        saved.append(sym)
    print(json.dumps({"saved": saved, "skipped_primary": skipped, "rejected": rejected, "errors": errors}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
