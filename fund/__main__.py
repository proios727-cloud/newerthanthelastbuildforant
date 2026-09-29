"""Paper-fund CLI. State lives in ledger/ (state.json, previews.json, events.jsonl).

  python -m fund init [--force]
  python -m fund mark SYMBOL PRICE [--bid B --ask A] [--ts ISO]
  python -m fund preview SYMBOL buy|sell QTY --price P [--bid B --ask A] [--adv N] [--stop S --target T] [--ts ISO]
  python -m fund approve PREVIEW_ID WORD
  python -m fund status
  python -m fund bars-append FILE    # merge connector bars {SYMBOL: [[t_unix, close], ...]} into ledger/bars.json
  python -m fund scan                # ranked Quant Scanner signals from ledger/bars.json
  python -m fund quotes FILE         # store Robinhood quotes {SYMBOL: {bid, ask, ts}} → ledger/quotes.json
  python -m fund shadow              # run every shadow variant on new bars (ledger/shadow/<variant>.json)
  python -m fund putbook plan|apply FILE   # paper short-put book on live option quotes (ledger/putbook.json)
  python -m fund receipt [--label L]  # write ledger/receipts/<fund-day>-<label>.json with a breach check
  python -m fund sync-board          # write ledger numbers into desk.json tiles/funnel, rebuild board.html
"""
import argparse
from datetime import date
import json
import pathlib
import subprocess
import sys

from . import clock, config, preview, putbook, receipt, risk, shadow
from .config import ROOT
from .ledger import Ledger, parse_ts

DIR = ROOT / "ledger"
STATE, PREVIEWS, EVENTS = DIR / "state.json", DIR / "previews.json", DIR / "events.jsonl"
RECEIPTS = DIR / "receipts"
BARS, SHADOW_DIR, QUOTES = DIR / "bars.json", DIR / "shadow", DIR / "quotes.json"
PUTBOOK = DIR / "putbook.json"


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
    log("fill", reducing=p["reducing"], **rec)
    print(json.dumps(rec, indent=2))


def cmd_status(a, cfg):
    L = load_ledger()
    snap = L.snapshot()
    snap["mode"] = cfg.mode
    snap["awaiting_approval"] = [k for k, p in load_previews().items() if p["status"] == "awaiting_approval"]
    print(json.dumps(snap, indent=2))


def load_bars():
    if not BARS.exists():
        sys.exit(f"no {BARS.relative_to(ROOT)} — seed it with 60+ daily closes per symbol first")
    return json.loads(BARS.read_text(encoding="utf-8"))


def cmd_bars_append(a, cfg):
    bars = load_bars()
    raw = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
    added = shadow.append_bars(bars, cfg, raw, clock.now())
    BARS.write_text(json.dumps(bars, indent=1) + "\n", encoding="utf-8")
    log("bars", added=added)
    print(json.dumps({"added": added, "last": {s: b["last"] for s, b in bars.items()}}, indent=2))


def cmd_scan(a, cfg):
    print(json.dumps(shadow.scan(load_bars()), indent=2))


def load_quotes():
    return json.loads(QUOTES.read_text(encoding="utf-8")) if QUOTES.exists() else {}


def cmd_quotes(a, cfg):
    raw = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
    q, skipped = load_quotes(), {}
    for sym, r in raw.items():
        if sym not in cfg.universe:
            sys.exit(f"{sym} is not in the universe")
        bid, ask = float(r["bid"] or 0), float(r["ask"] or 0)
        if not 0 < bid <= ask:  # empty or crossed book: keep the previous quote
            skipped[sym] = f"bid {bid} / ask {ask}"
            continue
        q[sym] = {"bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 6),
                  "spread_bps": shadow.spread_bps(bid, ask), "ts": r.get("ts") or clock.now().isoformat()}
    QUOTES.write_text(json.dumps(q, indent=1) + "\n", encoding="utf-8")
    log("quotes", spreads={s: v["spread_bps"] for s, v in q.items()}, skipped=skipped)
    print(json.dumps({"spread_bps": {s: v["spread_bps"] for s, v in q.items()}, "skipped": skipped}, indent=2))


def shadow_books(cfg):
    legacy = DIR / "shadow.json"  # single-book layout from before the variants
    if legacy.exists() and not (SHADOW_DIR / "all.json").exists():
        SHADOW_DIR.mkdir(parents=True, exist_ok=True)
        legacy.rename(SHADOW_DIR / "all.json")
    return {name: shadow.load(SHADOW_DIR / f"{name}.json", cfg, only) for name, only in shadow.VARIANTS.items()}


def cmd_shadow(a, cfg):
    bars, quotes, out = load_bars(), load_quotes(), {}
    for name, sh in shadow_books(cfg).items():
        evs = sh.step(bars, cfg, quotes=quotes)
        shadow.save(sh, SHADOW_DIR / f"{name}.json")
        for e in evs:
            e = dict(e)
            log(e.pop("kind"), variant=name, bar_ts=e.pop("ts"), **e)
        out[name] = {"events": len(evs), "summary": sh.summary()}
    print(json.dumps(out, indent=2))


def cmd_putbook(a, cfg):
    st, bars = putbook.load(PUTBOOK), load_bars()
    today = date.fromisoformat(bars["SPY"]["last"])  # the equity session the bars describe
    if a.action == "plan":
        print(json.dumps(putbook.plan(st, bars, today), indent=2))
        return
    if not a.file:
        sys.exit("putbook apply needs FILE")
    quotes = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
    out = putbook.apply(st, bars, quotes, today)
    putbook.save(st, PUTBOOK)
    for e in out.get("events", []):
        log(e.get("kind", "put_event"), **{k: v for k, v in e.items() if k != "kind"})
    print(json.dumps({**out, "summary": putbook.summary(st, quotes.get("marks"))}, indent=2))


def cmd_receipt(a, cfg):
    L = load_ledger()
    events = [json.loads(x) for x in EVENTS.read_text(encoding="utf-8").splitlines() if x] if EVENTS.exists() else []
    sh = {n: b.summary() for n, b in shadow_books(cfg).items()} if SHADOW_DIR.exists() or (DIR / "shadow.json").exists() else None
    if PUTBOOK.exists():
        sh = {**(sh or {}), "putbook": putbook.summary(putbook.load(PUTBOOK))}
    r = receipt.build(L, cfg, events, clock.now(), a.label, shadow=sh)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    out = RECEIPTS / f"{r['fund_day']}-{a.label}.json"
    out.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    log("receipt", path=str(out.relative_to(ROOT)), clean=r["clean"], breaches=r["breaches"])
    print(json.dumps(r, indent=2))
    if not r["clean"]:
        sys.exit(f"BREACH: {r['breaches']}")


def fmt_money(x):
    return f"${x:,.0f}"


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
    path.write_text(json.dumps(desk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts/build_board.py"), str(path), "--out", str(ROOT / "board.html")], check=True)


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
    p = sub.add_parser("bars-append"); p.add_argument("file")
    sub.add_parser("scan")
    sub.add_parser("shadow")
    p = sub.add_parser("quotes"); p.add_argument("file")
    p = sub.add_parser("putbook"); p.add_argument("action", choices=["plan", "apply"]); p.add_argument("file", nargs="?")
    p = sub.add_parser("receipt"); p.add_argument("--label", default="session")
    sub.add_parser("sync-board")
    a = ap.parse_args(argv)
    cfg = config.load()
    {"init": cmd_init, "mark": cmd_mark, "preview": cmd_preview, "approve": cmd_approve,
     "status": cmd_status, "receipt": cmd_receipt, "bars-append": cmd_bars_append, "scan": cmd_scan, "shadow": cmd_shadow, "quotes": cmd_quotes, "putbook": cmd_putbook, "sync-board": cmd_sync_board}[a.cmd](a, cfg)


if __name__ == "__main__":
    main()
