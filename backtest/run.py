"""Walk-forward replay of the shadow book over ~14 months of daily closes.

It drives the production code (fund.shadow.Shadow.step → fund.risk.check → fund.ledger.Ledger) one day
at a time, so the backtest and the live paper run share every rule. Nothing here is fitted: the signal
and exit parameters are the fixed ones in fund/shadow.py.

Data: backtest/data/<SYM>.txt holds the older closes (TradingView daily bars); ledger/bars.json holds
the most recent 60 (equities) / 59 (crypto). Equities: 300 NYSE sessions 2025-07-21 → 2026-09-28.
Crypto: 299 UTC days 2025-12-03 → 2026-09-27.

  python backtest/run.py            # writes backtest/results.json and prints a summary
"""
import json
import math
import pathlib
import sys
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fund import config, shadow  # noqa: E402

DATA = ROOT / "backtest" / "data"
FILES = {"SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "NVDA": "NVDA", "AMD": "AMD", "AAPL": "AAPL",
         "MSFT": "MSFT", "TSLA": "TSLA", "BTC/USD": "BTCUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD"}
NYSE_HOLIDAYS = {"2025-09-01", "2025-11-27", "2025-12-25", "2026-01-01", "2026-01-19", "2026-02-16",
                 "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07"}


def nyse_days(start, n):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5 and d.isoformat() not in NYSE_HOLIDAYS:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def load_series():
    recent = json.loads((ROOT / "ledger" / "bars.json").read_text())
    series = {}
    for sym, f in FILES.items():
        words = (DATA / f"{f}.txt").read_text().split()
        head = [float(x) for x in (words[1:] if sym == "SPY" else words)]
        tail = recent[sym]["closes"]
        if sym == "SPY":  # the SPY file holds all 300 closes: its tail must equal bars.json
            assert head[-60:] == tail, "SPY history does not match ledger/bars.json"
            closes = head
        else:
            assert len(head) == 240, (sym, len(head))
            jump = abs(tail[0] / head[-1] - 1)
            assert jump < 0.2, f"{sym}: suspicious join ({head[-1]} → {tail[0]})"
            closes = head + tail
        if "/" in sym:
            end = date.fromisoformat(recent[sym]["last"])
            days = [(end - timedelta(days=len(closes) - 1 - i)).isoformat() for i in range(len(closes))]
            assert days[0] == "2025-12-03", (sym, days[0])
        else:
            days = nyse_days("2025-07-21", len(closes))
            assert days[-1] == recent[sym]["last"] == "2026-09-28", (sym, days[-1])
        series[sym] = list(zip(days, closes))
    return series


def run(series, cfg, slip_bps=0.0, only=None, start=None, end=None):
    """Replay the shadow book. `only` restricts to one signal type; start/end bound the entry window."""
    orig_fee, orig_signals = shadow.fee, shadow.signals

    def fee(c, s, q, p):
        base = c.fees["crypto_bps"] if c.asset(s) == "crypto" else 0.0
        return round(q * p * (base + slip_bps) / 1e4, 2)

    def signals(closes):
        return [x for x in orig_signals(closes) if x[0] == only]

    shadow.fee = fee
    if only:
        shadow.signals = signals
    try:
        sh = shadow.Shadow.new(cfg)
        days = sorted({d for s in series.values() for d, _ in s})
        idx = {s: 0 for s in series}
        nav, events = [], []
        for d in days:
            if end and d > end:
                break
            bars = {}
            for s, rows in series.items():
                while idx[s] < len(rows) and rows[idx[s]][0] <= d:
                    idx[s] += 1
                if idx[s]:
                    bars[s] = {"last": rows[idx[s] - 1][0], "closes": [c for _, c in rows[:idx[s]]][-120:]}
            if start and d < start:  # warm-up: mark only, no trades
                for s, b in bars.items():
                    sh.done[s] = b["last"]
                continue
            events += sh.step(bars, cfg)
            nav.append((d, sh.ledger.nav(), sh.ledger.gross()))
        return sh, nav, events
    finally:
        shadow.fee, shadow.signals = orig_fee, orig_signals


def stats(nav, events, sh):
    vals = [v for _, v, _ in nav]
    rets = [b / a - 1 for a, b in zip(vals, vals[1:])]
    peak, mdd = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    days = (date.fromisoformat(nav[-1][0]) - date.fromisoformat(nav[0][0])).days or 1
    total = vals[-1] / vals[0] - 1
    sd = statistics_sd(rets)
    exits = [e for e in events if e["kind"] == "shadow_exit"]
    wins = [e["realized"] for e in exits if e["realized"] > 0]
    losses = [e["realized"] for e in exits if e["realized"] <= 0]
    by_why, by_sig, vetoes = {}, {}, {}
    entry_sig = {}
    for e in events:
        if e["kind"] == "shadow_fill":
            entry_sig[e["symbol"]] = e["signal"]
        elif e["kind"] == "shadow_exit":
            by_why[e["why"]] = by_why.get(e["why"], 0) + 1
            sig = entry_sig.get(e["symbol"], "?")
            t = by_sig.setdefault(sig, {"trades": 0, "pnl": 0.0, "wins": 0})
            t["trades"] += 1
            t["pnl"] = round(t["pnl"] + e["realized"], 2)
            t["wins"] += e["realized"] > 0
        elif e["kind"] == "shadow_veto":
            vetoes[e["rule"]] = vetoes.get(e["rule"], 0) + 1
    return {
        "start": nav[0][0], "end": nav[-1][0], "final_nav": round(vals[-1], 2),
        "total_return_pct": round(100 * total, 2),
        "annualized_pct": round(100 * ((1 + total) ** (365 / days) - 1), 2),
        "max_drawdown_pct": round(100 * mdd, 2),
        "sharpe": round(sum(rets) / len(rets) / sd * math.sqrt(365), 2) if sd else None,
        "avg_gross_pct": round(100 * sum(g / v for _, v, g in nav) / len(nav), 1),
        "trades": len(exits), "open_at_end": len(sh.meta),
        "win_rate": round(len(wins) / len(exits), 3) if exits else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) else None,
        "exits_by_reason": by_why, "by_signal": by_sig, "vetoes_by_rule": vetoes,
    }


def statistics_sd(x):
    if len(x) < 2:
        return 0.0
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def buy_hold(series, syms, start, end):
    """Equal-weight buy-and-hold of `syms` from the first close on/after start to the last on/before end."""
    rs = []
    for s in syms:
        rows = [(d, c) for d, c in series[s] if start <= d <= end]
        rs.append(rows[-1][1] / rows[0][1] - 1)
    return round(100 * sum(rs) / len(rs), 2)


def main():
    cfg = config.load()
    series = load_series()
    eq = [s for s in series if "/" not in s]
    base_sh, base_nav, base_ev = run(series, cfg)
    base = stats(base_nav, base_ev, base_sh)
    start, end = base["start"], base["end"]
    mid = base_nav[len(base_nav) // 2][0]
    out = {
        "window": {"start": start, "end": end, "equity_sessions": 300, "crypto_days": 299,
                   "note": "Signals need 51 closes, so equities can trade from 2025-09-30 and crypto from 2026-01-22."},
        "base": base,
        "costs": {},
        "signals_alone": {},
        "halves": {},
        "benchmarks": {
            "SPY_buy_hold_pct": buy_hold(series, ["SPY"], "2025-09-30", end),
            "equal_weight_8_equities_pct": buy_hold(series, eq, "2025-09-30", end),
            "equal_weight_3_crypto_pct": buy_hold(series, ["BTC/USD", "ETH/USD", "SOL/USD"], "2026-01-22", end),
        },
    }
    for bps in (5, 10, 20):
        sh, nav, ev = run(series, cfg, slip_bps=bps)
        out["costs"][f"{bps}bps_per_side"] = stats(nav, ev, sh)
    for sig in ("momentum", "breakout", "mean_reversion"):
        sh, nav, ev = run(series, cfg, only=sig)
        out["signals_alone"][sig] = stats(nav, ev, sh)
    for name, (s, e) in {"first_half": (None, mid), "second_half": (mid, None)}.items():
        sh, nav, ev = run(series, cfg, start=s, end=e)
        out["halves"][name] = stats(nav, ev, sh)
    out["equity_curve"] = [(d, round(v, 2)) for d, v, _ in base_nav]
    (ROOT / "backtest" / "results.json").write_text(json.dumps(out, indent=1) + "\n")

    b = out["base"]
    print(f"window {start} → {end}")
    print(f"base      ret {b['total_return_pct']:+.2f}%  ann {b['annualized_pct']:+.2f}%  maxDD {b['max_drawdown_pct']:.2f}%  "
          f"sharpe {b['sharpe']}  trades {b['trades']}  win {b['win_rate']}  PF {b['profit_factor']}  gross {b['avg_gross_pct']}%")
    for k, v in out["costs"].items():
        print(f"{k:<16} ret {v['total_return_pct']:+.2f}%  maxDD {v['max_drawdown_pct']:.2f}%  sharpe {v['sharpe']}")
    for k, v in out["signals_alone"].items():
        print(f"only {k:<15} ret {v['total_return_pct']:+.2f}%  maxDD {v['max_drawdown_pct']:.2f}%  trades {v['trades']}  "
              f"win {v['win_rate']}  PF {v['profit_factor']}")
    for k, v in out["halves"].items():
        print(f"{k:<16} {v['start']}→{v['end']}  ret {v['total_return_pct']:+.2f}%  maxDD {v['max_drawdown_pct']:.2f}%  sharpe {v['sharpe']}")
    print("benchmarks", out["benchmarks"])
    print("exits", b["exits_by_reason"], "vetoes", b["vetoes_by_rule"])
    print("by signal", b["by_signal"])


if __name__ == "__main__":
    main()
