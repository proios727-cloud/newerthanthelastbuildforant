"""Step 1: live BTC candles and order book depth from Binance's free public market-data API."""
from __future__ import annotations

import time

import requests

INTERVAL_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
               "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000}


class Binance:
    def __init__(self, base: str, timeout: float = 10.0):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.timeout = timeout

    def _get(self, path: str, **params):
        for attempt in range(4):
            try:
                r = self.s.get(f"{self.base}{path}", params=params, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code}")
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def server_time_ms(self) -> int:
        return int(self._get("/api/v3/time")["serverTime"])

    def closed_candles(self, symbol: str, interval: str, limit: int) -> list[dict]:
        """Closed candles only (the still-forming one is dropped)."""
        raw = self._get("/api/v3/klines", symbol=symbol, interval=interval, limit=limit + 1)
        now = self.server_time_ms()
        out = [{"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]),
                "v": float(k[5]), "close_time": k[6], "trades": k[8], "taker_buy_v": float(k[9])}
               for k in raw]
        return [c for c in out if c["close_time"] < now][-limit:]

    def depth(self, symbol: str, limit: int) -> dict:
        d = self._get("/api/v3/depth", symbol=symbol, limit=limit)
        return {"bids": [(float(p), float(q)) for p, q in d["bids"]],
                "asks": [(float(p), float(q)) for p, q in d["asks"]],
                "last_update_id": d["lastUpdateId"], "ts": int(time.time() * 1000)}
