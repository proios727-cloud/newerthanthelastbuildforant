"""Pipeline test on LIVE Binance data with a STUB Drex (test only; never used by bot.py)."""
import os, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("BOT_STATE_DIR", tempfile.mkdtemp())
import config; config.STATE_DIR = Path(os.environ["BOT_STATE_DIR"])
import bot as botmod
from config import Config
from journal import verify, read
from strategies import Signal

class StubDrex:
    def __init__(self, regime): self.regime, self.calls = regime, []
    def decide(self, state, questions, image=None):
        self.calls.append((list(questions), image is not None and image.exists()))
        if "regime" in questions:
            p = {"TRENDING": .1, "CHOPPY": .1, "PANIC": .1}; p[self.regime] = .8
            return {"model": "stub", "request_id": "t", "answers": {"regime": {"type": "choice", "choice": self.regime, "probabilities": p}}}
        return {"model": "stub", "request_id": "t", "answers": {
            "take": {"type": "noul", "noul": .9},
            "book_control": {"type": "choice", "probabilities": {"BUYERS": .7, "SELLERS": .1, "BALANCED": .2}},
            "entry": {"type": "choice", "probabilities": {"MARKET": .8, "LIMIT": .1, "WAIT": .1}}}}

def run(regime, force_signal):
    cfg = Config.load()
    b = botmod.Bot(cfg); b.drex = StubDrex(regime)
    if force_signal:  # force a signal so TAKE path is exercised regardless of the live chart
        botmod.signal_for = lambda r, c, cfg: Signal("breakout", "LONG", c[-1]["c"], c[-1]["c"] * .99, c[-1]["c"] * 1.03, "forced")
    assert b.cycle()
    return b

b = run("TRENDING", True)
kinds = [r["kind"] for r in read(config.STATE_DIR / "decisions.jsonl")]
print("events:", kinds)
assert kinds[:4] == ["regime", "signal", "gate", "fill"], kinds
pos = b.broker.s["position"]; print("position:", {k: pos[k] for k in ("side","qty","entry","stop")})
notional = pos["qty"] * pos["entry"]; assert notional <= 0.2 * 10000 + 1, notional
print("notional", round(notional, 2), "<= cap 2000 ✓; risk at stop", round(pos["qty"]*(pos["entry"]-pos["stop"]), 2))
assert all(img for _, img in b.drex.calls), "snapshot image sent on every Drex call"
assert b.cycle() is False, "no double-processing of the same candle"
print("log chain:", verify(config.STATE_DIR / "decisions.jsonl"))
# PANIC flattens
b.broker.s["last_candle_t"] -= 1; b.drex = StubDrex("PANIC"); b.cycle()
assert b.broker.s["position"] is None
print("PANIC ->", [r["kind"] for r in read(config.STATE_DIR / "decisions.jsonl")][-3:])
snap = sorted((config.STATE_DIR / "snapshots").glob("*.png"))[-1]; print("snapshot", snap.stat().st_size // 1024, "KiB")
import shutil; shutil.copy(snap, Path(__file__).resolve().parents[1] / "sample_snapshot.png")
print("ALL PASS")
