"""Turn Robinhood option-chain responses saved in a session transcript into gex_map.py input files, without retyping.

A subagent (or this session) calls get_equity_quotes, get_option_instruments and get_option_quotes; the responses land in the
transcript JSONL. This joins each instrument (symbol, strike, type, expiry) to its quote (open interest, volume, IV, greeks)
and writes options/data/chains/<SYMBOL>-<asof>.json in the shape gex_map.py documents. Contracts whose IV is missing or a
placeholder (below 1%) are left out and counted, since the map's Black-Scholes rescan needs a real IV.
    python3 scripts/rh_chain_from_transcript.py TRANSCRIPT.jsonl [OUTDIR]
"""
import json
import pathlib
import sys


def _text(content):
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def collect(lines):
    calls, instruments, quotes, spots = {}, {}, {}, {}
    for line in lines:
        try:
            msg = json.loads(line).get("message", {})
        except json.JSONDecodeError:
            continue
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get("type") == "tool_use":
                calls[c["id"]] = c["name"].split("__")[-1]
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                name = calls[c["tool_use_id"]]
                try:
                    data = json.loads(_text(c.get("content"))).get("data", {})
                except (json.JSONDecodeError, AttributeError):
                    continue
                if name == "get_option_instruments":
                    for i in data.get("instruments", []):
                        instruments[i["id"]] = i
                elif name == "get_option_quotes":
                    for r in data.get("results", []):
                        q = r.get("quote") or {}
                        if q.get("instrument_id"):
                            quotes[q["instrument_id"]] = q
                elif name == "get_equity_quotes":
                    for r in data.get("results", []):
                        q = r.get("quote") or {}
                        if q.get("symbol") and _num(q.get("last_trade_price")):
                            spots[q["symbol"]] = (float(q["last_trade_price"]), q.get("venue_last_trade_time"))
    return instruments, quotes, spots


def build(instruments, quotes, spots):
    out = {}
    for iid, inst in instruments.items():
        sym, q = inst["chain_symbol"], quotes.get(iid)
        if sym not in spots or q is None:
            continue
        chain = out.setdefault(sym, {"symbol": sym, "spot": spots[sym][0], "asof": spots[sym][1],
                                     "contracts": [], "skipped_no_iv": 0})
        iv = _num(q.get("implied_volatility"))
        if iv is None or iv < 0.01:
            chain["skipped_no_iv"] += 1
            continue
        chain["contracts"].append({
            "strike": float(inst["strike_price"]), "type": inst["type"], "expiry": inst["expiration_date"],
            "oi": int(_num(q.get("open_interest")) or 0), "volume": int(_num(q.get("volume")) or 0), "iv": iv,
            "gamma": _num(q.get("gamma")), "vega": _num(q.get("vega")), "delta": _num(q.get("delta")),
            "bid": _num(q.get("bid_price")), "ask": _num(q.get("ask_price")),
        })
    for c in out.values():
        c["contracts"].sort(key=lambda k: (k["expiry"], k["strike"], k["type"]))
    return out


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    outdir = pathlib.Path(argv[2] if len(argv) > 2 else "options/data/chains")
    with open(argv[1]) as f:
        chains = build(*collect(f))
    outdir.mkdir(parents=True, exist_ok=True)
    for sym, c in chains.items():
        stamp = (c["asof"] or "")[:16].replace(":", "")
        dest = outdir / f"{sym}-{stamp}.json"
        dest.write_text(json.dumps(c, indent=1))
        print(f"{dest}: spot {c['spot']}, {len(c['contracts'])} contracts, {c['skipped_no_iv']} skipped (no IV)")


if __name__ == "__main__":
    main(sys.argv)
