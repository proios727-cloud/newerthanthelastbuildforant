import copy
from datetime import datetime,timedelta
from decimal import Decimal
import unittest
from replay import Replay,Policy,synthetic_rows,ET

D=Decimal

class AccountingTests(unittest.TestCase):
    def setup_engine(self,mode='weekly',bankroll='1000',**policy):
        self.engine=Replay(bankroll,Policy(mode=mode,strategy='breakout20',**policy),synthetic=True)
        self.bars,self.quotes=synthetic_rows(mode)
        self.at=datetime(2026,10,12,9,55,tzinfo=ET)
        self.engine.pending['SPY']={'time':self.at,'session':'2026-10-12','underlying':600,'strategy':'breakout20'}
        return self.engine

    def quote(self,index=0,**fields):
        q=copy.deepcopy(self.quotes[index]);q.update(fields)
        if 'timestamp' in fields: q['source_timestamp']=q['timestamp'];q['receive_time']=fields.get('received_at',q['timestamp'])
        elif 'received_at' in fields: q['receive_time']=fields['received_at']
        self.engine.quote(q,datetime.fromisoformat(q.get('receive_time',q.get('received_at',q['timestamp']))))

    def test_multiplier_fees_cash_and_realized_actual_quotes(self):
        self.setup_engine();self.quote();self.quote(1)
        self.assertEqual(self.engine.cash,D('1009.70'))
        self.assertEqual(self.engine.realized,D('9.70'))
        self.assertEqual(self.engine.fees,D('1.30'))
        self.assertEqual(self.engine.trades[0]['contracts'],1)
        self.assertEqual(D(self.engine.trades[0]['basis']),D('40.65'))
        self.assertLessEqual(D(self.engine.trades[0]['basis']),50)

    def test_same_timestamp_cannot_fill_signal(self):
        self.setup_engine()
        with self.assertRaisesRegex(ValueError,'strictly after signal'):
            self.quote(timestamp=self.at.isoformat())
        self.assertEqual(self.engine.cash,1000)

    def test_exit_must_follow_entry(self):
        self.setup_engine();self.quote()
        at=self.quotes[0]['timestamp']
        with self.assertRaises(ValueError):self.quote(1,timestamp=at)
        self.assertEqual(self.engine.realized,0)

    def test_stale_future_crossed_wide_quotes(self):
        self.setup_engine()
        for fields in ({'bid':'.41','ask':'.40'},{'bid':'.30','ask':'.40'},
                       {'received_at':(self.at+timedelta(minutes=1)).isoformat()},
                       {'received_at':self.at.isoformat()}, {'bid':'NaN'}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.quote(**fields)
        self.assertEqual(self.engine.cash,1000)

    def test_exact_metadata_and_call_only(self):
        self.setup_engine()
        for fields in ({'root':'AAPL'},{'option_type':'put'},{'symbol':'SPY261016P00600000'},
                       {'strike':601},{'expiration':'2026-10-17'},{'multiplier':10},{'dte':3},
                       {'delta':None},{'delta':.8},{'source':None}):
            with self.subTest(fields=fields),self.assertRaises((ValueError,TypeError)):
                self.quote(**fields)
        self.assertEqual(self.engine.cash,1000)

    def test_delta_may_change_after_entry_without_blocking_exit(self):
        self.setup_engine();self.quote();self.quote(1,delta=.85)
        self.assertEqual(self.engine.realized,D('9.70'))

    def test_future_expiry_outside_weekly_bucket(self):
        self.setup_engine()
        with self.assertRaisesRegex(ValueError,'DTE bucket'):
            self.quote(symbol='SPY261020C00600000',expiration='2026-10-20',dte=8)

    def test_affordable_full_premium_includes_entry_fee(self):
        self.setup_engine(bankroll='800')
        with self.assertRaisesRegex(ValueError,'cash-risk budget'):self.quote()
        self.assertEqual(self.engine.cash,800)

    def test_correlation_group_blocks_second_root(self):
        self.setup_engine();self.quote()
        self.engine.pending['QQQ']=dict(self.engine.pending.get('SPY',{}))
        self.quote(1,root='QQQ',symbol='QQQ261016C00600000')
        self.assertEqual(len(self.engine.trades),1)
        self.assertIn('already exposed',self.engine.skips[-1]['reason'])

    def test_iv_or_underlying_does_not_manufacture_premium_gain(self):
        self.setup_engine();self.quote()
        self.quote(1,bid='.38',ask='.40',iv=2.0,underlying=700)
        self.assertEqual(self.engine.realized,0)
        self.assertEqual(len(self.engine.trades),1)
        self.assertLess(D(self.engine.snapshots[-1]['equity']),1000)

    def test_stop_uses_actual_bid_and_net_fees(self):
        self.setup_engine();self.quote();self.quote(1,bid='.31',ask='.32',delta=.25)
        self.assertEqual(self.engine.realized,D('-10.30'))
        self.assertEqual(self.engine.trades[-1]['reason'],'premium_stop')

    def test_50_percent_target_requires_observed_move(self):
        self.setup_engine(target=D('.50'));self.quote();self.quote(1)
        self.assertEqual(self.engine.realized,0)
        self.quote(1,timestamp=(self.at+timedelta(minutes=2)).isoformat(),bid='.60',ask='.61')
        self.assertEqual(self.engine.trades[-1]['reason'],'premium_target')

    def test_missing_exit_quote_unresolved_not_zero_or_gain(self):
        self.setup_engine()
        result=self.engine.run([],self.quotes[:1])
        self.assertEqual(result['realized_net_pnl'],'0')
        self.assertEqual(len(result['unresolved_positions']),1)
        self.assertIsNone(result['snapshots'][-1]['equity'])
        self.assertFalse(result['report_complete'])
        self.assertIsNone(result['net_total_return'])
        self.assertEqual(D(result['cash']),D('959.35'))

    def test_overnight_disabled_and_session_cutoff(self):
        self.setup_engine();self.quote()
        with self.assertRaisesRegex(ValueError,'overnight'):
            self.quote(1,timestamp='2026-10-13T09:31:00-04:00',dte=3)
        self.quote(1,timestamp='2026-10-12T15:30:01-04:00',bid='.39',ask='.40')
        self.assertEqual(self.engine.trades[-1]['reason'],'session_cutoff')

    def test_0dte_20min_time_stop_and_13_entry_cutoff(self):
        self.setup_engine('0dte');self.quote()
        self.quote(1,timestamp='2026-10-12T10:16:00-04:00',bid='.39',ask='.40')
        self.assertEqual(self.engine.trades[-1]['reason'],'time_stop')
        self.setup_engine('0dte');self.engine.pending['SPY']['time']=datetime(2026,10,12,12,59,59,tzinfo=ET)
        with self.assertRaisesRegex(ValueError,'entry outside'):
            self.quote(timestamp='2026-10-12T13:00:00-04:00')

    def test_weekly_90minute_time_stop(self):
        self.setup_engine();self.quote()
        self.quote(1,timestamp='2026-10-12T11:26:00-04:00',bid='.39',ask='.40')
        self.assertEqual(self.engine.trades[-1]['reason'],'time_stop')

    def test_early_close_forces_observed_exit_at_1230(self):
        self.setup_engine();self.quote(session_close='2026-10-12T13:00:00-04:00')
        self.quote(1,timestamp='2026-10-12T12:30:01-04:00',bid='.39',ask='.40',session_close='2026-10-12T13:00:00-04:00')
        self.assertEqual(self.engine.trades[-1]['reason'],'session_cutoff')

    def test_missing_bid_liquidity_does_not_fabricate_zero_exit(self):
        self.setup_engine();self.quote()
        with self.assertRaisesRegex(ValueError,'liquidity'):
            self.quote(1,bid=0,ask='.01',bid_size=0)
        self.assertEqual(self.engine.realized,0)

    def test_spread_blowout_does_not_block_valid_risk_reducing_exit(self):
        self.setup_engine('0dte');self.quote()
        self.quote(1,bid='.20',ask='.40',bid_size=1)
        self.assertEqual(self.engine.trades[-1]['reason'],'premium_stop')
        self.assertEqual(self.engine.realized,D('-21.30'))

    def test_real_quote_requires_explicit_sizes(self):
        self.setup_engine();self.engine.synthetic=False
        quote=copy.deepcopy(self.quotes[0]);quote['source']='PROVIDER_TEST';quote.pop('bid_size');quote.pop('ask_size')
        with self.assertRaisesRegex(ValueError,'explicit bid_size'):
            self.engine.quote(quote,datetime.fromisoformat(quote['receive_time']))
        self.assertEqual(self.engine.cash,1000)

    def test_0dte_and_weekly_cannot_cross_contract_bucket(self):
        self.setup_engine('weekly')
        with self.assertRaisesRegex(ValueError,'DTE bucket'):
            self.quote(symbol='SPY261012C00600000',expiration='2026-10-12',dte=0)
        self.setup_engine('0dte')
        with self.assertRaisesRegex(ValueError,'DTE bucket'):
            self.quote(symbol='SPY261016C00600000',expiration='2026-10-16',dte=4)

class ChronologyTests(unittest.TestCase):
    def test_weekly_complete_synthetic_replay_only(self):
        bars,quotes=synthetic_rows('weekly')
        report=Replay(policy=Policy(mode='weekly',strategy='breakout20'),synthetic=True).run(bars,quotes)
        self.assertEqual(len(report['trades']),2)
        self.assertEqual(report['realized_net_pnl'],'9.70')
        self.assertIn('NONE',report['performance_evidence'])
        self.assertGreater(report['trades'][0]['timestamp'],report['trades'][0]['signal_close'])

    def test_0dte_complete_synthetic_replay_only(self):
        bars,quotes=synthetic_rows('0dte')
        report=Replay(policy=Policy(mode='0dte',strategy='breakout20'),synthetic=True).run(bars,quotes)
        self.assertEqual(len(report['trades']),2)
        self.assertEqual(report['policy']['dte_bucket'],'0dte')

    def test_unfinished_bar_never_signal_even_with_future_quote(self):
        bars,quotes=synthetic_rows()
        report=Replay(synthetic=True).run(bars,quotes,as_of=bars[-1]['timestamp'])
        self.assertEqual(report['trades'],[])
        self.assertTrue(any('unfinished' in s['reason'] for s in report['skipped']))

    def test_unsorted_input_sorted_by_observable_events(self):
        bars,quotes=synthetic_rows()
        first=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars,quotes)
        second=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(list(reversed(bars)),list(reversed(quotes)))
        self.assertEqual(first['trades'],second['trades'])

    def test_duplicate_and_gapped_bars_rejected(self):
        engine=Replay();bars,_=synthetic_rows()
        at=datetime.fromisoformat(bars[0]['timestamp'])+timedelta(minutes=1)
        engine.bar(bars[0],at)
        with self.assertRaisesRegex(ValueError,'chronology'):engine.bar(bars[0],at)
        with self.assertRaisesRegex(ValueError,'chronology'):engine.bar(bars[2],at+timedelta(minutes=2))

    def test_no_future_bar_mutation_changes_prior_fill(self):
        bars,quotes=synthetic_rows()
        report=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars,quotes)
        future=dict(bars[-1],timestamp='2026-10-12T09:55:00-04:00',receive_time='2026-10-12T09:56:00-04:00',close=1000,high=1000,open=1000,low=1000)
        altered=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars+[future],quotes)
        self.assertEqual(report['trades'][0],altered['trades'][0])

    def test_low_delta_profile_is_explicit_and_external(self):
        bars,quotes=synthetic_rows()
        for quote in quotes: quote['delta']=.25
        policy=Policy(strategy='breakout20',delta_min=.15,delta_max=.35)
        report=Replay(policy=policy,synthetic=True).run(bars,quotes)
        self.assertEqual(len(report['trades']),2)
        blocked=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars,quotes)
        self.assertEqual(blocked['trades'],[])

    def test_bar_delivery_delay_cannot_fill_earlier_quote(self):
        bars,quotes=synthetic_rows()
        bars[-1]['receive_time']='2026-10-12T09:56:01-04:00'
        result=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars,quotes)
        self.assertEqual(result['trades'],[])

    def test_real_replay_rejects_empty_or_synthetic_sources(self):
        with self.assertRaisesRegex(ValueError,'incomplete real'):Replay().run([],[])
        bars,quotes=synthetic_rows()
        with self.assertRaisesRegex(ValueError,'synthetic source'):Replay().run(bars,quotes)

    def test_orb_and_vwap_reclaim_hypotheses_independently_trigger(self):
        bars,quotes=synthetic_rows()
        for i,bar in enumerate(bars):
            price=600 if i<20 else 599 if i<24 else 605
            bar.update(open=price,high=price+.001,low=price-.001,close=price)
        for strategy in ('orb','vwap-reclaim'):
            with self.subTest(strategy=strategy):
                report=Replay(policy=Policy(strategy=strategy),synthetic=True).run(bars,quotes)
                self.assertEqual(len(report['trades']),2)
                self.assertEqual(report['trades'][0]['strategy'],strategy)

    def test_late_bar_is_stale_not_fresh_new_signal(self):
        bars,quotes=synthetic_rows()
        bars[-1]['receive_time']='2026-10-12T09:55:10-04:00'
        quotes[0]['timestamp']='2026-10-12T09:55:11-04:00'
        quotes[0]['source_timestamp']=quotes[0]['receive_time']=quotes[0]['timestamp']
        report=Replay(policy=Policy(strategy='breakout20'),synthetic=True).run(bars,quotes)
        self.assertEqual(report['trades'],[])
        self.assertTrue(any('stale underlying' in r['reason'] for r in report['skipped']))

    def test_policy_rejects_invalid_numbers(self):
        for policy in (Policy(fee=D('NaN')),Policy(entry_fraction=D('.06')),Policy(quote_age_seconds=float('inf'))):
            with self.assertRaises(ValueError):Replay(policy=policy)

if __name__=='__main__':unittest.main()
