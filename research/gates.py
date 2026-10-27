"""Strategy deployment gauntlet: five gates a backtested strategy must clear before it may trade.

This sits one level above fund/risk.py. Risk vets a single order against live limits; the gauntlet
vets a whole strategy against its own backtest, stress runs, risk review and paper record. A
strategy that is not DEPLOYABLE here never reaches the trader seat.

Input is a normalized JSON summary of one backtest (see research/README.md for the schema). Every
check is total: a missing or malformed field fails that check with a reason. Nothing raises.

  Gate 1  honest settings   settings      venue fees on, slippage at or above the floor
  Gate 2  right numbers     sample        enough closed trades
                            quality       Sharpe and profit factor
                            expectancy    p·W − (1−p)·L > 0
                            pain          max drawdown within budget
                            benchmark     beats buy and hold
                            neutral       long/short books keep |beta| small
                            luck          Sharpe clears the best-of-N-by-chance bar
  Gate 3  risk officer      risk_officer  independent review returned KEEP
  Gate 4  stress            costs         still profitable at 2x fees and slippage
                            plateau       nudged parameters keep most of the Sharpe
                            recent        trailing year still positive
  Gate 5  forward           forward       weeks of paper trading that track the backtest
"""
import json
import math
import pathlib
from dataclasses import dataclass, field

DEFAULT_SCORECARD = {
    "min_slippage_bps": 5.0,
    "min_closed_trades": 100,
    "min_sharpe": 1.0,
    "min_profit_factor": 1.3,
    "max_drawdown_pct": 20.0,
    "min_excess_vs_hold_pct": 0.0,
    "max_abs_beta_neutral": 0.1,
    "min_return_2x_costs_pct": 0.0,
    "min_plateau_ratio": 0.5,
    "min_return_last_1y_pct": 0.0,
    "min_paper_days": 21,
    "min_paper_tracking": 0.5,
}

BOOKS = ("directional", "long_short")


@dataclass(frozen=True)
class Check:
    gate: int
    name: str
    ok: bool
    detail: str


@dataclass
class Result:
    status: str                                   # DEPLOYABLE | BLOCKED
    checks: list = field(default_factory=list)

    @property
    def deployable(self):
        return self.status == "DEPLOYABLE"

    def failed(self):
        return [c for c in self.checks if not c.ok]

    def to_dict(self):
        return {"status": self.status,
                "checks": [{"gate": c.gate, "name": c.name, "ok": c.ok, "detail": c.detail} for c in self.checks]}


class _Missing(Exception):
    pass


def scorecard(overrides=None):
    card = dict(DEFAULT_SCORECARD)
    unknown = set(overrides or {}) - set(card)
    if unknown:
        raise ValueError(f"unknown scorecard keys: {sorted(unknown)}")
    card.update(overrides or {})
    return card


def load_scorecard(desk_path):
    desk = json.loads(pathlib.Path(desk_path).read_text(encoding="utf-8"))
    return scorecard(desk.get("research", {}).get("scorecard"))


def luck_threshold(n_variants, years):
    """Expected best annualized Sharpe among N skill-less variants: sqrt(2 ln N) · σ_SR, σ_SR ≈ 1/sqrt(years).

    Bailey & López de Prado (2014). One variant tested means no selection, so no luck bar.
    """
    if n_variants <= 1:
        return 0.0
    return math.sqrt(2 * math.log(n_variants)) / math.sqrt(years)


def _get(r, *path):
    v = r
    for k in path:
        if not isinstance(v, dict) or k not in v:
            raise _Missing(f"missing {'.'.join(path)}")
        v = v[k]
    return v


def _num(r, *path):
    v = _get(r, *path)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _Missing(f"{'.'.join(path)} must be a number, got {v!r}")
    return float(v)


def _settings(r, c):
    fees, slip = _get(r, "settings", "venue_fees"), _num(r, "settings", "slippage_bps")
    ok = fees is True and slip >= c["min_slippage_bps"]
    return ok, f"venue_fees={fees}, slippage {slip:g} bps (floor {c['min_slippage_bps']:g})"


def _sample(r, c):
    n = _num(r, "closed_trades")
    return n >= c["min_closed_trades"], f"{n:g} closed trades (need {c['min_closed_trades']:g})"


def _quality(r, c):
    sr, pf = _num(r, "sharpe"), _num(r, "profit_factor")
    ok = sr > c["min_sharpe"] and pf > c["min_profit_factor"]
    return ok, f"Sharpe {sr:.2f} (> {c['min_sharpe']:g}), PF {pf:.2f} (> {c['min_profit_factor']:g})"


def _expectancy(r, c):
    p, w, l = _num(r, "win_rate"), _num(r, "avg_win"), abs(_num(r, "avg_loss"))
    if not 0 <= p <= 1:
        raise _Missing(f"win_rate must be 0..1, got {p:g}")
    e = p * w - (1 - p) * l
    return e > 0, f"E = {p:.2f}·{w:g} − {1 - p:.2f}·{l:g} = {e:+.2f} per trade"


def _pain(r, c):
    dd = abs(_num(r, "max_drawdown_pct"))
    return dd <= c["max_drawdown_pct"], f"max drawdown {dd:.1f}% (budget {c['max_drawdown_pct']:g}%)"


def _benchmark(r, c):
    x = _num(r, "return_pct") - _num(r, "buy_hold_return_pct")
    return x > c["min_excess_vs_hold_pct"], f"excess vs buy-and-hold {x:+.1f} pts"


def _neutral(r, c):
    book = _get(r, "book")
    if book not in BOOKS:
        return False, f"book must be one of {BOOKS}, got {book!r}"
    if book == "directional":
        return True, "directional book: beta not gated"
    b = _num(r, "beta")
    return abs(b) <= c["max_abs_beta_neutral"], f"beta {b:+.2f} (|beta| ≤ {c['max_abs_beta_neutral']:g})"


def _luck(r, c):
    n, yrs, sr = _num(r, "variants_tested"), _num(r, "years"), _num(r, "sharpe")
    if n < 1 or yrs <= 0:
        raise _Missing("variants_tested must be ≥ 1 and years > 0")
    bar = luck_threshold(n, yrs)
    return sr > bar, f"Sharpe {sr:.2f} vs {bar:.2f} expected from the best of {n:g} variants over {yrs:g}y by chance"


def _risk_officer(r, c):
    v = _get(r, "risk_verdict")
    return v == "KEEP", f"risk officer said {v!r}"


def _costs(r, c):
    x = _num(r, "stress", "return_2x_costs_pct")
    return x > c["min_return_2x_costs_pct"], f"return at 2x costs {x:+.1f}%"


def _plateau(r, c):
    sr = _num(r, "sharpe")
    nb = _get(r, "stress", "neighbor_sharpes")
    if not isinstance(nb, list) or not nb or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in nb):
        raise _Missing("stress.neighbor_sharpes must be a non-empty list of numbers")
    if sr <= 0:
        return False, f"base Sharpe {sr:.2f} is not positive"
    ratio = min(nb) / sr
    return ratio >= c["min_plateau_ratio"], f"worst neighbor keeps {ratio:.0%} of Sharpe (need {c['min_plateau_ratio']:.0%})"


def _recent(r, c):
    x = _num(r, "return_last_1y_pct")
    return x > c["min_return_last_1y_pct"], f"trailing-year return {x:+.1f}%"


def _forward(r, c):
    days, psr, sr = _num(r, "paper", "days"), _num(r, "paper", "sharpe"), _num(r, "sharpe")
    need = c["min_paper_tracking"] * sr
    ok = days >= c["min_paper_days"] and psr >= need
    return ok, f"{days:g} paper days (need {c['min_paper_days']:g}), paper Sharpe {psr:.2f} (need ≥ {need:.2f})"


CHECKS = [
    (1, "settings", _settings),
    (2, "sample", _sample), (2, "quality", _quality), (2, "expectancy", _expectancy), (2, "pain", _pain),
    (2, "benchmark", _benchmark), (2, "neutral", _neutral), (2, "luck", _luck),
    (3, "risk_officer", _risk_officer),
    (4, "costs", _costs), (4, "plateau", _plateau), (4, "recent", _recent),
    (5, "forward", _forward),
]


def check(report, card=None):
    card = scorecard() if card is None else card
    if not isinstance(report, dict):
        return Result("BLOCKED", [Check(0, "report", False, "report must be a JSON object")])
    out = []
    for gate, name, fn in CHECKS:
        try:
            ok, detail = fn(report, card)
        except _Missing as e:
            ok, detail = False, str(e)
        out.append(Check(gate, name, bool(ok), detail))
    status = "DEPLOYABLE" if all(c.ok for c in out) else "BLOCKED"
    return Result(status, out)


def render(result, name="strategy"):
    lines = [f"{name}: {result.status}"]
    for c in result.checks:
        lines.append(f"  [{'PASS' if c.ok else 'FAIL'}] gate {c.gate} {c.name:<12} {c.detail}")
    return "\n".join(lines)
