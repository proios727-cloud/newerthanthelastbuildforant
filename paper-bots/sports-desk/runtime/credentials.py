"""Load only an Odds API token; never evaluate environment-file expressions."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NAMES = ('ODDS_API_KEY', 'THE_ODDS_API_KEY')
TOKEN = re.compile(r'[A-Za-z0-9_-]{8,512}')


def load_odds_key(path=None):
    existing = os.environ.get('ODDS_API_KEY') or os.environ.get('THE_ODDS_API_KEY')
    if existing:
        if not TOKEN.fullmatch(existing):
            raise ValueError('Odds API token format invalid; value omitted')
        os.environ['ODDS_API_KEY'] = existing
        return 'process_environment'
    if path is None:
        return 'not_configured'
    p = Path(path)
    try:
        if p.stat().st_size > 65536:
            raise ValueError('credential file too large')
        text = p.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        raise ValueError('cannot read specified environment file; contents omitted') from None
    values = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('export '): line = line[7:].strip()
        name, separator, value = line.partition('=')
        if not separator or name.strip() not in NAMES: continue
        value = value.strip()
        if value.startswith(('"', "'")):
            quote = value[0]; end = value.find(quote, 1)
            if end < 0 or value[end+1:].strip() and not value[end+1:].strip().startswith('#'):
                raise ValueError('malformed quoted Odds API token; value omitted')
            value = value[1:end]
        else:
            value = value.split(' #', 1)[0].strip()
        if not TOKEN.fullmatch(value):
            raise ValueError('Odds API token must be a literal token; interpolation and commands rejected')
        values.append(value)
    if not values: raise ValueError('environment file has no supported Odds API token field')
    if len(set(values)) != 1: raise ValueError('conflicting Odds API token fields; values omitted')
    os.environ['ODDS_API_KEY'] = values[0]
    return 'specified_environment_file'


def probe_odds_access(opener=None):
    """Free sports-list endpoint; no wagers, no quota-consuming odds requests."""
    key = os.environ.get('ODDS_API_KEY')
    if not key:
        return {'connected': False, 'reason': 'ODDS_API_KEY not configured'}
    url = 'https://api.the-odds-api.com/v4/sports?' + urlencode({'apiKey': key})
    try:
        with (opener or urlopen)(Request(url, headers={'User-Agent':'SportsPaperDesk/1.0'}), timeout=15) as response:
            data = json.loads(response.read(2_000_000))
            if not isinstance(data, list): raise ValueError('unexpected provider schema')
            quotas = {name: response.headers.get(name) for name in ('x-requests-remaining','x-requests-used')}
        return {'connected': True, 'active_sports_returned': len(data), 'quota_headers': quotas,
                'endpoint':'sports_list', 'trading_enabled':False}
    except Exception:
        return {'connected':False,'reason':'provider authentication/connectivity check failed; credential and response body omitted'}
