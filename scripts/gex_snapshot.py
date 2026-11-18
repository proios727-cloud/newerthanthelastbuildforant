#!/usr/bin/env python3
"""Dealer-gamma (GEX) snapshot from a recorded option chain. RESEARCH / PAPER ONLY: reads a chain JSON file and writes
files; it never contacts a broker and nothing here places, previews, cancels or exercises an order.

Usage: python scripts/gex_snapshot.py CHAIN.json [--out DIR]

Writes DIR/gex.json {symbol, spot, asof, net_gex, flip, king, call_wall, put_wall, regime, by_strike:[{strike, gex}]}
(by_strike limited to +/-5% of spot, gex = call + put dollars per 1% move), appends one line to DIR/gex_log.jsonl and
prints a 3-line summary. Regime is "positive" or "negative" net gamma. Stdlib only.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import options  # noqa: E402


def snapshot(chain):
    m = options.gex_map(chain)
    by = options.gex_by_strike(chain)
    spot = chain["spot"]
    return {
        "symbol": chain.get("symbol"), "spot": spot, "asof": chain.get("asof"),
        "net_gex": m.net, "flip": m.flip, "king": m.king, "call_wall": m.call_wall, "put_wall": m.put_wall,
        "regime": "positive" if m.net > 0 else "negative",
        "by_strike": [{"strike": s, "gex": sum(by[s])} for s in sorted(by) if abs(s - spot) <= 0.05 * spot],
    }


def _money(x):
    a = abs(x)
    s = f"${a / 1e9:.2f}B" if a >= 1e9 else f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a:,.0f}"
    return ("-" if x < 0 else "") + s


def summary(snap):
    flip = "none" if snap["flip"] is None else f"{snap['flip']:g}"
    return "\n".join([
        f"{snap['symbol']} spot {snap['spot']:g} as of {snap['asof']}",
        f"net GEX {_money(snap['net_gex'])} per 1% move ({snap['regime']} gamma), flip {flip}",
        f"king {snap['king']:g}, call wall {snap['call_wall']:g}, put wall {snap['put_wall']:g} (research only)",
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("chain")
    ap.add_argument("--out", default="gex")
    a = ap.parse_args(argv)
    chain = json.loads(pathlib.Path(a.chain).read_text(encoding="utf-8"))
    snap = snapshot(chain)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gex.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    with open(out / "gex_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({k: v for k, v in snap.items() if k != "by_strike"}) + "\n")
    print(summary(snap))


if __name__ == "__main__":
    main()
