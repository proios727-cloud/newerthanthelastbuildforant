"""Bot settings. Override any field with an env var named BOT_<FIELD> (e.g. BOT_INTERVAL=5m)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
STATE_DIR = Path(os.environ.get("BOT_STATE_DIR", ROOT / "state"))


@dataclass
class Config:
    # Market data (Binance public, no account)
    symbol: str = "BTCUSDT"
    interval: str = "15m"
    binance_base: str = "https://data-api.binance.vision"
    candles_lookback: int = 200
    depth_limit: int = 5000

    # Mode
    mode: str = "paper"  # paper only; live is intentionally not implemented
    allow_shorts: bool = False  # spot BTC: long-only by default

    # Drex
    drex_base: str = "https://console.nace.ai"
    drex_model: str = "drex-max"  # Max accepts the chart image
    drex_timeout_s: float = 30.0

    # Risk layer (step 7)
    regime_threshold: float = 0.60  # min P(regime) to run its playbook
    take_threshold: float = 0.65  # min P(TAKE) to allow a trade
    panic_threshold: float = 0.50  # P(PANIC) above this = hands off
    panic_flatten: bool = True  # close open position when PANIC fires
    risk_per_trade_pct: float = 0.5  # % of equity lost if stop hits
    max_position_pct: float = 20.0  # hard cap on notional, % of equity
    max_open_positions: int = 1
    max_trades_per_day: int = 10
    max_daily_loss_pct: float = 2.0  # halt new trades for the UTC day
    loss_cooldown_candles: int = 2

    # Paper broker
    starting_equity: float = 10_000.0
    fee_bps: float = 10.0  # 0.10% taker/maker
    slippage_bps: float = 2.0
    limit_ttl_candles: int = 2

    # Strategy params
    breakout_lookback: int = 20
    atr_period: int = 14
    stop_atr: float = 1.5
    breakout_target_atr: float = 3.0

    # Nightly review (step 8)
    review_hour_utc: int = 0
    review_window_hours: int = 168
    auto_tune: bool = True
    tune_min_samples: int = 30
    tune_max_step: float = 0.05

    # Notifications (ntfy.sh topic; empty = off)
    ntfy_topic: str = ""
    ntfy_base: str = "https://ntfy.sh"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        tuned = STATE_DIR / "tuned.json"  # thresholds written by review.py
        if tuned.exists():
            for k, v in json.loads(tuned.read_text()).items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        for f in fields(cls):
            raw = os.environ.get(f"BOT_{f.name.upper()}")
            if raw is None:
                continue
            t = type(getattr(cfg, f.name))
            setattr(cfg, f.name, raw.lower() in ("1", "true", "yes") if t is bool else t(raw))
        if cfg.mode != "paper":
            raise SystemExit("Only paper mode is implemented. Live execution is a separate, explicit step.")
        return cfg

    def as_dict(self) -> dict:
        return asdict(self)
