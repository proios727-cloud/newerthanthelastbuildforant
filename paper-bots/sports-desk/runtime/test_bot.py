import copy
import json
from pathlib import Path
import tempfile
import unittest
from bot import SportsBot, Rejected, consensus, depth, validate_mapping

NOW=1800000000

def mapping():
    return dict(ticker='SYNTHETIC-NFL-TEAM-A',sport='americanfootball_nfl',event_id='synthetic-event',outcome='Team A',market_type='h2h',side='yes',expected_outcomes=['Team A','Team B'],independent_bookmakers=['synthetic-book-a','synthetic-book-b'],settlement_verified=True,rules_note='SYNTHETIC fixture: exhaustive binary settlement; no real event',fee_verified=True,fee_note='SYNTHETIC $0.02 per-contract reserve, not actual exchange fee',fee_per_contract=.02,exit_fee_per_contract=.02,uncertainty_margin=.05,minimum_edge=.03,profit_target_per_contract=.05,max_book_age_seconds=5,max_source_age_seconds=120)

def snapshot():
    return dict(market={'ticker':'SYNTHETIC-NFL-TEAM-A','status':'active'},book={'yes_dollars':[['.38','100']],'no_dollars':[['.60','100']]},book_received_at=NOW,book_source_timestamp=NOW,odds_received_at=NOW,synthetic=True,odds={'id':'synthetic-event','sport_key':'americanfootball_nfl','commence_time':NOW+3600,'bookmakers':[{'key':b,'markets':[{'key':'h2h','last_update':NOW,'outcomes':[{'name':'Team A','price':1.3},{'name':'Team B','price':4.2}]}]} for b in ('synthetic-book-a','synthetic-book-b')]})

class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'paper.sqlite';self.bot=SportsBot(self.path,'1000')
    def tearDown(self):
        self.bot.account.close();self.tmp.cleanup()
    def test_entry_budget_persistent_idempotency(self):
        report=self.bot.step(mapping(),snapshot(),NOW)
        self.assertEqual(report['action'],'paper_entry')
        self.assertLessEqual(self.bot.account.initial-self.bot.account._cash(),5)
        self.bot.step(mapping(),snapshot(),NOW)
        self.assertEqual(self.bot.db.execute("SELECT COUNT(*) FROM fills WHERE kind='entry'").fetchone()[0],1)
        self.bot.account.close();self.bot=SportsBot(self.path,'1000')
        self.bot.step(mapping(),snapshot(),NOW)
        self.assertEqual(self.bot.db.execute("SELECT COUNT(*) FROM fills WHERE kind='entry'").fetchone()[0],1)
    def test_unknown_receipt_stale_and_live_skip(self):
        for field in ('book_received_at','book_source_timestamp','odds_received_at'):
            s=snapshot();s[field]=NOW-500
            self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')
        s=snapshot();s['book_source_timestamp']=None
        self.assertIn('unknown',self.bot.step(mapping(),s,NOW)['reason'])
        s=snapshot();s['odds']['commence_time']=NOW
        self.assertIn('live/started',self.bot.step(mapping(),s,NOW)['reason'])
    def test_insufficient_books_and_mapping(self):
        s=snapshot();s['odds']['bookmakers'][0]['markets'][0]['outcomes'].pop()
        self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')
        s=snapshot();s['odds']['id']='different'
        self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')
        m=mapping();m['settlement_verified']=False
        self.assertEqual(self.bot.step(m,snapshot(),NOW)['action'],'skip')
        m=mapping();m['fee_per_contract']=None
        self.assertEqual(self.bot.step(m,snapshot(),NOW)['action'],'skip')
    def test_uncertainty_blocks(self):
        m=mapping();m['uncertainty_margin']=.5
        self.assertEqual(self.bot.step(m,snapshot(),NOW)['action'],'skip')
    def test_net_partial_exit_and_duplicate(self):
        self.bot.step(mapping(),snapshot(),NOW)
        s=snapshot();s['book']['yes_dollars']=[['.65','5']];s['book']['no_dollars']=[['.34','100']]
        report=self.bot.step(mapping(),s,NOW)
        self.assertEqual(report['action'],'paper_exit');self.assertEqual(report['quantity'],'5')
        self.assertEqual(self.bot.account.snapshot(now=NOW)['realized_pnl'],'1.05')
        self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'duplicate')
        self.assertEqual(self.bot.account.position(1)['remaining'],'6')
        # Partial available bids never manufacture equity from unsupported full depth.
        self.assertIsNone(self.bot.status({mapping()['ticker']:s},[mapping()],NOW)['equity'])
    def test_no_overdraft_atomic(self):
        with self.assertRaises(Rejected):
            self.bot.mutate('oversized',ticker='A',side='yes',q=10000,price='.4',fee='20')
        self.assertEqual(self.bot.account._cash(),1000)
        self.assertEqual(self.bot.db.execute('SELECT COUNT(*) FROM actions').fetchone()[0],0)
    def test_size_aware_depth(self):
        q,ask=depth({'no_dollars':[['.6','3'],['.5','7']]},'yes',purchase=True,requested=10)
        self.assertEqual(ask,Decimal('.47'))
    def test_duplicate_h2h_cannot_count_one_book_twice(self):
        s=snapshot();book=s['odds']['bookmakers'][0]
        book['markets'].append(copy.deepcopy(book['markets'][0]))
        s['odds']['bookmakers']= [book]
        self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')
    def test_status_uses_observation_time_after_collection(self):
        self.bot.step(mapping(),snapshot(),NOW)
        s=snapshot()
        s['book_received_at']=NOW+2;s['book_source_timestamp']=NOW+2;s['odds_received_at']=NOW+2
        report=self.bot.status({mapping()['ticker']:s},[mapping()],NOW+2)
        self.assertIsNotNone(report['equity'])
        self.assertEqual(report['unavailable_marks'],[])
    def test_forced_exit_at_deadline_or_after_kickoff_without_odds(self):
        for timestamp in (NOW+3100,NOW+3601):
            with self.subTest(timestamp=timestamp):
                t=tempfile.TemporaryDirectory();b=SportsBot(Path(t.name)/'x.sqlite','1000')
                b.step(mapping(),snapshot(),NOW)
                s=snapshot();s['book_received_at']=timestamp;s['book_source_timestamp']=timestamp;s['odds']=None
                r=b.step(mapping(),s,timestamp)
                self.assertEqual(r['action'],'paper_exit');self.assertEqual(r['exit_reason'],'deadline flatten')
                self.assertEqual(b.account.position(1)['remaining'],'0')
                b.account.close();t.cleanup()
    def test_entry_flatten_deadline_blocked(self):
        s=snapshot();s['odds']['commence_time']=NOW+500
        self.assertIn('flatten window',self.bot.step(mapping(),s,NOW)['reason'])
    def test_deadline_empty_depth_unresolved(self):
        self.bot.step(mapping(),snapshot(),NOW)
        s=snapshot();s['book']['yes_dollars']=[];s['odds']=None
        r=self.bot.step(mapping(),s,NOW)
        self.assertEqual(r['action'],'unresolved_position')
        self.assertIsNone(self.bot.status({mapping()['ticker']:s},[mapping()],NOW)['equity'])
        self.assertEqual(self.bot.db.execute('SELECT COUNT(*) FROM fills').fetchone()[0],1)
    def test_crossed_and_wide_books_rejected(self):
        for price in ('.50','.20'):
            s=snapshot();s['book']['yes_dollars']=[[price,'100']]
            self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')
    def test_stale_book_sources_skip(self):
        s=snapshot()
        for b in s['odds']['bookmakers']:b['markets'][0]['last_update']=NOW-121
        self.assertEqual(self.bot.step(mapping(),s,NOW)['action'],'skip')

from decimal import Decimal
if __name__=='__main__':unittest.main()
