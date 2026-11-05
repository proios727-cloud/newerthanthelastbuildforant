"""Pregame PAPER sports collector/executor. No live-order transport exists."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'quant'))
from credentials import load_odds_key, probe_odds_access
from monitor import PaperAccount
from engine import Rejected, decimal, fresh, no_vig, number

D = Decimal
ROOT = Path(__file__).resolve().parent


def stamp(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            pass
    return number(value, 'timestamp')


def get_json(url):
    # Never return URLs or exception bodies: Odds API credentials live in query strings.
    try:
        with urlopen(Request(url, headers={'User-Agent': 'SportsPaperDesk/1.0'}), timeout=15) as response:
            return json.load(response)
    except Exception:
        raise Rejected('data request failed; check provider access and connectivity') from None


def validate_mapping(m):
    for key in ('ticker', 'sport', 'event_id', 'outcome', 'rules_note', 'fee_note', 'independent_bookmakers'):
        if not m.get(key):
            raise Rejected('mapping missing ' + key)
    if m.get('fee_verified') is not True:
        raise Rejected('fee reserve not explicitly verified for this series')
    if m.get('settlement_verified') is not True:
        raise Rejected('settlement rules not explicitly verified')
    if m.get('market_type') != 'h2h' or m.get('side', 'yes') not in ('yes', 'no'):
        raise Rejected('only explicitly mapped binary h2h outcomes supported')
    outcomes = m.get('expected_outcomes')
    if not isinstance(outcomes, list) or len(outcomes) < 2 or len(set(outcomes)) != len(outcomes) or m['outcome'] not in outcomes:
        raise Rejected('explicit exhaustive outcomes required')
    books = m['independent_bookmakers']
    if not isinstance(books, list) or len(set(books)) < 2:
        raise Rejected('at least two explicitly reviewed independent books required')
    for key in ('fee_per_contract', 'exit_fee_per_contract', 'uncertainty_margin', 'minimum_edge', 'profit_target_per_contract'):
        value = decimal(m.get(key), key)
        if value < 0 or value >= 1:
            raise Rejected(key + ' must be explicit and in [0,1)')
    if decimal(m['fee_per_contract'],'fee reserve') < D('.02') or decimal(m['exit_fee_per_contract'],'exit fee reserve') < D('.02'):
        raise Rejected('per-contract reserves below $0.02 unsupported; verify multiplier and rounding')
    if number(m.get('flatten_before_start_seconds',600),'flatten window') < 0:
        raise Rejected('flatten window must be nonnegative')
    return m


def collect(m, now=None, *, book_only=False):
    """GET-only adapter. REST book has no reliable event timestamp by default."""
    key = os.environ.get('ODDS_API_KEY')
    if not key and not book_only:
        raise Rejected('ODDS_API_KEY not configured')
    ticker = quote(m['ticker'], safe='')
    market = get_json('https://external-api.kalshi.com/trade-api/v2/markets/' + ticker)['market']
    book_response = get_json('https://external-api.kalshi.com/trade-api/v2/markets/' + ticker + '/orderbook')
    received = time.time()
    odds = None
    if not book_only:
        params = urlencode({'apiKey': key, 'bookmakers': ','.join(m['independent_bookmakers']), 'markets': 'h2h', 'oddsFormat': 'decimal'})
        odds = get_json('https://api.the-odds-api.com/v4/sports/' + quote(m['sport'], safe='') + '/events/' + quote(m['event_id'], safe='') + '/odds?' + params)
    fp = book_response.get('orderbook_fp')
    if fp is None:
        # Older REST representation is cents, not dollar strings.
        old = book_response.get('orderbook', {})
        fp = {s + '_dollars': [[str(decimal(p, 'cents') / 100), str(q)] for p, q in old.get(s, [])] for s in ('yes', 'no')}
    return {'market': market, 'book': fp, 'book_received_at': received,
            'book_source_timestamp': book_response.get('source_timestamp'),
            'book_timestamp_kind': 'provider_source' if book_response.get('source_timestamp') else 'receipt_only',
            'odds': odds, 'odds_received_at': time.time(), 'synthetic': False}


def validate_book(m, s, now):
    market = s.get('market', {})
    if market.get('ticker') != m['ticker'] or market.get('status') not in ('open', 'active'):
        raise Rejected('mapped market closed, missing or mismatched')
    fresh(s.get('book_received_at'), now, m.get('max_book_age_seconds', 5), 'book receipt')
    source = s.get('book_source_timestamp')
    if source is not None:
        fresh(stamp(source), now, m.get('max_book_age_seconds', 5), 'book source')
    elif m.get('allow_receipt_only_book') is not True:
        raise Rejected('book source age unknown; receipt-only REST snapshot rejected by default')
    book = s.get('book', {})
    best = {}
    for side in ('yes', 'no'):
        levels = book.get(side + '_dollars')
        if not isinstance(levels, list) or not levels:
            raise Rejected('missing executable two-sided depth')
        prices = []
        for row in levels:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                raise Rejected('invalid book level')
            price, quantity = decimal(row[0], 'price'), decimal(row[1], 'depth')
            if not 0 <= price <= 1 or quantity <= 0:
                raise Rejected('invalid book price/quantity')
            prices.append(price)
        best[side] = max(prices)
    spread = 1 - best['yes'] - best['no']
    limit = decimal(m.get('max_spread', '.03'), 'max_spread')
    if not 0 <= limit <= 1 or spread < 0:
        raise Rejected('crossed or invalid book')
    if spread > limit:
        raise Rejected('book spread exceeds limit')


def validate_snapshot(m, s, now):
    validate_book(m,s,now)
    event = s.get('odds') or {}
    if event.get('id') != m['event_id'] or event.get('sport_key') != m['sport']:
        raise Rejected('explicit event mapping mismatch')
    kickoff = stamp(event.get('commence_time'))
    if kickoff <= now or s.get('live') is True:
        raise Rejected('live/started entries unsupported: no verified live forecast')
    window = number(m.get('flatten_before_start_seconds',600),'flatten window')
    if window < 0 or now >= kickoff-window:
        raise Rejected('new entry blocked inside pregame flatten window')
    fresh(s.get('odds_received_at'), now, m.get('max_source_age_seconds', 120), 'odds receipt')
    return event


def consensus(m, s, now):
    event = validate_snapshot(m, s, now)
    estimates = []
    seen = set()
    for book in event.get('bookmakers', []):
        key = book.get('key')
        if key not in m['independent_bookmakers'] or key in seen:
            continue
        seen.add(key)
        for market in book.get('markets', []):
            if market.get('key') != 'h2h':
                continue
            try:
                fresh(stamp(market.get('last_update')), now, m.get('max_source_age_seconds', 120), 'sportsbook source')
                pairs = market.get('outcomes', [])
                prices = {o['name']: o['price'] for o in pairs}
                if len(prices) != len(pairs) or set(prices) != set(m['expected_outcomes']):
                    continue
                p = no_vig(prices, complete=True, mutually_exclusive=True)[m['outcome']]
                estimates.append(p if m.get('side', 'yes') == 'yes' else 1 - p)
                break  # At most one estimate per reviewed independent bookmaker.
            except (Rejected, KeyError, TypeError):
                continue
    if len(estimates) < max(2, int(m.get('minimum_books', 2))):
        raise Rejected('insufficient fresh complete independent sportsbook outcomes')
    # This margin is a user-configured hypothesis, NOT a calibrated confidence interval.
    median = D(str(statistics.median(estimates)))
    margin = decimal(m['uncertainty_margin'], 'uncertainty_margin')
    return max(D(0), median - margin), {'consensus': str(median), 'books_used': len(estimates), 'uncertainty_margin': str(margin), 'bound_label': 'heuristic hypothesis; uncalibrated'}


def depth(book, side, *, purchase, requested):
    field = ('no' if side == 'yes' else 'yes') if purchase else side
    levels = book.get(field + '_dollars')
    if not isinstance(levels, list) or not levels:
        raise Rejected('missing executable depth')
    rows = []
    for row in levels:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise Rejected('invalid book level')
        p, q = decimal(row[0], 'price'), decimal(row[1], 'depth')
        if not 0 <= p <= 1 or q <= 0:
            raise Rejected('invalid book price/quantity')
        rows.append((1-p if purchase else p, q))
    remaining, total, filled = decimal(requested, 'quantity'), D(0), D(0)
    if remaining <= 0:
        raise Rejected('quantity must be positive')
    for price, available in sorted(rows, reverse=not purchase):
        take = min(available, remaining)
        total += take * price
        filled += take
        remaining -= take
        if remaining == 0:
            break
    if filled == 0:
        raise Rejected('empty fill')
    return filled, total / filled


class SportsBot:
    def __init__(self, path, bankroll):
        self.account = PaperAccount(path, desk='sports', bankroll=bankroll)
        self.db = self.account.db
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS actions (key TEXT PRIMARY KEY, position_id INTEGER, action TEXT);
            CREATE TABLE IF NOT EXISTS mapping_positions (ticker TEXT PRIMARY KEY, position_id INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS mapping_kickoffs (ticker TEXT PRIMARY KEY, kickoff REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, requests INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, timestamp REAL, ticker TEXT, kind TEXT, payload TEXT);
        ''')

    def log(self, now, ticker, kind, payload):
        self.db.execute('INSERT INTO journal VALUES(NULL,?,?,?,?)', (now, ticker, kind, json.dumps(payload, allow_nan=False)))
        self.db.commit()

    def mutate(self, key, *, ticker, side, q, price, fee, position=None, kickoff=None):
        """Action key, position, and accounting journal change in ONE SQLite transaction."""
        q, price, fee = self.account._validate(q, price, fee)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            if self.db.execute('SELECT 1 FROM actions WHERE key=?', (key,)).fetchone():
                self.db.rollback()
                return False
            if position is None:
                if q*price+fee > self.account._cash() or price <= 0:
                    raise Rejected('entry exceeds available cash or invalid ask')
                # Re-check budgets under lock to prevent simultaneous processors oversizing.
                basis = sum((D(a)*D(b)+D(c) for a,b,c in self.db.execute('SELECT remaining,unit_cost,unallocated_entry_fee FROM positions')), D(0))
                if q*price+fee > self.account.initial*D('.005') or basis+q*price+fee > self.account.initial*D('.10'):
                    raise Rejected('entry exceeds 0.5% position or 10% exposure limit')
                if self.db.execute('SELECT 1 FROM mapping_positions WHERE ticker=?', (ticker,)).fetchone():
                    raise Rejected('mapping already entered; one entry per explicit market')
                position = self.db.execute("INSERT INTO positions VALUES(NULL,?,?,?,?,?,'0')", (ticker,side,str(q),str(price),str(fee))).lastrowid
                self.db.execute('INSERT INTO mapping_positions VALUES(?,?)', (ticker,position))
                if kickoff is None: raise Rejected('entry missing verified event start')
                self.db.execute('INSERT INTO mapping_kickoffs VALUES(?,?)',(ticker,kickoff))
                self.db.execute("INSERT INTO fills VALUES(NULL,?,'entry',?,?,?,'0')", (position,str(q),str(price),str(fee)))
                action = 'entry'
            else:
                row = self.db.execute('SELECT remaining,unit_cost,unallocated_entry_fee,realized FROM positions WHERE id=?', (position,)).fetchone()
                if row is None:
                    raise Rejected('unknown position')
                remaining,cost,entry_fee,realized = map(D,row)
                if remaining <= 0 or q > remaining:
                    raise Rejected('exit exceeds remaining')
                if self.account._cash()+q*price-fee < 0:
                    raise Rejected('exit fees exceed cash and proceeds')
                allocated = entry_fee*q/remaining
                pnl = q*(price-cost)-allocated-fee
                self.db.execute('UPDATE positions SET remaining=?,unallocated_entry_fee=?,realized=? WHERE id=?', (str(remaining-q),str(entry_fee-allocated),str(realized+pnl),position))
                self.db.execute("INSERT INTO fills VALUES(NULL,?,'exit',?,?,?,?)", (position,str(q),str(price),str(fee),str(pnl)))
                action = 'exit'
            self.db.execute('INSERT INTO actions VALUES(?,?,?)', (key,position,action))
            self.db.commit()
            return True
        except BaseException:
            self.db.rollback()
            raise

    def step(self, mapping, snapshot, now=None):
        now = time.time() if now is None else now
        ticker = mapping.get('ticker', '<unmapped>')
        try:
            m = validate_mapping(mapping)
            p, evidence = None, {}
            side = m.get('side', 'yes')
            fee, exit_fee = D(str(m['fee_per_contract'])), D(str(m['exit_fee_per_contract']))
            row = self.db.execute('SELECT position_id FROM mapping_positions WHERE ticker=?', (ticker,)).fetchone()
            fingerprint = hashlib.sha256(json.dumps(snapshot,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if row:
                validate_book(m,snapshot,now)
                position_id = row[0]
                pos = self.account.position(position_id)
                if pos['side'] != side or pos['market'] != ticker:
                    raise Rejected('persisted position side differs from mapping; restore original mapping')
                remaining = D(pos['remaining'])
                if remaining <= 0:
                    return {'action':'already_closed','ticker':ticker}
                start = self.db.execute('SELECT kickoff FROM mapping_kickoffs WHERE ticker=?',(ticker,)).fetchone()
                if start is None: raise Rejected('open position missing persisted start time')
                forced = now >= start[0]-number(m.get('flatten_before_start_seconds',600),'flatten window')
                if not forced and snapshot.get('odds'):
                    p, evidence = consensus(m,snapshot,now)
                q, bid = depth(snapshot['book'], side, purchase=False, requested=remaining)
                unit_basis = D(pos['unit_cost']) + D(pos['unallocated_entry_fee'])/remaining
                net_profit = bid-exit_fee-unit_basis
                if not forced and net_profit < D(str(m['profit_target_per_contract'])) and (p is None or p-bid > D(str(m['minimum_edge']))):
                    return {'action':'hold','ticker':ticker,**evidence}
                done = self.mutate('exit:'+str(position_id)+':'+fingerprint, ticker=ticker, side=side, q=q, price=bid, fee=q*exit_fee, position=position_id)
                report = {'action':'paper_exit' if done else 'duplicate','ticker':ticker,'quantity':str(q),'bid':str(bid),'exit_reason':'deadline flatten' if forced else 'profit target or insufficient remaining edge','remaining_unresolved':str(remaining-q),'synthetic':snapshot.get('synthetic',False),'book_timestamp_kind':snapshot.get('book_timestamp_kind','provider_source' if snapshot.get('book_source_timestamp') is not None else 'receipt_only'),'fee_label':'configured conservative PAPER reserve; not exchange-confirmed fee',**evidence}
            else:
                p, evidence = consensus(m,snapshot,now)
                status = self.account.snapshot(now=now)
                budget = min(self.account.initial*D('.005'), max(D(0), self.account.initial*D('.10')-D(status['entry_basis_open'])), D(status['cash']))
                best_q, best_ask = depth(snapshot['book'],side,purchase=True,requested=1)
                count = int(budget/(best_ask+fee)) if best_ask+fee > 0 else 0
                if count <= 0:
                    raise Rejected('budget insufficient for one contract')
                q, ask = depth(snapshot['book'],side,purchase=True,requested=count)
                # Require whole paper contracts and trim until actual depth-weighted cost fits budget.
                q = D(int(q))
                while q > 0:
                    q,ask = depth(snapshot['book'],side,purchase=True,requested=q)
                    if q*(ask+fee) <= budget:
                        break
                    q -= 1
                if q <= 0 or ask <= 0 or p-ask-fee <= 0 or p-ask-fee < D(str(m['minimum_edge'])):
                    raise Rejected('insufficient conservative net edge or affordable depth')
                done = self.mutate('entry:'+ticker, ticker=ticker,side=side,q=q,price=ask,fee=q*fee,kickoff=stamp(snapshot['odds']['commence_time']))
                report = {'action':'paper_entry' if done else 'duplicate','ticker':ticker,'quantity':str(q),'ask':str(ask),'edge':str(p-ask-fee),'synthetic':snapshot.get('synthetic',False),'book_timestamp_kind':snapshot.get('book_timestamp_kind','provider_source' if snapshot.get('book_source_timestamp') is not None else 'receipt_only'),'fee_label':'configured conservative PAPER reserve; not exchange-confirmed fee',**evidence}
            self.log(now,ticker,report['action'],report)
            return report
        except (Rejected, KeyError, ValueError, TypeError) as error:
            report = {'action':'skip','ticker':ticker,'reason':str(error)}
            existing = self.db.execute('SELECT position_id FROM mapping_positions WHERE ticker=?',(ticker,)).fetchone()
            if existing and D(self.account.position(existing[0])['remaining']) > 0:
                report['action']='unresolved_position'; report['remaining_unresolved']=self.account.position(existing[0])['remaining']
            self.log(now,ticker,'skip',report)
            return report

    def status(self, snapshots=None, mappings=None, now=None):
        now = time.time() if now is None else now
        marks = {}
        for m in mappings or []:
            row = self.db.execute('SELECT position_id FROM mapping_positions WHERE ticker=?',(m.get('ticker'),)).fetchone()
            s = (snapshots or {}).get(m.get('ticker'))
            if not row or not s:
                continue
            try:
                validate_mapping(m)
                validate_book(m,s,now)
                pos = self.account.position(row[0]); q = D(pos['remaining'])
                if q <= 0:
                    continue
                filled,bid = depth(s['book'],m.get('side','yes'),purchase=False,requested=q)
                if filled != q:
                    continue  # Never extrapolate partial depth into full liquidation equity.
                marks[row[0]] = {'bid':str(bid),'exit_fee':str(q*D(str(m['exit_fee_per_contract']))),'timestamp':now}
            except (Rejected,KeyError,TypeError):
                continue
        return self.account.snapshot(marks=marks,now=now)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--once',action='store_true'); mode.add_argument('--loop',type=float,nargs='?',const=300); mode.add_argument('--check',action='store_true'); mode.add_argument('--check-api',action='store_true')
    parser.add_argument('--env-file',type=Path,help='Reuse an existing local .env; only Odds API key loaded')
    parser.add_argument('--fixture',type=Path,help='Offline explicitly synthetic fixtures')
    parser.add_argument('--config','--mapping',dest='mapping',type=Path,default=ROOT/'config.example.json')
    parser.add_argument('--db',type=Path,default=ROOT/'paper.sqlite')
    parser.add_argument('--bankroll',default='1000',help='Immutable initial PAPER bankroll, USD')
    parser.add_argument('--interval',type=float,default=300,help='Deprecated alias interval if --loop omitted value')
    parser.add_argument('--halt-file',type=Path,default=ROOT/'HALT')
    args=parser.parse_args()
    try:
        credential_source=load_odds_key(args.env_file)
    except ValueError as error:
        parser.error(str(error))
    if args.check_api:
        print(json.dumps({'mode':'READ ONLY API CHECK','credential_source':credential_source,**probe_odds_access()},indent=2))
        return
    interval = args.loop if args.loop is not None else args.interval
    if interval < 1 or interval > 3600:
        parser.error('loop interval must be 1..3600 seconds')
    config=json.loads(args.mapping.read_text())
    mappings=config.get('mappings',[])
    problems=[]
    for m in mappings:
        try: validate_mapping(m)
        except Rejected as error: problems.append({'ticker':m.get('ticker'),'reason':str(error)})
    if not mappings: problems.append({'reason':'no explicit market mappings configured'})
    if not args.fixture and not os.environ.get('ODDS_API_KEY'): problems.append({'reason':'ODDS_API_KEY missing'})
    if args.check:
        print(json.dumps({'mode':'PAPER ONLY','ready':not problems,'problems':problems,'live_betting':'not implemented','book_source_age':'REST receipt is not verified event freshness'},indent=2));return
    args.db.parent.mkdir(parents=True,exist_ok=True)
    bot=SportsBot(args.db,args.bankroll)
    try:
        while True:
            if args.halt_file.exists():
                print(json.dumps({'mode':'PAPER ONLY','halted':True,'account':bot.status()},indent=2));break
            payload=json.loads(args.fixture.read_text()) if args.fixture else None
            now=payload.get('now',time.time()) if payload else time.time()
            snapshots={};reports=[]
            for m in mappings:
                try:
                    validate_mapping(m)
                    if payload:
                        s=payload['snapshots'][m['ticker']]
                        if s.get('synthetic') is not True: raise Rejected('offline fixture must declare synthetic=true')
                    else:
                        existing=bot.db.execute('SELECT 1 FROM mapping_positions WHERE ticker=?',(m['ticker'],)).fetchone()
                        if existing:
                            s=collect(m,book_only=True)
                        else:
                            day=datetime.now(timezone.utc).date().isoformat()
                            cap=int(config.get('max_odds_requests_per_day',100))
                            if cap < 1: raise Rejected('daily provider request cap must be positive')
                            bot.db.execute('BEGIN IMMEDIATE')
                            used=bot.db.execute('SELECT requests FROM quota WHERE day=?',(day,)).fetchone()
                            if used and used[0] >= cap:
                                bot.db.rollback(); raise Rejected('daily Odds API request budget exhausted')
                            bot.db.execute('INSERT INTO quota VALUES(?,1) ON CONFLICT(day) DO UPDATE SET requests=requests+1',(day,))
                            bot.db.commit()
                            s=collect(m)
                    snapshots[m['ticker']]=s
                    reports.append(bot.step(m,s,now=time.time() if not payload else now))
                except (Rejected,KeyError,TypeError) as error:
                    report={'action':'skip','ticker':m.get('ticker'),'reason':str(error)}
                    existing=bot.db.execute('SELECT position_id FROM mapping_positions WHERE ticker=?',(m.get('ticker'),)).fetchone()
                    if existing and D(bot.account.position(existing[0])['remaining'])>0:
                        report['action']='unresolved_position';report['remaining_unresolved']=bot.account.position(existing[0])['remaining']
                    reports.append(report)
                    bot.log(now,m.get('ticker','<unmapped>'),'skip',report)
            print(json.dumps({'mode':'PAPER ONLY','synthetic':bool(payload),'decisions':reports,'account':bot.status(snapshots,mappings,now if payload else time.time())},indent=2),flush=True)
            if not args.loop: break
            deadline=time.monotonic()+interval
            while time.monotonic()<deadline and not args.halt_file.exists():
                time.sleep(min(1,deadline-time.monotonic()))
    finally: bot.account.close()

if __name__=='__main__':main()
