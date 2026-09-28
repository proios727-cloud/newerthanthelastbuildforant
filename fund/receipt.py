"""Session receipts for the 30-day PAPER clock (gate 4).

A receipt is the Fund Reporter's record of one session: the ledger snapshot, what happened
that fund day (from ledger/events.jsonl), and a breach check. A breach is a book state the risk
rules should have made impossible:
  gross_cap     gross exposure above max_gross_pct
  position_cap  one position above max_position_pct of NAV (plus a 1-point drift allowance, since
                marks move after entry)
  halted_entry  an opening fill on a fund day whose P&L sat at or beyond the day-loss halt
A VETO is not a breach — it is the rules working.
"""
from . import clock
from .ledger import parse_ts

DRIFT_PCT = 1.0
KINDS = ("mark", "preview", "veto", "fill", "approve_refused", "shadow_fill", "shadow_exit", "shadow_veto")


def breaches(ledger, cfg, day_events):
    L, nav, out = cfg.limits, ledger.nav(), []
    if nav <= 0:
        return [("nav", f"NAV {nav:,.2f} ≤ 0")]
    gross_pct = 100 * ledger.gross() / nav
    if gross_pct > L.max_gross_pct:
        out.append(("gross_cap", f"gross {gross_pct:.1f}% > {L.max_gross_pct}%"))
    for s in ledger.positions:
        pct = 100 * abs(ledger.market_value(s)) / nav
        if pct > L.max_position_pct + DRIFT_PCT:
            out.append(("position_cap", f"{s} {pct:.1f}% > {L.max_position_pct}% (+{DRIFT_PCT} drift)"))
    if ledger.day_pnl_pct() <= -L.day_loss_halt_pct:
        opening = [e for e in day_events if e["kind"] == "fill" and e.get("reducing") is False]
        if opening:
            out.append(("halted_entry", f"{len(opening)} opening fill(s) on a day at the loss halt"))
    return out


def build(ledger, cfg, events, now, label="session", shadow=None):
    day = clock.fund_day(now)
    todays = [e for e in events if clock.fund_day(parse_ts(e["ts"])) == day]
    counts = {k: sum(1 for e in todays if e["kind"] == k) for k in KINDS}
    found = breaches(ledger, cfg, todays)
    return {
        "fund_day": day,
        "label": label,
        "ts": now.isoformat(),
        "mode": cfg.mode,
        "snapshot": ledger.snapshot(),
        "marks": {s: {"price": m["price"], "ts": m["ts"]} for s, m in sorted(ledger.marks.items())},
        "counts": counts,
        "shadow": shadow,
        "shadow_vetoes": sorted({e["rule"] for e in todays if e["kind"] == "shadow_veto"}),
        "breaches": [{"rule": r, "detail": d} for r, d in found],
        "clean": not found,
    }
