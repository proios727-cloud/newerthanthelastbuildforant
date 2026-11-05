import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot


NOW = 1780002000 // 86400 * 86400 + 12*3600 + 60


def observation(now=NOW):
    def rows(interval):
        end = now // interval * interval
        return [[end-(251-i)*interval,100+i,101+i,99+i,100+i,100+i,1,1] for i in range(252)]
    return {"source":"SYNTHETIC_FIXTURE", "received_at":now,"hourly_at":now,"daily_at":now,
            "pair_rules":{"ordermin":".00005","costmin":".5","lot_decimals":8},
            "quote":{"timestamp":now,"bid":"100","ask":"100.1"},
            "hourly":rows(3600),"daily":rows(86400)}


class Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)/"paper.sqlite"
        self.settings = bot.Settings(fee_rate=.001,slippage_rate=0)
        self.instance = bot.Bot(self.path,"1000",self.settings)

    def tearDown(self):
        self.instance.account.close()
        self.directory.cleanup()

    def entry(self, observations=None, now=NOW, candle=100):
        with patch.object(bot,"signal",return_value={"entry":True,"exit":False,"regime":True,"candle":candle}):
            return self.instance.tick(observations or {"BTC/USD":observation(now)},now)

    def test_closed_candles_excludes_current_and_future(self):
        rows=observation()["hourly"]
        closed=bot.closed_candles(rows,3600,NOW)
        self.assertEqual(len(closed),251)
        self.assertLessEqual(closed[-1][0]+3600,NOW)

    def test_daily_regime_and_signal_reject_missing_history(self):
        result=bot.signal(observation(),NOW,self.settings)
        self.assertTrue(result["regime"])
        obs=observation(); obs["daily"]=obs["daily"][-5:]
        with self.assertRaisesRegex(ValueError,"warmup"):
            bot.signal(obs,NOW,self.settings)

    def test_candle_gap_and_invalid_ohlc_rejected(self):
        rows=observation()["hourly"]; del rows[10]
        with self.assertRaisesRegex(ValueError,"missing candle"):
            bot.closed_candles(rows,3600,NOW)
        rows=observation()["hourly"]; rows[0][2]=1
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            bot.closed_candles(rows,3600,NOW)

    def test_stale_quote_blocks_entry_and_missing_mark(self):
        obs=observation(); obs["quote"]["timestamp"]=NOW-20
        self.assertEqual(self.entry({"BTC/USD":obs})["cash"],"1000")
        self.entry()
        result=self.entry({"BTC/USD":obs},candle=101)
        self.assertIsNone(result["equity"])
        self.assertEqual(len(result["unavailable_marks"]),1)

    def test_stale_candles_block_entry_but_fresh_quote_can_mark(self):
        self.entry()
        obs=observation(); obs["hourly_at"]=NOW-60
        result=self.entry({"BTC/USD":obs},candle=101)
        self.assertIsNotNone(result["equity"])
        self.assertEqual(self.instance.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0],1)

    def test_duplicate_across_restart_never_reenters(self):
        self.entry()
        self.instance.account.close()
        self.instance=bot.Bot(self.path,"1000",self.settings)
        result=self.entry()
        self.assertTrue(any(d["action"]=="DUPLICATE_SKIP" for d in result["decisions"]))
        self.assertEqual(self.instance.db.execute("SELECT COUNT(*) FROM fills").fetchone()[0],1)

    def test_cash_exposure_and_bid_ask_fees(self):
        result=self.entry()
        self.assertGreaterEqual(bot.D(result["cash"]),bot.D("900"))
        self.assertLessEqual(bot.D(result["entry_basis_open"]),bot.D("100"))
        self.assertLess(bot.D(result["total_pnl"]),0)  # crossing spread + both fees
        obs=observation(NOW+1); obs["quote"].update(bid="110",ask="110.1")
        with patch.object(bot,"signal",return_value={"entry":False,"exit":True,"regime":True,"candle":101}):
            report=self.instance.tick({"BTC/USD":obs},NOW+1)
        qty,cost,fee=self.instance.db.execute("SELECT quantity,price,fee FROM fills WHERE kind='entry'").fetchone()
        expected=bot.D(qty)*(bot.D("110")-bot.D(cost))-bot.D(fee)-bot.D(qty)*bot.D("110")*bot.D(".001")
        self.assertLess(abs(bot.D(report["realized_pnl"])-expected),bot.D("1e-20"))
        self.assertEqual(len(report["open_positions"]),0)

    def test_default_high_fees_reject_cost_cap(self):
        self.instance.settings=bot.Settings()
        result=self.entry()
        self.assertEqual(result["cash"],"1000")
        self.assertTrue(any(d["action"]=="estimated_roundtrip_cost_above_cap" for d in result["decisions"]))

    def test_shared_exposure_blocks_second_pair(self):
        report=self.entry({"BTC/USD":observation(),"SOL/USD":observation()})
        self.assertEqual(len(report["open_positions"]),1)
        self.assertTrue(any(d["action"]=="shared_position_limit" for d in report["decisions"]))

    def test_halt_blocks_fills_and_marks_missing_on_failure(self):
        halt=Path(self.directory.name)/"HALT"; halt.touch(); self.instance.halt=halt
        self.assertEqual(self.entry()["cash"],"1000")
        halt.unlink(); self.entry(candle=101)
        report=self.instance.tick({},NOW+1)
        self.assertIsNone(report["equity"])

    def test_redacts_unknown_fixture_fields(self):
        obs=observation(); obs["secret"]="do-not-log";obs["quote"]["token"]="do-not-log"
        self.entry({"BTC/USD":obs})
        logs="".join(r[0] for r in self.instance.db.execute("SELECT payload FROM runtime_logs"))
        self.assertNotIn("do-not-log",logs)

    def test_venue_minimum_and_missing_rules_block_entry(self):
        obs=observation();obs["pair_rules"]["ordermin"]="10"
        self.assertEqual(self.entry({"BTC/USD":obs})["cash"],"1000")
        obs=observation();del obs["pair_rules"]
        result=self.entry({"BTC/USD":obs},candle=101)
        self.assertEqual(result["cash"],"1000")

    def test_crash_claim_without_fill_never_retries(self):
        with self.instance.db:
            self.instance.db.execute("INSERT INTO runtime_decisions VALUES('BTC/USD',100,'claimed')")
        self.assertEqual(self.entry()["cash"],"1000")

    def test_missing_metadata_reconciles_at_fresh_bid_with_fee(self):
        self.instance.account.enter(market="BTC/USD",side="long",quantity=".1",ask="100.1",entry_fee=".01001")
        report=self.entry()
        self.assertTrue(any(d.get("reason")=="missing_position_metadata" for d in report["decisions"]))
        self.assertLess(bot.D(report["realized_pnl"]),0)

    def test_unclosed_daily_candle_cannot_change_signal(self):
        obs=observation();original=bot.signal(obs,NOW,self.settings)
        obs["daily"][-1][1:5]=[99999,99999,99999,99999]
        self.assertEqual(bot.signal(obs,NOW,self.settings),original)

    def test_4h_closure_and_daily_regime(self):
        obs=observation();obs["signal_minutes"]=240
        end=NOW//14400*14400
        obs["hourly"]=[[end-(251-i)*14400,100+i,101+i,99+i,100+i,100+i,1,1] for i in range(252)]
        settings=bot.Settings(signal_minutes=240,research_only=True,max_cost=.02)
        result=bot.signal(obs,NOW,settings)
        self.assertEqual(result["candle"],end-14400)
        self.assertTrue(result["regime"])
        obs["hourly"][-1][1:5]=[99999]*4
        self.assertEqual(bot.signal(obs,NOW,settings),result)
        with self.assertRaisesRegex(ValueError,"interval differs"):
            bot.signal(obs,NOW,self.settings)

    def test_two_percent_cost_cap_requires_research_flag(self):
        with self.assertRaisesRegex(ValueError,"explicit research_only"):
            bot.Settings(max_cost=.02).validate()
        bot.Settings(signal_minutes=240,research_only=True,max_cost=.02).validate()
        with self.assertRaises(ValueError):
            bot.Settings(research_only=True,max_cost=.021).validate()


if __name__=="__main__": unittest.main()
