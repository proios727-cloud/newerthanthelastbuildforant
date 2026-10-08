"""Load the fund block (limits, universe, fees) from desk.json — the single source of truth.

Also loads .env (if present) into os.environ WITHOUT overriding existing values.
.env values are never logged or printed.
"""
import json
import os
import pathlib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent

TRUTHY = {"1", "true", "yes", "on"}


def load_env(path=ROOT / ".env"):
    """Stdlib .env loader: fills empty/missing env values only; existing env wins."""
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if not key or key.startswith("#"):
            continue
        if key not in os.environ or not os.environ[key]:
            os.environ[key] = val


def env(name, default=""):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in TRUTHY


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
    load_env()
    return from_dict(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))
