"""Paper-fund CLI. State lives in ledger/ (state.json, previews.json, events.jsonl).

  python -m fund init [--force]
  python -m fund mark SYMBOL PRICE [--bid B --ask A] [--ts ISO]
  python -m fund preview SYMBOL buy|sell QTY --price P [--bid B --ask A] [--adv N] [--stop S --target T] [--ts ISO]
  python -m fund approve PREVIEW_ID WORD
  python -m fund status
  python -m fund sync-board          # write ledger numbers into desk.json tiles/funnel, rebuild board.html
  python -m fund loop [--once] [--every SEC] [--max-ticks N] [--no-sync]   # live Alpha Vantage marks
  python -m fund ingest FILE|-       # mark from agent-pushed quotes JSON (no request budget)
"""
import argparse
import json
import pathlib
import os
import subprocess
import sys
import time

from . import clock, config, feed, preview, risk
from .config import ROOT
from .ledger import Ledger, parse_ts

DIR = ROOT / "ledger"
STATE, PREVIEWS, EVENTS = DIR / "state.json", DIR / "previews.json", DIR / "events.jsonl"
FEED = DIR / "feed.json"


def log(kind, **data):
    DIR.mkdir(exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": clock.now().isoformat(), "kind": kind, **data}) + "\n")


def load_ledger():
    if not STATE.exists():
        sys.exit("no ledger — run: python -m fund init")
    return Ledger.load(STATE)


def load_previews():
    return json.loads(PREVIEWS.read_text()) if PREVIEWS.exists() else {}


def save_previews(p):
    PREVIEWS.write_text(json.dumps(p, indent=2))


def ts_arg(a):
    return parse_ts(a.ts) if a.ts else clock.now()


def cmd_init(a, cfg):
    if STATE.exists() and not a.force:
        sys.exit(f"{STATE} exists — use --force to reset the paper fund")
    Ledger(cfg.starting_nav).save(STATE)
    save_previews({})
    log("init", starting_nav=cfg.starting_nav)
    print(f"paper fund initialized at {cfg.starting_nav:,.2f}")


def cmd_mark(a, cfg):
    L = load_ledger()
    L.mark(a.symbol, a.price, ts_arg(a), a.bid, a.ask)
    L.save(STATE)
    log("mark", symbol=a.symbol, price=a.price, bid=a.bid, ask=a.ask)
    print(json.dumps(L.snapshot(), indent=2))


def cmd_preview(a, cfg):
    L = load_ledger()
    ts = ts_arg(a)
    o = risk.Order(a.symbol, a.side, a.qty, a.price, ts, a.bid, a.ask, a.adv)
    try:
        p = preview.build(o, L, cfg, ts, stop=a.stop, target=a.target)
    except preview.GateError as e:
        log("veto", symbol=a.symbol, side=a.side, qty=a.qty, reason=str(e))
        sys.exit(str(e))
    ps = load_previews()
    ps[p["id"]] = p
    save_previews(ps)
    log("preview", id=p["id"], symbol=p["symbol"], side=p["side"], qty=p["qty"], limit=p["limit"])
    print(json.dumps(p, indent=2))
    print(f"\nReply `python -m fund approve {p['id']} {cfg.approval_word}` within {cfg.limits.preview_ttl_sec:.0f}s.")


def cmd_approve(a, cfg):
    L, ps = load_ledger(), load_previews()
    p = ps.get(a.id) or sys.exit(f"no preview {a.id}")
    try:
        rec = preview.approve(p, a.word, L, cfg, clock.now())
    except preview.GateError as e:
        save_previews(ps)
        log("approve_refused", id=a.id, reason=str(e))
        sys.exit(str(e))
    L.save(STATE)
    save_previews(ps)
    log("fill", **rec)
    print(json.dumps(rec, indent=2))


def cmd_status(a, cfg):
    L = load_ledger()
    snap = L.snapshot()
    snap["mode"] = cfg.mode
    snap["awaiting_approval"] = [k for k, p in load_previews().items() if p["status"] == "awaiting_approval"]
    fs = feed.load_state(FEED)
    snap["feed"] = {"date": fs["date"], "used": fs["used"], "last_fetch": fs["last_fetch"]}
    print(json.dumps(snap, indent=2))


def fmt_money(x):
    return f"${x:,.0f}"


FEED_KEEP = 20


def cmd_sync_board(a, cfg):
    path = ROOT / "desk.json"
    desk = json.loads(path.read_text(encoding="utf-8"))
    L, ps = load_ledger(), load_previews()
    s = L.snapshot()
    waiting = sum(1 for p in ps.values() if p["status"] == "awaiting_approval")
    tr = lambda x: "up" if x > 0 else "down" if x < 0 else "flat"
    tiles = {
        "Paper NAV": (fmt_money(s["nav"]), tr(s["nav"] - L.starting_nav)),
        "Day P&L": (f"{s['day_pnl']:+,.0f} ({s['day_pnl_pct']:+.2f}%)", tr(s["day_pnl"])),
        "Gross exposure": (f"{s['gross_pct']:.1f}%", "flat"),
        "Drawdown from peak": (f"{s['drawdown_pct']:.2f}%", "down" if s["drawdown_pct"] > 0 else "flat"),
        "Previews awaiting EXECUTE": (str(waiting), "flat"),
    }
    for t in desk["tiles"]:
        if t["label"] in tiles:
            t["value"], t["trend"] = tiles[t["label"]]
    counts = {"Previewed": len(ps),
              "Approved": sum(1 for p in ps.values() if p["status"] == "filled_paper"),
              "Filled (paper)": len(L.fills)}
    for f in desk["funnel"]:
        if f["stage"] in counts:
            f["count"] = counts[f["stage"]]
    used = max(0.0, -s["day_pnl_pct"]) / cfg.limits.day_loss_halt_pct * 100
    for w in desk["watch"]:
        if w["label"] == "Risk budget used today":
            w["value"] = f"{used:.0f}%"
        sym = w["label"].split(" (")[0]
        m = L.marks.get(sym)
        if m:
            t = clock.to_et(parse_ts(m["ts"]))
            w["label"] = f"{sym} ({t:%m-%d %H:%M} ET)"
            w["value"] = f"{m['price']:,.2f}"
            w["delta"] = f"bid {m['bid']:,.2f} / ask {m['ask']:,.2f}" if m.get("bid") and m.get("ask") else ""
    if getattr(a, "note", None):
        desk["feed"] = (desk["feed"] + [{"t": f"{clock.to_et(clock.now()):%H:%M}", "agent": "quant", "msg": a.note}])[-FEED_KEEP:]
    path.write_text(json.dumps(desk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts/build_board.py"), str(path), "--out", str(ROOT / "board.html")], check=True)


def _feed_note(rep):
    parts = [f"{m['symbol']} {m['price']:,.2f}" for m in rep["marked"]]
    if rep["errors"]:
        parts.append(f"{len(rep['errors'])} error(s)" + (" · rate-limited, backing off" if rep["rate_limited"] else ""))
    return f"Live marks: {', '.join(parts)} (requests {rep['used']}/{rep['daily']} today)"


def run_tick(cfg, source, now, sync=True, sleep=time.sleep):
    L, st = load_ledger(), feed.load_state(FEED)
    fcfg = feed.feed_config(json.loads((ROOT / "desk.json").read_text(encoding="utf-8"))["fund"])
    rep = feed.tick(L, st, source, cfg.universe, fcfg, now, sleep=sleep)
    L.save(STATE)
    feed.save_state(st, FEED)
    if rep["planned"]:
        log("feed_tick", **{k: rep[k] for k in ("planned", "marked", "skipped", "errors", "used")})
    if sync and (rep["marked"] or rep["errors"]):
        cmd_sync_board(argparse.Namespace(note=_feed_note(rep)), cfg)
    return rep


def cmd_loop(a, cfg):
    load_ledger()
    fcfg = feed.feed_config(json.loads((ROOT / "desk.json").read_text(encoding="utf-8"))["fund"])
    try:
        source = feed.AlphaVantage(os.environ.get(fcfg["key_env"]))
    except feed.FeedError as e:
        sys.exit(f"{e} ({fcfg['key_env']})")
    n = 0
    while True:
        rep = run_tick(cfg, source, clock.now(), sync=not a.no_sync)
        print(json.dumps(rep), flush=True)
        n += 1
        if a.once or (a.max_ticks and n >= a.max_ticks):
            break
        time.sleep(a.every)


def cmd_ingest(a, cfg):
    L = load_ledger()
    raw = sys.stdin.read() if a.file == "-" else pathlib.Path(a.file).read_text(encoding="utf-8")
    try:
        quotes = feed.load_quotes(json.loads(raw), clock.now())
    except (feed.FeedError, KeyError, ValueError) as e:
        sys.exit(f"bad quotes: {e}")
    marked, skipped = feed.apply(L, quotes, cfg.universe)
    L.save(STATE)
    log("ingest", marked=marked, skipped=skipped)
    rep = {"ts": clock.now().isoformat(), "marked": marked, "skipped": skipped, "errors": [],
           "rate_limited": False, "used": "-", "daily": "-"}
    print(json.dumps({"marked": marked, "skipped": skipped}, indent=2))
    if marked and not a.no_sync:
        cmd_sync_board(argparse.Namespace(note=_feed_note(rep).replace(" (requests -/- today)", " (pushed)")), cfg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m fund")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("mark")
    p.add_argument("symbol"); p.add_argument("price", type=float)
    p.add_argument("--bid", type=float); p.add_argument("--ask", type=float); p.add_argument("--ts")
    p = sub.add_parser("preview")
    p.add_argument("symbol"); p.add_argument("side", choices=["buy", "sell"]); p.add_argument("qty", type=float)
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--bid", type=float); p.add_argument("--ask", type=float); p.add_argument("--adv", type=float)
    p.add_argument("--stop", type=float); p.add_argument("--target", type=float); p.add_argument("--ts")
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("word")
    sub.add_parser("status")
    sub.add_parser("sync-board")
    p = sub.add_parser("loop")
    p.add_argument("--once", action="store_true"); p.add_argument("--every", type=float, default=60)
    p.add_argument("--max-ticks", type=int); p.add_argument("--no-sync", action="store_true")
    p = sub.add_parser("ingest"); p.add_argument("file"); p.add_argument("--no-sync", action="store_true")
    a = ap.parse_args(argv)
    cfg = config.load()
    {"init": cmd_init, "mark": cmd_mark, "preview": cmd_preview, "approve": cmd_approve,
     "status": cmd_status, "sync-board": cmd_sync_board,
     "loop": cmd_loop, "ingest": cmd_ingest}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
