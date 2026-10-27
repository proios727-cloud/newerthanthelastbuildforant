import gzip
import json
import os
import random
import tempfile
import unittest

from gmdesk import analyze, record, replay, shadow
from gmdesk.core import VPIN, Monitor, decompose, maker_fee, position_limit


def synth_markets(n=20, seed=3, toxic_every=3):
    """Binary markets: noise takers at fair price, plus informed takers in 'toxic' markets."""
    rnd, out, t0 = random.Random(seed), [], 1_000_000.0
    for i in range(n):
        R = 1.0 if rnd.random() < 0.5 else 0.0
        toxic = i % toxic_every == 0
        close, tr, p = t0 + 900 * (i + 1), [], 0.5
        for k in range(600):
            ts = close - 900 + k * 1.5
            informed = toxic and rnd.random() < 0.7
            s = (1 if R else -1) if informed else rnd.choice((1, -1))
            p = min(0.97, max(0.03, p + (0.004 * s if informed else rnd.uniform(-0.01, 0.01))))
            tr.append({"ts": ts, "p": round(p, 3), "q": rnd.randint(1, 20), "s": s})
        out.append({"ticker": f"T{i}", "close_ts": close, "R": R, "trades": tr})
    return out


class Core(unittest.TestCase):
    def test_vpin_balanced_and_onesided(self):
        v = VPIN(10, n=3)
        for _ in range(30):
            v.push(5, 1); v.push(5, -1)
        self.assertAlmostEqual(v.value, 0.0)
        for _ in range(6):
            v.push(10, 1)
        self.assertAlmostEqual(v.value, 1.0)

    def test_vpin_none_until_window_full(self):
        v = VPIN(10, n=5); v.push(25, 1)
        self.assertIsNone(v.value)

    def test_monitor_states_and_multiplier(self):
        m = Monitor(0.5, 0.7)
        m.update(0.4); self.assertEqual((m.status, m.multiplier(0.4)), ("ACTIVE", 1.0))
        m.update(0.6); self.assertEqual(m.status, "WARNING"); self.assertAlmostEqual(m.multiplier(0.6), 2.0)
        m.update(0.8); self.assertIsNone(m.multiplier(0.8))

    def test_limits_and_fee(self):
        self.assertEqual(position_limit(20, 0), 20); self.assertEqual(position_limit(20, 1), 5)
        self.assertEqual(maker_fee(0.5, 100), 0.44)       # ceil(0.0175*100*0.25 dollars) to the cent
        self.assertEqual(maker_fee(0.5, 1), 0.01)

    def test_decompose_bounds(self):
        rnd = random.Random(1)
        sides = [rnd.choice((1, -1)) for _ in range(400)]
        prices = [0.5 + 0.01 * s + rnd.uniform(-0.002, 0.002) for s in sides]   # bid-ask bounce
        d = decompose(prices, sides)
        self.assertTrue(0 <= d["as_fraction"] <= 1)
        self.assertAlmostEqual(d["effective_c"], 2.0, delta=0.4)
        self.assertIsNone(decompose([0.5 + 0.001 * i for i in range(50)], [1] * 50))   # no bounce: undefined


class Record(unittest.TestCase):
    def test_norm_trade_and_ts(self):
        r = record.norm_trade({"trade_id": "a", "ticker": "X", "created_time": "2026-10-07T13:14:59.5Z",
                               "yes_price_dollars": "0.4200", "count_fp": "3.5", "taker_side": "no"}, "S")
        self.assertEqual((r["p"], r["q"], r["s"]), (0.42, 3.5, -1))
        self.assertAlmostEqual(r["ts"] % 1, 0.5)

    def test_backfill_writes_and_skips_existing(self):
        def fetch(path, params=None):
            if path == "/markets":
                return {"markets": [{"ticker": "M1", "close_time": "2026-10-07T13:15:00Z", "result": "yes"}]}
            return {"trades": [{"trade_id": "1", "ticker": "M1", "created_time": "2026-10-07T13:10:00Z",
                                "yes_price_dollars": "0.6", "count_fp": "2", "taker_side": "yes"}]}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(record.backfill("S", 5, d, fetch, log=lambda *a, **k: None), 1)
            self.assertEqual(record.backfill("S", 5, d, fetch, log=lambda *a, **k: None), 0)
            ms = analyze.load(os.path.join(d, "S"))
            self.assertEqual((len(ms), ms[0]["R"], ms[0]["trades"][0]["s"]), (1, 1.0, 1))


class Calibrate(unittest.TestCase):
    def test_no_lookahead_and_markout_sign(self):
        ms = synth_markets(6)
        rows = analyze.annotate(ms, bucket=50, n=5)
        self.assertIsNone(rows[0]["vpin"])
        tox = [r for r in rows if r["ticker"] == "T0"]
        self.assertLess(sum(r["settle_c"] * r["q"] for r in tox), 0)   # makers lose to informed flow

    def test_run_report_shape(self):
        rep = analyze.run(synth_markets(30), n=10)
        self.assertEqual(rep["markets"], {"train": 18, "test": 12})
        self.assertIn("pass", rep["gate2"])
        self.assertEqual(len(rep["maker_markout_settle_by_vpin"]), 5)


class Replay(unittest.TestCase):
    def test_fill_needs_trade_through_quote(self):
        model = {"warn": 9, "halt": 10, "cuts": [0.2, 0.4, 0.6, 0.8], "adverse_c": [0] * 5, "stop_tau": 0,
                 "bucket": 10, "n": 2}
        cfg = dict(replay.DEFAULTS, base_half_c=2.0, latency_s=0.0)
        q = replay.Quoter(1000, model, cfg, False, VPIN(10, 2))
        q.on_trade({"ts": 0, "p": 0.5, "q": 1, "s": 1})
        bid, ask, _ = q.requote(1)
        self.assertEqual((bid, ask), (0.48, 0.52))
        self.assertIsNone(q.on_trade({"ts": 2, "p": 0.52, "q": 3, "s": 1}))          # equal price: behind queue
        f = q.on_trade({"ts": 3, "p": 0.53, "q": 3, "s": 1})
        self.assertEqual((f["side"], f["px"], f["q"]), ("sell_yes", 0.52, 3))
        self.assertEqual(q.bk.inv, -3)

    def test_gm_halts_and_beats_as_on_toxic_synthetic(self):
        rep = replay.run(synth_markets(45, toxic_every=2), tune_grid=(1.0, 3.0))
        self.assertGreaterEqual(rep["gm_as"]["total_pnl"], rep["pure_as"]["total_pnl"])
        self.assertIn("ci95", rep["diff_per_market"])


class Shadow(unittest.TestCase):
    def test_report_gate4(self):
        with tempfile.TemporaryDirectory() as d:
            log, rp = os.path.join(d, "s.jsonl"), os.path.join(d, "r.json")
            json.dump({"gm_as": {"total_pnl": 10, "contracts": 1000, "fills": 200, "markets": 20}}, open(rp, "w"))
            with open(log, "w") as f:
                for i in range(20):
                    for _ in range(10):
                        f.write(json.dumps({"ev": "fill"}) + "\n")
                    f.write(json.dumps({"ev": "settle", "pnl": 0.5, "contracts": 50}) + "\n")
            out = shadow.report(log, rp)
            self.assertTrue(out["gate4"]["pass"])


if __name__ == "__main__":
    unittest.main()
