"""Deterministic long-call PAPER event replay. No broker, credentials, or order API."""
from __future__ import annotations
import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from decimal import Decimal
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ET = ZoneInfo('America/New_York')
except ZoneInfoNotFoundError:
    raise SystemExit('New York timezone data is missing. On Windows run: py -3 -m pip install tzdata ; then retry. Other systems: python -m pip install tzdata') from None
D = lambda value: Decimal(str(value))
ROOTS = ('SPY', 'QQQ')


def numeric(value, name):
    try:
        result = float(value)
    except (ValueError,TypeError):
        raise ValueError(name+' must be numeric') from None
    if isinstance(value,bool) or not math.isfinite(result):
        raise ValueError(name+' must be finite')
    return result


def stamp(value):
    if isinstance(value,(int,float)):
        result = numeric(value,'timestamp')
        if result < 0: raise ValueError('negative timestamp')
        return datetime.fromtimestamp(result,ET)
    value = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if value.tzinfo is None: raise ValueError('timestamps must have explicit timezone')
    return value.astimezone(ET)


def ema(values, period):
    result = sum(values[:period])/period
    for value in values[period:]: result += 2/(period+1)*(value-result)
    return result


@dataclass(frozen=True)
class Policy:
    mode: str = 'weekly'
    strategy: str = 'orb'
    fee: Decimal = Decimal('.65')
    target: Decimal = Decimal('.25')
    stop: Decimal = Decimal('.20')
    max_spread: Decimal = Decimal('.10')
    entry_fraction: Decimal = Decimal('.05')
    exposure_fraction: Decimal = Decimal('.10')
    quote_age_seconds: float = 5
    max_signal_age_seconds: float = 120
    max_bar_delay_seconds: float = 5
    delta_gate: bool = True
    delta_min: float = .45
    delta_max: float = .65
    near_atm_fraction: float | None = .02

    def validate(self):
        if self.mode not in ('weekly','0dte') or self.strategy not in ('orb','vwap-reclaim','breakout20'):
            raise ValueError('invalid mode or strategy')
        for name in ('fee','target','stop','max_spread','entry_fraction','exposure_fraction'):
            value = getattr(self,name)
            if not isinstance(value,Decimal) or not value.is_finite(): raise ValueError(name+' must be finite Decimal')
        if self.fee<0 or self.target not in (D('.25'),D('.50')) or not 0<self.stop<1:
            raise ValueError('invalid fee/target/stop')
        if not 0<self.max_spread<=1 or not 0<self.entry_fraction<=D('.05') or not 0<self.exposure_fraction<=D('.10'):
            raise ValueError('invalid risk or spread limit')
        if numeric(self.quote_age_seconds,'quote age')<=0 or numeric(self.max_signal_age_seconds,'signal age')<=0 or numeric(self.max_bar_delay_seconds,'bar delay')<0:
            raise ValueError('age limits must be positive')
        if not 0<=numeric(self.delta_min,'delta min')<=numeric(self.delta_max,'delta max')<=1:
            raise ValueError('invalid external delta profile')
        if self.near_atm_fraction is not None and not 0<numeric(self.near_atm_fraction,'near ATM fraction')<=1:
            raise ValueError('invalid near ATM fraction')


class Replay:
    def __init__(self, bankroll='1000', policy=Policy(), synthetic=False):
        policy.validate()
        self.initial = D(numeric(bankroll,'bankroll'))
        if self.initial<=0: raise ValueError('bankroll must be positive')
        self.cash, self.realized, self.fees, self.peak = self.initial,D(0),D(0),self.initial
        self.policy, self.synthetic = policy,synthetic
        self.position=None
        self.history={}
        self.pending={}
        self.trades=[]
        self.skips=[]
        self.snapshots=[]
        self.provenance=set()
        self.session_ends={}
        self.seen_quotes=set()
        self.terminal_unresolved=[]

    def session_end(self,row,at):
        key=str(at.date())
        value=stamp(row['session_close']) if row.get('session_close') else self.session_ends.get(key,datetime.combine(at.date(),time(16),ET))
        if value.date()!=at.date() or not time(12,30)<=value.time()<=time(16): raise ValueError('invalid regular/early session close')
        if key in self.session_ends and self.session_ends[key]!=value: raise ValueError('conflicting session close metadata')
        self.session_ends[key]=value
        return value

    def skip(self,reason,row=None):
        self.skips.append({'reason':reason,'root':(row or {}).get('root'),'timestamp':(row or {}).get('timestamp')})

    def bar(self,row,event_time):
        root=row['root']; opening=stamp(row['timestamp']); closed=opening+timedelta(minutes=1)
        if event_time<closed: raise ValueError('unfinished bar')
        if (event_time-closed).total_seconds()>self.policy.max_bar_delay_seconds: raise ValueError('stale underlying bar delivery')
        if root not in ROOTS or opening.second or opening.microsecond: raise ValueError('invalid bar root/minute')
        session_end=self.session_end(row,opening)
        if opening.weekday()>4 or not time(9,30)<=opening.time() or closed>session_end: raise ValueError('bar outside regular session')
        values={k:numeric(row.get(k),k) for k in ('open','high','low','close','volume')}
        if min(values[k] for k in ('open','high','low','close'))<=0 or values['volume']<0:
            raise ValueError('invalid OHLC/volume')
        if values['low']>min(values['open'],values['close']) or values['high']<max(values['open'],values['close']) or values['low']>values['high']:
            raise ValueError('inconsistent OHLC')
        if not row.get('source'): raise ValueError('missing bar provenance')
        self.provenance.add(str(row['source']))
        key=(root,opening.date())
        history=self.history.setdefault(key,[])
        if history and opening != history[-1]['at']+timedelta(minutes=1): raise ValueError('duplicate/missing/unordered bar chronology')
        history.append(dict(at=opening,**values))
        if self.position and self.position['session'] != str(opening.date()):
            self.terminal_unresolved.append(self.position)
            self.position=None  # Never use next-session quotes to invent overnight exits.
        self.pending={r:s for r,s in self.pending.items() if s['session']==str(opening.date())}
        entry_cut=min(datetime.combine(closed.date(),time(13) if self.policy.mode=='0dte' else time(15),ET),session_end-timedelta(minutes=60))
        if not time(9,45)<=closed.time() or closed>=entry_cut or len(history)<21: return
        if history[0]['at'].time()!=time(9,30): return # session VWAP/ORB requires opening history.
        closes=[b['close'] for b in history]
        fast,slow=ema(closes,9),ema(closes,21)
        volume=sum(b['volume'] for b in history)
        if volume<=0: return
        vwap=sum((b['high']+b['low']+b['close'])/3*b['volume'] for b in history)/volume
        relative=history[-1]['volume']/(sum(b['volume'] for b in history[-21:-1])/20) if sum(b['volume'] for b in history[-21:-1])>0 else 0
        trend=closes[-1]>vwap and fast>slow and relative>=1.2
        orb_high=max(b['high'] for b in history[:15])
        if self.policy.strategy=='orb':
            trigger=trend and closes[-1]>orb_high and closes[-2]<=orb_high
        elif self.policy.strategy=='breakout20':
            trigger=trend and closes[-1]>max(b['high'] for b in history[-21:-1])
        else:
            old_volume=sum(b['volume'] for b in history[:-1])
            old_vwap=sum((b['high']+b['low']+b['close'])/3*b['volume'] for b in history[:-1])/old_volume
            trigger=trend and closes[-2]<=old_vwap
        if trigger:
            self.pending[root]={'time':event_time,'bar_close':closed,'session':str(opening.date()),'underlying':closes[-1],
                                'strategy':self.policy.strategy,'rvol':relative,'vwap':vwap,'ema9':fast,'ema21':slow}

    def validate_quote(self,row,now):
        event=stamp(row.get('source_timestamp',row['timestamp'])); received=stamp(row.get('receive_time',row.get('received_at',row['timestamp'])))
        if 'source_timestamp' in row and event!=stamp(row['timestamp']): raise ValueError('source/event timestamp mismatch')
        session_end=self.session_end(row,event)
        if event.weekday()>4 or not time(9,30)<=event.time() or event>session_end: raise ValueError('quote outside declared regular session')
        if event>received or not 0<=(now-event).total_seconds()<=self.policy.quote_age_seconds:
            raise ValueError('future or stale quote event')
        if received!=now: raise ValueError('quote receipt/event mismatch')
        if not row.get('source'): raise ValueError('missing quote provenance')
        root=row.get('root'); symbol=str(row.get('symbol','')).replace(' ','')
        match=re.fullmatch(r'(SPY|QQQ)(\d{6})C(\d{8})',symbol)
        if root not in ROOTS or not match or match[1]!=root or row.get('option_type')!='call': raise ValueError('exact SPY/QQQ call symbol required')
        expiry=datetime.strptime(match[2],'%y%m%d').date()
        if str(expiry)!=str(row.get('expiration')) or D(match[3])/1000!=D(row.get('strike')): raise ValueError('symbol/strike/expiration mismatch')
        if expiry<event.date() or event.date()!=received.date(): raise ValueError('expired or cross-session quote')
        if expiry.weekday()>4: raise ValueError('weekend expiration unsupported')
        dte=(expiry-event.date()).days
        if numeric(row.get('dte'),'dte')!=dte: raise ValueError('DTE metadata mismatch')
        if (self.policy.mode=='0dte' and dte!=0) or (self.policy.mode=='weekly' and not 1<=dte<=7): raise ValueError('wrong DTE bucket')
        if numeric(row.get('multiplier'),'multiplier')!=100: raise ValueError('100 option multiplier required')
        if self.policy.delta_gate:
            delta=numeric(row.get('delta'),'externally provided delta')
            if not 0<=delta<=1: raise ValueError('invalid external call delta')
        bid,ask=D(numeric(row.get('bid'),'bid')),D(numeric(row.get('ask'),'ask'))
        if bid<0 or ask<=0 or bid>ask: raise ValueError('crossed/invalid option quote')
        if bid==0 and numeric(row.get('bid_size',0),'bid size')<=0: raise ValueError('zero bid has no executable sell liquidity')
        for size_key in ('bid_size','ask_size'):
            if size_key in row and numeric(row[size_key],size_key)<0: raise ValueError('negative option quote size')
        is_exit=bool(self.position and self.position['symbol']==symbol)
        if (ask-bid)/ask>self.policy.max_spread and not is_exit: raise ValueError('wide option premium spread')
        if not self.synthetic and ('bid_size' not in row or 'ask_size' not in row): raise ValueError('real quote requires explicit bid_size and ask_size')
        self.provenance.add(str(row['source']))
        return event,received,bid,ask,symbol

    def snapshot(self,now,mark=None):
        equity=self.cash if not self.position and not self.terminal_unresolved else None
        if self.position and mark is not None and not self.terminal_unresolved:
            equity=self.cash+mark*100*self.position['contracts']-self.policy.fee*self.position['contracts']
        if equity is not None: self.peak=max(self.peak,equity)
        risk=sum((p['basis'] for p in self.terminal_unresolved),D(0))+(self.position['basis'] if self.position else D(0))
        self.snapshots.append({'timestamp':now.isoformat(),'cash':str(self.cash),'equity':None if equity is None else str(equity),
                               'full_premium_at_risk':str(risk),'realized_net_pnl':str(self.realized),'fees_paid':str(self.fees),
                               'sampled_peak':str(self.peak),'drawdown':None if equity is None else str(self.peak-equity)})

    def quote(self,row,now):
        event,received,bid,ask,symbol=self.validate_quote(row,now)
        fingerprint=(symbol,event.isoformat(),received.isoformat())
        if fingerprint in self.seen_quotes: raise ValueError('duplicate option quote timestamp')
        self.seen_quotes.add(fingerprint)
        p=self.position
        if p and p['symbol']==symbol:
            if str(event.date())!=p['session']: raise ValueError('overnight disabled; no exit from next session')
            if event<=p['entry_at']: raise ValueError('exit quote must be strictly after entry')
            if row.get('bid_size') is not None and numeric(row['bid_size'],'bid size')<p['contracts']: raise ValueError('insufficient exit bid size; unresolved until executable quote')
            holding=(event-p['entry_at']).total_seconds()/60
            reason=None
            if event>=min(datetime.combine(event.date(),time(15,30),ET),self.session_end(row,event)-timedelta(minutes=30)): reason='session_cutoff'
            elif bid<=p['ask']*(1-self.policy.stop): reason='premium_stop'
            elif bid>=p['ask']*(1+self.policy.target): reason='premium_target'
            elif holding>=(20 if self.policy.mode=='0dte' else 90): reason='time_stop'
            if reason:
                proceeds=bid*100*p['contracts'];fee=self.policy.fee*p['contracts']
                profit=proceeds-fee-p['basis']
                self.cash+=proceeds-fee;self.realized+=profit;self.fees+=fee
                self.trades.append({'action':'exit','symbol':symbol,'timestamp':event.isoformat(),'bid':str(bid),'contracts':p['contracts'],
                                    'net_realized_pnl':str(profit),'reason':reason,'source':row['source']})
                self.position=None
            self.snapshot(now,bid if self.position else None)
            return
        if self.position or self.terminal_unresolved:
            self.skip('correlated SPY/QQQ group already exposed',row);return
        signal=self.pending.get(row['root'])
        if not signal: return
        if event<=signal['time']: raise ValueError('entry quote must be strictly after signal close')
        if (event-signal['time']).total_seconds()>self.policy.max_signal_age_seconds: raise ValueError('signal expired before executable quote')
        cutoff=min(datetime.combine(event.date(),time(13) if self.policy.mode=='0dte' else time(15),ET),self.session_end(row,event)-timedelta(minutes=60))
        if str(event.date())!=signal['session'] or not time(9,45)<=event.time() or event>=cutoff: raise ValueError('entry outside same-session window')
        if self.policy.delta_gate and not self.policy.delta_min<=numeric(row['delta'],'external delta')<=self.policy.delta_max: raise ValueError('entry external delta outside configured profile')
        if self.policy.near_atm_fraction is not None and abs(float(row['strike'])/signal['underlying']-1)>self.policy.near_atm_fraction: raise ValueError('outside near ATM limit')
        cost=ask*100+self.policy.fee
        budget=min(self.cash,self.initial*self.policy.entry_fraction,self.initial*self.policy.exposure_fraction)
        count=int(budget/cost)
        if row.get('ask_size') is not None and numeric(row['ask_size'],'ask size')<count: raise ValueError('insufficient entry ask size')
        if count<1: raise ValueError('premium plus fees exceeds per-entry cash-risk budget')
        basis=cost*count
        self.cash-=basis;self.fees+=self.policy.fee*count
        self.position={'symbol':symbol,'contracts':count,'ask':ask,'basis':basis,'entry_at':event,'session':signal['session']}
        self.pending.clear() # one active correlated asset group; consume all signals.
        self.trades.append({'action':'entry','symbol':symbol,'root':row['root'],'timestamp':event.isoformat(),'signal_close':signal.get('bar_close',signal['time']).isoformat(),'signal_available_at':signal['time'].isoformat(),
                            'ask':str(ask),'contracts':count,'entry_fee':str(self.policy.fee*count),'basis':str(basis),'source':row['source'],
                            'external_delta':row.get('delta'),'strategy':signal['strategy']})
        self.snapshot(now,bid)

    def run(self,bars,quotes,as_of=None):
        if not self.synthetic:
            if not bars or not quotes: raise ValueError('incomplete real replay: both underlying bars and option quotes required')
            if any('SYNTHETIC' in str(r.get('source','')).upper() for r in bars+quotes): raise ValueError('synthetic source requires synthetic flag')
            if any(not b.get('receive_time') for b in bars) or any(not q.get('source_timestamp') or not q.get('receive_time') for q in quotes): raise ValueError('real replay requires separate source/receipt timestamp metadata')
        events=[]
        for b in bars:
            opening=stamp(b['timestamp']);closed=opening+timedelta(minutes=1)
            if as_of is not None and closed>stamp(as_of): self.skip('unfinished/future bar',b);continue
            available=stamp(b.get('receive_time',b.get('received_at',closed.isoformat())))
            if available<closed: self.skip('unfinished bar received before close',b);continue
            if as_of is not None and available>stamp(as_of): self.skip('future bar receipt',b);continue
            events.append((available,0,b))
        for q in quotes:
            available=stamp(q.get('receive_time',q.get('received_at',q['timestamp'])))
            if as_of is not None and available>stamp(as_of): self.skip('future quote receipt',q);continue
            events.append((available,1,q))
        events.sort(key=lambda e:(e[0],e[1]))
        for at,kind,row in events:
            try:
                if kind==0: self.bar(row,at)
                else: self.quote(row,at)
            except (ValueError,KeyError,TypeError,ArithmeticError) as error:
                self.skip(str(error) if isinstance(error,ValueError) else 'invalid input schema',row)
        if self.position: self.terminal_unresolved.append(self.position);self.position=None
        if events: self.snapshot(events[-1][0])
        return {'mode':'PAPER EVENT REPLAY ONLY','synthetic':self.synthetic,'performance_evidence':'NONE: fixtures are accounting tests' if self.synthetic else 'Historical replay only; no live-fill or future-performance evidence',
                'policy':{'dte_bucket':self.policy.mode,'strategy':self.policy.strategy,'target':str(self.policy.target),'fee_per_contract_per_side':str(self.policy.fee),'multiplier':100,'external_delta_range':[self.policy.delta_min,self.policy.delta_max]},
                'report_complete':bool(bars and quotes and self.history) and not self.terminal_unresolved,'inputs_present':bool(bars and quotes),
                'net_total_return':None if self.terminal_unresolved or not (bars and quotes and self.history) else str(self.realized/self.initial),
                'initial_bankroll':str(self.initial),'cash':str(self.cash),'realized_net_pnl':str(self.realized),'fees_paid':str(self.fees),
                'unresolved_positions':[{'symbol':p['symbol'],'contracts':p['contracts'],'basis':str(p['basis']),'reason':'no verified same-session exit quote; no fabricated liquidation'} for p in self.terminal_unresolved],
                'trades':self.trades,'skipped':self.skips,'snapshots':self.snapshots,'sources':sorted(self.provenance),
                'limitations':['No live orders, option Greeks estimation, IV model, or depth/queue guarantee','Bid/ask history and external delta must be independently sourced','Exchange holiday calendar not included; exact contract metadata required','Signals are unvalidated hypotheses; ORB/VWAP/EMA/RVOL do not establish an edge']}


def load_rows(path):
    if path.suffix.lower()=='.csv':
        with path.open(newline='') as f: return list(csv.DictReader(f))
    value=json.loads(path.read_text())
    return value['rows'] if isinstance(value,dict) else value


def synthetic_rows(mode='weekly'):
    start=datetime(2026,10,12,9,30,tzinfo=ET)
    bars=[]
    for i in range(25):
        price=600+i*.002 if i<24 else 601
        bars.append(dict(timestamp=(start+timedelta(minutes=i)).isoformat(),root='SPY',open=price,high=price+.001,low=price-.001,close=price,volume=100 if i<24 else 300,source='SYNTHETIC_FIXTURE'))
    expiry='2026-10-16' if mode=='weekly' else '2026-10-12'
    suffix='261016' if mode=='weekly' else '261012'
    base=dict(root='SPY',symbol='SPY'+suffix+'C00600000',strike=600,expiration=expiry,option_type='call',dte=4 if mode=='weekly' else 0,multiplier=100,delta=.55,source='SYNTHETIC_FIXTURE',bid_size=10,ask_size=10)
    quotes=[dict(base,timestamp=(start+timedelta(minutes=25,seconds=1)).isoformat(),bid='.38',ask='.40'),
            dict(base,timestamp=(start+timedelta(minutes=26)).isoformat(),bid='.51',ask='.52')]
    for bar in bars: bar['receive_time']=(stamp(bar['timestamp'])+timedelta(minutes=1)).isoformat()
    for quote in quotes: quote['source_timestamp']=quote['timestamp'];quote['receive_time']=quote['timestamp']
    return bars,quotes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['audit'])
    parser.add_argument('--barsfile',type=Path);parser.add_argument('--quotesfile',type=Path)
    parser.add_argument('--mode',choices=['weekly','0dte'],required=True)
    parser.add_argument('--strategy',choices=['orb','vwap-reclaim','breakout20'],default='breakout20')
    parser.add_argument('--bankroll',default='1000');parser.add_argument('--fee',default='.65')
    parser.add_argument('--max-bar-delay-seconds',type=float,default=5)
    parser.add_argument('--near-atm-fraction',type=float,default=.02);parser.add_argument('--no-near-atm-gate',action='store_true')
    parser.add_argument('--trades-csv',type=Path,help='Optional separate trade journal CSV')
    parser.add_argument('--delta-min',type=float,default=.45);parser.add_argument('--delta-max',type=float,default=.65)
    parser.add_argument('--target',choices=['.25','.50'],default='.25')
    parser.add_argument('--synthetic',action='store_true');parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--as-of',help='Explicit final observable timestamp; unfinished bars skipped')
    args=parser.parse_args()
    if args.synthetic:
        if args.barsfile or args.quotesfile: parser.error('synthetic uses generated labelled fixtures only')
        bars,quotes=synthetic_rows(args.mode)
    else:
        if not args.barsfile or not args.quotesfile: parser.error('real replay requires both independently sourced files')
        bars,quotes=load_rows(args.barsfile),load_rows(args.quotesfile)
        if any(r.get('source')=='SYNTHETIC_FIXTURE' for r in bars+quotes): parser.error('synthetic sources require --synthetic')
    policy=Policy(mode=args.mode,strategy=args.strategy,fee=D(args.fee),target=D(args.target),delta_min=args.delta_min,delta_max=args.delta_max,near_atm_fraction=None if args.no_near_atm_gate else args.near_atm_fraction,max_bar_delay_seconds=args.max_bar_delay_seconds)
    report=Replay(args.bankroll,policy,args.synthetic).run(bars,quotes,args.as_of)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if args.trades_csv:
        args.trades_csv.parent.mkdir(parents=True,exist_ok=True)
        fields=sorted({key for trade in report['trades'] for key in trade}) or ['action','symbol','timestamp']
        with args.trades_csv.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(report['trades'])
    print(json.dumps({k:report[k] for k in ('mode','synthetic','performance_evidence','realized_net_pnl','unresolved_positions')},indent=2))

if __name__=='__main__':main()
