"""Public-data, paper-only crypto monitor. No private API or order transport."""
from __future__ import annotations
import argparse
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN
from email.utils import parsedate_to_datetime
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "quant"))
from monitor import PaperAccount

PAIRS = {"BTC/USD": "XBTUSD", "SOL/USD": "SOLUSD"}
D = lambda x: Decimal(str(x))


@dataclass(frozen=True)
class Settings:
    signal_minutes: int = 60
    research_only: bool = False
    fee_rate: float = 0.008  # Low-tier taker research estimate; confirm actual account tier.
    slippage_rate: float = 0.0005
    max_cost: float = 0.005  # Maximum ESTIMATED round-trip spread+fees+slippage.
    max_exposure: float = 0.10
    risk_fraction: float = 0.005
    stop_fraction: float = 0.04
    max_hours: float = 72
    quote_max_age: float = 10
    source_max_age: float = 30

    def validate(self):
        if self.signal_minutes not in (60,240) or not isinstance(self.research_only,bool):
            raise ValueError("signal_minutes must be 60 or 240; research_only must be boolean")
        values = asdict(self)
        if any(not math.isfinite(v) or v < 0 for v in values.values()):
            raise ValueError("settings must be finite and nonnegative")
        if not 0 < self.stop_fraction < 1 or not 0 < self.max_exposure <= .10:
            raise ValueError("stop must be (0,1); shared exposure must be (0,0.10]")
        permitted_cost=.02 if self.research_only else .005
        if not 0 < self.risk_fraction <= .005 or not 0 < self.max_cost <= permitted_cost:
            raise ValueError("risk cap0.005; cost cap0.005 unless explicit research_only permits0.02")
        if self.max_hours <= 0 or self.quote_max_age <= 0 or self.source_max_age <= 0:
            raise ValueError("time limits must be positive")


def fresh(timestamp, now, age):
    stamp = float(timestamp)
    if not math.isfinite(stamp) or not 0 <= now - stamp <= age:
        raise ValueError("stale or future source timestamp")


def request_public(endpoint, params):
    # Fixed read-only endpoint allowlist: impossible to pass an order endpoint.
    if endpoint not in ("OHLC", "Ticker", "AssetPairs"):
        raise ValueError("public endpoint not permitted")
    started = time.time()
    url = "https://api.kraken.com/0/public/" + endpoint + "?" + urlencode(params)
    with urlopen(Request(url, headers={"User-Agent": "paper-crypto-research/1.0"}), timeout=8) as reply:
        server_date = reply.headers.get("Date")
        result = json.loads(reply.read(2_000_000))
    received = time.time()
    if received - started > 8 or not server_date:
        raise ValueError("missing HTTP freshness metadata or slow response")
    fresh(parsedate_to_datetime(server_date).timestamp(), received, 15)
    if result.get("error"):
        raise ValueError("public feed returned API errors")
    return result["result"], received


def fetch(pair, signal_minutes=60):
    if signal_minutes not in (60,240):
        raise ValueError("unsupported signal interval")
    public_pair = PAIRS[pair]
    hourly, hourly_at = request_public("OHLC", {"pair": public_pair, "interval": signal_minutes})
    daily, daily_at = request_public("OHLC", {"pair": public_pair, "interval": 1440})
    rules, _ = request_public("AssetPairs", {"pair": public_pair})
    ticker, quote_at = request_public("Ticker", {"pair": public_pair})
    def only(result):
        keys = [key for key in result if key != "last"]
        if len(keys) != 1:
            raise ValueError("ambiguous pair response")
        return result[keys[0]]
    tick = only(ticker)
    return {"source": "KRAKEN_PUBLIC", "received_at": quote_at, "signal_minutes": signal_minutes,
            "hourly_at": hourly_at, "daily_at": daily_at,
            "hourly": only(hourly), "daily": only(daily),
            "pair_rules": {key: only(rules).get(key) for key in ("ordermin", "costmin", "lot_decimals")},
            "quote": {"timestamp": quote_at, "freshness_kind": "HTTP_RECEIPT_ONLY", "bid": tick["b"][0], "ask": tick["a"][0]}}


def closed_candles(rows, interval, now):
    result = []
    previous = None
    for row in rows:
        stamp, opening, high, low, closing = map(float, row[:5])
        if any(not math.isfinite(v) for v in (stamp, opening, high, low, closing)):
            raise ValueError("nonfinite candle")
        if stamp < 0 or stamp % interval or min(opening, high, low, closing) <= 0:
            raise ValueError("invalid candle timestamp or price")
        if low > min(opening, closing) or high < max(opening, closing) or low > high:
            raise ValueError("inconsistent OHLC")
        if previous is not None and stamp != previous + interval:
            raise ValueError("duplicate, unordered or missing candle")
        previous = stamp
        if stamp + interval <= now:
            result.append((stamp, closing))
    return result


def ema(values, period):
    value = sum(values[:period]) / period
    output = [None] * (period - 1) + [value]
    alpha = 2 / (period + 1)
    for item in values[period:]:
        value += alpha * (item - value)
        output.append(value)
    return output


def signal(observation, now, settings):
    if observation.get("signal_minutes",60)!=settings.signal_minutes:
        raise ValueError("source candle interval differs from configured signal interval")
    interval=settings.signal_minutes*60
    fresh(observation["received_at"], now, settings.source_max_age)
    fresh(observation["hourly_at"], now, settings.source_max_age)
    fresh(observation["daily_at"], now, settings.source_max_age)
    hours = closed_candles(observation["hourly"], interval, now)
    days = closed_candles(observation["daily"], 86400, now)
    if len(hours) < 250 or len(days) < 250:
        raise ValueError("insufficient 250-candle warmup")
    if not 0 <= now - (hours[-1][0] + interval) < interval:
        raise ValueError("missing latest closed hourly candle")
    # Daily regime must have been available at the SIGNAL close, not polling time.
    close_time = hours[-1][0] + interval
    days = [row for row in days if row[0] + 86400 <= close_time]
    if len(days) < 250 or not 0 <= close_time - (days[-1][0] + 86400) < 86400:
        raise ValueError("missing daily regime at signal time")
    fast, slow = ema([v for _, v in hours], 20), ema([v for _, v in hours], 50)
    daily = ema([v for _, v in days], 50)
    regime = days[-1][1] > daily[-1] and daily[-1] > daily[-2]
    return {"candle": int(hours[-1][0]), "entry": regime and fast[-1] > slow[-1] and fast[-2] <= slow[-2],
            "exit": fast[-1] < slow[-1], "regime": regime}


def quote(observation, now, settings):
    fresh(observation["received_at"], now, settings.source_max_age)
    item = observation["quote"]
    fresh(item["timestamp"], now, settings.quote_max_age)
    bid, ask = D(item["bid"]), D(item["ask"])
    if not bid.is_finite() or not ask.is_finite() or not 0 < bid <= ask:
        raise ValueError("invalid bid/ask")
    return bid * (1 - D(settings.slippage_rate)), ask * (1 + D(settings.slippage_rate))


class Bot:
    def __init__(self, db, bankroll, settings=Settings(), halt=None):
        settings.validate()
        self.settings, self.halt = settings, halt
        self.account = PaperAccount(db, desk="crypto", bankroll=bankroll)
        self.db = self.account.db
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runtime_decisions(pair TEXT, candle INTEGER, outcome TEXT,
            PRIMARY KEY(pair,candle));
          CREATE TABLE IF NOT EXISTS runtime_positions(id INTEGER PRIMARY KEY, opened REAL, stop TEXT);
          CREATE TABLE IF NOT EXISTS runtime_logs(id INTEGER PRIMARY KEY, timestamp REAL, kind TEXT, payload TEXT);
        """)

    def log(self, now, kind, payload):
        with self.db:
            self.db.execute("INSERT INTO runtime_logs VALUES(NULL,?,?,?)", (now, kind, json.dumps(payload, allow_nan=False)))

    def tick(self, observations, now):
        marks, outcomes = {}, []
        quotes, signals = {}, {}
        for pair in PAIRS:
            item = observations.get(pair)
            # Whitelist public observation fields so fixture secrets cannot enter logs.
            if item:
                raw = {key: item.get(key) for key in ("source", "received_at", "signal_minutes", "hourly_at", "daily_at", "hourly", "daily")}
                raw["quote"] = {key: item.get("quote", {}).get(key) for key in ("timestamp", "freshness_kind", "bid", "ask")}
                raw["pair_rules"] = {key: item.get("pair_rules",{}).get(key) for key in ("ordermin","costmin","lot_decimals")}
                self.log(now, "observation", {"pair": pair, "public": raw})
            try:
                if not item or item.get("source") not in ("KRAKEN_PUBLIC", "SYNTHETIC_FIXTURE"):
                    raise ValueError("missing/unrecognized public source")
                quotes[pair] = quote(item, now, self.settings)
                signals[pair] = signal(item, now, self.settings)
            except (ValueError, KeyError, TypeError, ArithmeticError) as error:
                outcomes.append({"pair": pair, "action": "BLOCK", "reason": str(error) if isinstance(error, ValueError) else "invalid public observation schema"})
        positions = self.db.execute("SELECT id,market,remaining,unit_cost FROM positions WHERE CAST(remaining AS REAL)>0").fetchall()
        halted = bool(self.halt and self.halt.exists())
        for ident, pair, units, cost in positions:
            if pair not in quotes:
                continue
            bid, _ = quotes[pair]
            q = D(units)
            info = self.db.execute("SELECT opened,stop FROM runtime_positions WHERE id=?", (ident,)).fetchone()
            reason = None
            if not info:
                reason = "missing_position_metadata"
            elif bid <= D(info[1]):
                reason = "stop"
            elif now - info[0] >= self.settings.max_hours * 3600:
                reason = "time_exit"
            elif signals.get(pair, {}).get("exit"):
                reason = "trend_exit"
            # HALT blocks all simulated fills; available fresh marks still reported.
            if reason and not halted:
                fee = q * bid * D(self.settings.fee_rate)
                pnl = self.account.exit(position_id=ident, quantity=q, bid=bid, exit_fee=fee)
                outcomes.append({"pair": pair, "action": "PAPER_EXIT", "reason": reason, "realized_pnl": str(pnl)})
            else:
                marks[ident] = {"bid": str(bid), "exit_fee": str(q*bid*D(self.settings.fee_rate)), "timestamp": observations[pair]["quote"]["timestamp"]}
        snapshot = self.account.snapshot(marks=marks, now=now, max_mark_age=self.settings.quote_max_age)
        for pair, candidate in signals.items():
            # Claim before fill: at-most-once entries even after a crash/restart.
            # A crash after claim can skip a trade, never retry one blindly.
            with self.db:
                cursor = self.db.execute("INSERT OR IGNORE INTO runtime_decisions VALUES(?,?,?)", (pair, candidate["candle"], "claimed"))
            if cursor.rowcount == 0:
                outcomes.append({"pair": pair, "action": "DUPLICATE_SKIP"})
                continue
            reason = "no_cross"
            if halted:
                reason = "halt_file"
            elif candidate["entry"]:
                bid, ask = quotes[pair]
                total_cost = (ask-bid)/ask + D(self.settings.fee_rate)*2
                if total_cost > D(self.settings.max_cost):
                    reason = "estimated_roundtrip_cost_above_cap"
                elif snapshot["equity"] is None:
                    reason = "unavailable_portfolio_mark"
                elif snapshot["open_positions"]:
                    reason = "shared_position_limit"
                else:
                    equity = D(snapshot["equity"])
                    fee_rate=D(self.settings.fee_rate)
                    risk_distance=D(self.settings.stop_fraction)+2*fee_rate+2*D(self.settings.slippage_rate)
                    notional = min(equity*D(self.settings.max_exposure)/(1+fee_rate), equity*D(self.settings.risk_fraction)/risk_distance, D(snapshot["cash"])/(1+fee_rate))
                    if notional <= 0:
                        reason = "no_paper_cash"
                    else:
                        rules=observations[pair].get("pair_rules",{})
                        try:
                            minimum_units=D(rules["ordermin"]);minimum_cost=D(rules["costmin"]);precision=int(rules["lot_decimals"])
                            if not 0<=precision<=18 or not minimum_units.is_finite() or not minimum_cost.is_finite() or minimum_units<=0 or minimum_cost<=0:
                                raise ValueError("invalid pair rules")
                            units=(notional/ask).quantize(Decimal(1).scaleb(-precision),rounding=ROUND_DOWN)
                        except (ValueError, KeyError, TypeError, ArithmeticError):
                            units=D(0);reason="missing_or_invalid_venue_minimums"
                        if units<=0:
                            reason="missing_or_invalid_venue_minimums"
                        elif units<minimum_units:
                            reason="below_venue_minimum_units"
                        elif units*ask<minimum_cost:
                            reason="below_venue_minimum_cost"
                        else:
                            notional=units*ask
                            ident = self.account.enter(market=pair, side="long", quantity=units, ask=ask, entry_fee=notional*fee_rate)
                            with self.db:
                                self.db.execute("INSERT INTO runtime_positions VALUES(?,?,?)", (ident, now, str(ask*(1-D(self.settings.stop_fraction)))))
                            marks[ident] = {"bid": str(bid), "exit_fee": str(units*bid*fee_rate), "timestamp": observations[pair]["quote"]["timestamp"]}
                            snapshot = self.account.snapshot(marks=marks, now=now, max_mark_age=self.settings.quote_max_age)
                            reason = "PAPER_ENTRY"
            with self.db:
                self.db.execute("UPDATE runtime_decisions SET outcome=? WHERE pair=? AND candle=?", (reason,pair,candidate["candle"]))
            outcomes.append({"pair": pair, "action": reason, **candidate})
        snapshot.update(halted=halted, decisions=outcomes, settings=asdict(self.settings),
                        observation_sources={p:o.get("source") for p,o in observations.items() if p in PAIRS},
                        fill_model="SIMULATED top-of-book with estimated adverse slippage; no depth/queue guarantee")
        self.log(now, "status", snapshot)
        return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--once", action="store_true")
    modes.add_argument("--loop", action="store_true")
    modes.add_argument("--check", action="store_true", help="Public feed diagnostic only; no account/fills")
    modes.add_argument("--health", action="store_true", help="Read-only saved runtime state; no collection/fills")
    parser.add_argument("--config", type=Path, help="Research settings JSON; no credentials")
    parser.add_argument("--interval", type=float, default=60)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--bankroll", type=str)
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parent / "state" / "paper.sqlite")
    parser.add_argument("--halt-file", type=Path, default=Path(__file__).resolve().parent / "HALT")
    parser.add_argument("--fee-rate", type=float)
    parser.add_argument("--slippage-rate", type=float)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval <= 15:
        parser.error("--interval must exceed 15 seconds")
    configured = json.loads(args.config.read_text()) if args.config else {}
    if set(configured) - set(Settings.__dataclass_fields__):
        parser.error("config contains unknown settings; credentials are not accepted")
    if args.fee_rate is not None:
        configured["fee_rate"] = args.fee_rate
    if args.slippage_rate is not None:
        configured["slippage_rate"] = args.slippage_rate
    settings = Settings(**configured)
    settings.validate()
    if args.health:
        if not args.db.exists():
            print(json.dumps({"mode":"PAPER ONLY","initialized":False,"halted":args.halt_file.exists()}))
            return 0
        with sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro",uri=True) as lookup:
            row = lookup.execute("SELECT timestamp,payload FROM runtime_logs WHERE kind='status' ORDER BY id DESC LIMIT 1").fetchone()
        print(json.dumps({"mode":"PAPER ONLY","initialized":True,"running_verified":False,
                          "last_status_age_seconds":time.time()-row[0] if row else None,
                          "halted":args.halt_file.exists(),"last_status":json.loads(row[1]) if row else None},indent=2))
        return 0
    def collect():
        if args.fixture:
            payload = json.loads(args.fixture.read_text())
            if any(o.get("source") != "SYNTHETIC_FIXTURE" for o in payload["observations"].values()):
                raise ValueError("fixtures must be labelled SYNTHETIC_FIXTURE")
            return payload["observations"], float(payload["now"]), []
        observations, errors = {}, []
        for pair in PAIRS:
            try:
                observations[pair] = fetch(pair,settings.signal_minutes)
            except Exception as error:
                errors.append({"pair": pair, "failure_type": type(error).__name__, "reason": "public feed unavailable; no entry or mark from this source"})
        # Refresh both quotes together after history requests so BTC is not marked
        # from an older quote while waiting for SOL's candle downloads.
        if observations:
            try:
                tickers,stamp=request_public("Ticker",{"pair":"XBTUSD,SOLUSD"})
                aliases={"BTC/USD":("XXBTZUSD","XBTUSD","BTC/USD"),"SOL/USD":("SOLUSD","SOL/USD")}
                for pair,observation in observations.items():
                    ticker=next(tickers[k] for k in aliases[pair] if k in tickers)
                    observation["received_at"]=stamp
                    observation["quote"]={"timestamp":stamp,"freshness_kind":"HTTP_RECEIPT_ONLY","bid":ticker["b"][0],"ask":ticker["a"][0]}
            except Exception as error:
                errors.append({"failure_type":type(error).__name__,"reason":"batch quote refresh failed; original quote age guards remain active"})
        return observations, time.time(), errors
    if args.check:
        observations, now, errors = collect()
        statuses = []
        for pair, obs in observations.items():
            try:
                quote(obs, now, settings)
                result = signal(obs, now, settings)
                statuses.append({"pair":pair,"ok":True,"source":obs["source"],"closed_candle":result["candle"]})
            except Exception as error:
                errors.append({"pair":pair,"failure_type":type(error).__name__,"reason":"freshness/schema/warmup diagnostic failed"})
        print(json.dumps({"mode":"PUBLIC FEED CHECK ONLY", "statuses":statuses,"errors":errors},indent=2))
        return 0 if len(statuses)==2 and not errors else 2
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with args.db.with_suffix(".lock").open("a") as lock:
        try:
            if sys.platform == "win32":
                import msvcrt
                lock.write("0")
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            parser.error("another runtime owns this database")
        bankroll = args.bankroll
        if bankroll is None and args.db.exists():
            with sqlite3.connect(args.db) as lookup:
                row = lookup.execute("SELECT initial FROM account WHERE id=1").fetchone()
                bankroll = row[0] if row else None
        if bankroll is None:
            parser.error("--bankroll required for new paper account; no actual funding")
        bot = Bot(args.db, bankroll, settings, args.halt_file)
        try:
            while True:
                if args.loop and args.halt_file.exists():
                    print(json.dumps({"mode":"PAPER ONLY","halted":True,"loop_stopped":True}),flush=True)
                    bot.log(time.time(),"control",{"reason":"halt_file_loop_stop"})
                    break
                observations, now, errors = collect()
                report = bot.tick(observations, now)
                report["feed_errors"] = errors
                bot.log(now,"feed_diagnostics",errors)
                print(json.dumps(report,indent=2,allow_nan=False),flush=True)
                if not args.loop:
                    break
                deadline=time.monotonic()+args.interval
                while time.monotonic()<deadline and not args.halt_file.exists():
                    time.sleep(max(0,min(1,deadline-time.monotonic())))
        finally:
            bot.account.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
