import importlib.util
import json
import pathlib
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GexSnapshotTests(unittest.TestCase):
    def test_snapshot_files_and_summary(self):
        gs = _load("gex_snapshot")
        d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d))
        gs.main([str(ROOT / "options/data/chains/SPY-2026-11-02T1739.json"), "--out", str(d)])
        gs.main([str(ROOT / "options/data/chains/SPY-2026-11-02T1739.json"), "--out", str(d)])
        snap = json.loads((d / "gex.json").read_text())
        self.assertIn(snap["regime"], ("positive", "negative"))
        self.assertTrue(snap["by_strike"])
        self.assertTrue(all(abs(b["strike"] - snap["spot"]) <= 0.05 * snap["spot"] for b in snap["by_strike"]))
        self.assertEqual(len((d / "gex_log.jsonl").read_text().splitlines()), 2)


class RhChainTranscriptTests(unittest.TestCase):
    def test_transcript_to_chain_with_since(self):
        rh = _load("rh_chain_from_transcript")
        d = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d))
        pre = "mcp__Robinhood__"

        def use(i, name, ts):
            return json.dumps({"timestamp": ts, "message": {"content": [{"type": "tool_use", "id": i, "name": pre + name, "input": {}}]}})

        def res(i, data, ts):
            return json.dumps({"timestamp": ts, "message": {"content": [
                {"type": "tool_result", "tool_use_id": i, "content": json.dumps({"data": data})}]}})

        t = "2026-11-02T17:40:00Z"
        lines = [
            use("a", "get_equity_quotes", t),
            res("a", {"results": [{"quote": {"symbol": "SPY", "last_trade_price": "758.28", "venue_last_trade_time": "2026-11-02T17:39:32Z"}}]}, t),
            use("b", "get_option_instruments", t),
            res("b", {"instruments": [
                {"id": "i1", "chain_symbol": "SPY", "strike_price": "758", "type": "call", "expiration_date": "2026-11-02"},
                {"id": "i2", "chain_symbol": "SPY", "strike_price": "758", "type": "put", "expiration_date": "2026-11-02"}]}, t),
            use("c", "get_option_quotes", t),
            res("c", {"results": [
                {"quote": {"instrument_id": "i1", "implied_volatility": "0.2", "open_interest": "100", "volume": "5", "gamma": "0.05"}},
                {"quote": {"instrument_id": "i2", "implied_volatility": "0.0", "open_interest": "100"}}]}, t),
        ]
        tr = d / "t.jsonl"
        tr.write_text("\n".join(lines) + "\n")
        chains = rh.build(*rh.collect(lines))
        self.assertEqual(len(chains["SPY"]["contracts"]), 1)
        self.assertEqual(chains["SPY"]["skipped_no_iv"], 1)
        self.assertEqual(rh.build(*rh.collect(lines, since="2026-11-03T00:00:00Z")), {})

        import contextlib
        import io
        for argv in ([str(tr), str(d / "o1")], [str(tr), str(d / "o2"), "--since", "2026-11-01T00:00:00Z"]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rh.main(argv)
            summ = json.loads(buf.getvalue())
            self.assertEqual((summ["symbols"], summ["contracts"], len(summ["saved"])), (["SPY"], 1, 1))
            self.assertTrue(pathlib.Path(summ["saved"][0]).exists())


if __name__ == "__main__":
    unittest.main()
