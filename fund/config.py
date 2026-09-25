"""Load the fund block (limits, universe, fees) from desk.json — the single source of truth."""
import json
import pathlib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Limits:
    max_position_pct: float
    max_gross_pct: float
    max_group_pct: float
    day_loss_halt_pct: float
    drawdown_halt_pct: float
    max_spread_bps: dict
    max_adv_pct: float
    event_blackout_min: float
    max_quote_age_sec: float
    preview_ttl_sec: float


@dataclass(frozen=True)
class FundConfig:
    mode: str
    approval_word: str
    starting_nav: float
    fees: dict
    limits: Limits
    universe: dict = field(default_factory=dict)

    def asset(self, symbol):
        return self.universe[symbol]["asset"]

    def group(self, symbol):
        return self.universe[symbol]["group"]


def from_dict(desk):
    f = desk["fund"]
    return FundConfig(
        mode=desk["mode"],
        approval_word=desk["approval_word"],
        starting_nav=float(f["starting_nav"]),
        fees=f["fees"],
        limits=Limits(**f["limits"]),
        universe=f["universe"],
    )


def load(path=ROOT / "desk.json"):
    return from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
