"""Build head.html: the Desk Head page (chat with the head agent + delegate to a cloud agent session).

It embeds a snapshot of the ledger — every book, the JEV test, recent activity — computed with the desk's
own code, into assets/head-template.html. Rebuild and republish after each daily receipt:

    python scripts/build_head.py            # writes head.html
"""
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fund import __main__ as cli, calibration, config, jevcheck, killswitch, putbook, spreadbook, trendbook  # noqa: E402

CONFIG = {
    "repo_url": "https://github.com/proios727-cloud/newerthanthelastbuildforant",
    "branch": "claude/adoring-allen-240cm9",
    "environment_id": "env_01KrsAmiYWRZqyR29iNfoYrE",
    "guard": [
        "Paper only. Never call any preview, review, place, cancel or exercise tool on a brokerage connector.",
        "Never run `python3 -m fund approve` or type EXECUTE; approval is human-only.",
        "Don't hand-edit ledger/ files, desk.json limits, or jevcheck's registered bar.",
        "Never run `python3 -m fund kill disarm`; only the human disarms the kill switch.",
        "Work on a new branch off claude/adoring-allen-240cm9 and open a draft pull request into it; never push to that branch directly.",
        "Run `python3 -m unittest` before pushing and report what changed and what the tests showed.",
    ],
}

ACTIVITY_KINDS = {"put_entry", "put_exit", "put_skip", "put_ghost_entry", "put_ghost_exit",
                  "spread_entry", "spread_exit", "spread_skip", "spread_ghost_entry", "spread_ghost_exit"}


def describe(e):
    k, s = e["kind"], e.get("symbol", "")
    if k == "put_entry":
        return f"Put book sold {s} {e['strike']}P {e['expiration']} for ${e['credit']:,.2f}"
    if k == "spread_entry":
        return f"Spread book sold {s} {e['short']}/{e['long']}P for ${e['credit']:,.2f}, max loss ${e['max_loss']:,.2f}"
    if k in ("put_exit", "spread_exit", "put_ghost_exit", "spread_ghost_exit"):
        who = "Vetoed ghost" if "ghost" in k else ("Put book" if k.startswith("put") else "Spread book")
        return f"{who} closed {s} ({e['why']}): P&L ${e['pnl']:,.2f}"
    if k.endswith("ghost_entry"):
        return f"JEV vetoed {s}; tracking it as a ghost (p={e.get('jev_p')})"
    if k.endswith("_skip"):
        return f"{'Put' if k.startswith('put') else 'Spread'} book skipped {s}: {e['reason']}"
    return k


def snapshot():
    cfg = config.load()
    L = cli.load_ledger()
    receipts = sorted(cli.RECEIPTS.glob("*.json"))
    rec = json.loads(receipts[-1].read_text(encoding="utf-8")) if receipts else {}
    st, sp = putbook.load(cli.PUTBOOK), spreadbook.load(cli.SPREADBOOK)
    marks = json.loads(cli.QUOTES.read_text(encoding="utf-8")) if cli.QUOTES.exists() else {}
    real = {**L.snapshot(), "awaiting_approval": [k for k, p in cli.load_previews().items()
                                                  if p.get("status") == "awaiting_approval"]}
    shadow = {}
    for name, book in cli.shadow_books(cfg).items():
        v = book.summary()
        shadow[name] = {**v, "open": len(v["open"])}
    logs = [{**x, "book": "put"} for x in st["log"]] + [{**x, "book": "spread"} for x in sp["log"]]
    activity = [{"date": x.get("date"), "text": describe(x)} for x in logs if x.get("kind") in ACTIVITY_KINDS][-30:]
    import judge
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fund_day": rec.get("fund_day"), "clean": rec.get("clean"), "breaches": rec.get("breaches", []),
        "mode": "PAPER",
        "jev_mode": "live" if getattr(judge.from_env(), "live", False) else "stub (no TypeSafe key; never vetoes)",
        "real": real, "shadow": shadow,
        "putbook": putbook.summary(st), "spreadbook": spreadbook.summary(sp),
        "trendbook": trendbook.summary(trendbook.load(cli.TRENDBOOK)),
        "jevcheck": jevcheck.evaluate(st, sp),
        "jev_calibration": calibration.report(st, sp),
        "kill_switch": {k: v for k, v in killswitch.load(cli.KILL).items() if k != "history"},
        "open_detail": {"putbook": st["positions"], "spreadbook": sp["positions"],
                        "ghosts": {**st.get("ghosts", {}), **sp.get("ghosts", {})}},
        "activity": activity,
        "rules": {
            "real_book": "5% per position, 150% gross, halts at -3% day or -10% drawdown; orders need EXECUTE within 5 min",
            "put_book": "sell ~30-delta put ~30 DTE after a bullish signal; exit 50% credit, 3x stop, 15 sessions, 7 DTE, day before earnings",
            "spread_book": "$1-2 wide put credit spread, 16-35 delta short, >=20% credit/width, max loss <=20% of $500 NAV, one open; exit 50% / 2x / 15 sessions / 7 DTE / earnings",
            "jev": "veto-only on headlines; vetoed sales tracked as ghosts; keep/drop bar registered 2026-09-29",
        },
        "research": {
            "baselines": "T-bills ~4.24%, HYSA 4.2-4.5%, card APR ~22% (pay first), SPY ~11%/yr with dividends 2005-2026",
            "evidence": "Cboe PUT ~7.6%/yr, BXM ~6.4%/yr, CNDR (spread proxy) ~1.6%/yr 2005-2026",
            "go_no_go": "spreads: >=8 closed, >+2% per $ risked after slippage, win rate >=5pt over delta-implied; "
                        "Kalshi: >=300 windows, >=60% both-fill; sportsbook CLV: >=200 picks, mean >=+2%",
            "plan": "pay debt >8% first; $300-350 fractional SPY/VTI; $150-200 SPY 1-2 wide spreads only after a passing paper run",
        },
    }


def build(out=ROOT / "head.html"):
    html = (ROOT / "assets" / "head-template.html").read_text(encoding="utf-8")
    snap = json.dumps(snapshot(), separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*SNAPSHOT*/null", snap).replace("/*CONFIG*/null", json.dumps(CONFIG).replace("</", "<\\/"))
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build())
