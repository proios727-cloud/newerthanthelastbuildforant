# 24/7 Agent Hedge Fund

An 8-seat agent desk that researches, sizes, and risk-checks trades around the clock across **US equities/ETFs** (regular hours) and **crypto** (24/7). The agents plan the trades and the human approves them. **No order is sent until you reply `EXECUTE` to a preview that is less than 5 minutes old.**

**Mode: `PAPER`.** Market data is live (Alpha Vantage). No broker or exchange is wired, so every fill is a paper fill.

## Files

| Path | What it is |
|---|---|
| `desk.json` | The single config: seats, funnel, limits, handoffs and gates. Edit this file; everything else is generated from it. |
| `board.html` | Control-room board built from `desk.json`. Open it in a browser. **Load config** lets you paste a different config for a quick look. |
| `charters/<seat>.md` | One charter per seat: mission, trigger, inputs, outputs, done-when, and what it must never do. |
| `scripts/build_board.py` | Validates `desk.json` and renders `board.html`. It refuses a broken or dishonest config (for example LIVE mode while blockers are open). |
| `scripts/gen_charters.py` | Regenerates the charters from `desk.json`. |
| `assets/desk-board.html` | The board template. |
| `fund/ledger.py` | Paper ledger: cash, long/short positions, average cost, realized P&L, NAV, peak and drawdown, and a fund-day roll at 00:00 ET. |
| `fund/risk.py` | The Risk Officer's rules as pure functions. PASS comes with a max size; VETO names the rule. |
| `fund/preview.py` | Order preview → `EXECUTE` gate → paper fill. There is no live execution path. |
| `fund/__main__.py` | The command-line tool (see below). Its state lives in `ledger/`. |
| `fund/shadow.py` | Quant Scanner signals (momentum, breakout, mean reversion) and the shadow book, which trades every risk-passed signal at the close with no approval step. Also merges connector bars into `ledger/bars.json`. |
| `fund/receipt.py` | Session receipts for gate 4: ledger snapshot, the day's event counts, and a breach check (gross cap, position cap + 1-point drift, opening fill on a halted day). A VETO is not a breach. |
| `ledger/` | Live paper-run state and `receipts/`, committed so the 30-day record persists. |
| `tests/` | Unit tests: `python3 -m unittest -v` |

```bash
python3 scripts/build_board.py desk.json --out board.html
python3 scripts/gen_charters.py desk.json --out charters
```

## Running the paper fund

```bash
python3 -m fund init                                   # start at desk.json fund.starting_nav ($100k)
python3 -m fund mark BTC/USD 84266.90 --bid 84263.99 --ask 84267.30
python3 -m fund preview BTC/USD buy 1 --price 84266.90 --bid 84263.99 --ask 84267.30 --stop 80000 --target 92000
python3 -m fund approve <preview-id> EXECUTE          # must be exact and within 5 min; risk is re-checked
python3 -m fund status
python3 -m fund receipt --label close                  # ledger/receipts/<fund-day>-close.json with a breach check
python3 -m fund sync-board                             # ledger numbers → desk.json tiles/funnel → board.html
```

The limits, universe and fees all live in the `fund` block of `desk.json`. The placeholder universe is SPY, QQQ, IWM, NVDA, AMD, AAPL, MSFT, TSLA, BTC/USD, ETH/USD and SOL/USD. Edit that block to change them.

**Rules the code enforces:** orders only for symbols in the universe; quotes must be ≤ 120 s old; equities trade only 09:30–16:00 ET on weekdays (holidays are not modeled); spread ≤ 10 bps for equities and 20 bps for crypto; halts at a −3% day or a −10% drawdown; a 15-minute macro-event blackout; caps of 5% per position, 150% gross, 20% per group and 1% of ADV. Orders that reduce a position skip the halts and caps, so the fund can always get smaller.

## Seats

| Seat | Role | Job |
|---|---|---|
| Portfolio Manager `pm` | router | Routes work, sets the daily risk budget, holds the approval queue |
| Macro & News `macro` | intel | Labels the regime (risk-on/off/neutral) and flags event risk in the next 24h |
| Quant Scanner `quant` | scanner | Momentum, mean-reversion and breakout signals, ranked |
| Fundamental Analyst `analyst` | custom | Writes a thesis, catalyst and invalidation level for each signal |
| Risk Officer `risk` | risk | **Veto seat.** PASS with a max size, or VETO naming the broken rule |
| Execution Trader `trader` | entry | Builds order previews only. In PAPER mode, writes fills to the ledger |
| Book Manager `book` | exit | Stops, targets, trims, rebalances. Exits are previews too |
| Fund Reporter `reporter` | reporter | Session receipts, with every number taken from the ledger |

## Data flow

```
macro ──regime_label──▶ pm
quant ──signal_list──▶ analyst ──thesis──▶ risk ──risk_verdict──▶ trader ──order_preview──▶ HUMAN (EXECUTE)
                                                                  book ──exit_preview──▶ HUMAN (EXECUTE)
reporter ──session_receipt──▶ pm
```

Every hop has a timeout and a rule for what happens on failure (see `handoffs` in `desk.json`). If a hop fails, the idea is held or dropped. It is never pushed forward.

## Schedule (ET)

- **Crypto:** scans every 15 min, around the clock. The crypto day rolls at 00:00.
- **Equities:** scans every 30 min, 09:30–16:00. Equity orders are placed only in regular hours.
- **Overnight (20:00–08:00):** research, theses and exit plans.
- **Receipts:** 08:30 pre-market, 16:15 close, 00:00 crypto roll.

## Risk limits (Risk Officer enforces)

- ≤ 5% of NAV per position · ≤ 150% gross exposure · ≤ 20% per sector or coin
- New entries halt at a −3% day or a −10% drawdown from peak
- Liquidity: spread and ADV checks. Event risk: no new entries in the 15 min before a macro release
- Limits change only between sessions, only in `desk.json`, and only by the human

## Go-live gates

1. Risk limits and the drawdown halt are written as rules and unit-tested (**passed**: `fund/risk.py`, tests)
2. The market-data feed supports the scan cadence (**partial**: the TradingView connector returns all 11 symbols in one call and 300 days of daily bars, so end-of-day scans work, but its quotes are delayed 15+ minutes and have no bid/ask. The Robinhood connector returns real-time bid/ask for all 11 symbols in two calls, which covers the intraday cadence and the spread check, but it isn't wired in yet. ThetaData is on the free tier, and stock quotes need a paid plan)
3. The paper ledger marks NAV correctly across equity sessions and the crypto day roll (**passed**: `fund/ledger.py`, tests)
4. 30 days of PAPER receipts with no risk-rule breach (**running**: day 1 was 2026-09-28; see below)
5. A broker or exchange preview tool returns a real quote (**blocked**: no execution connector)
6. The human replies `EXECUTE` to the first fresh live preview (**open**)

## Probe receipts (2026-09-25)

- `GLOBAL_QUOTE SPY` returned 767.18, prev close 767.81, −0.0821%, last trading day 2026-09-24
- `CURRENCY_EXCHANGE_RATE BTC→USD` hit `rate_limit` on the first call. The retry returned 84,266.90 (bid 84,263.99 / ask 84,267.30)

## Paper run (gate 4)

Started **2026-09-28** at $100,000. A Claude Code Routine runs each weekday at 16:40 ET, after the delayed close has settled. Each run does four things:

1. Pulls the last 5 daily bars per symbol from the TradingView connector and merges the completed ones into `ledger/bars.json` with `python -m fund bars-append`. Bars still in progress are refused.
2. Marks the real paper book at those closes.
3. Runs `python -m fund shadow`.
4. Writes `ledger/receipts/<fund-day>-close.json`, runs `sync-board`, and commits to the run branch.

A receipt with `"clean": false` stops the clock, and the routine reports it.

**Two books.** The **real paper book** (`ledger/state.json`) fills only when you approve a preview with `EXECUTE` within 5 minutes. The routine never approves one. The **shadow book** (`ledger/shadow.json`, `fund/shadow.py`) trades every Quant Scanner signal the Risk Officer passes, at the daily close, with no approval step. It shows what the desk would have done, so the 30-day run tests the signals and the risk rules, not just the marking path. Each receipt carries the shadow NAV, return, drawdown, open positions, closed trades, win rate, and the rules that vetoed entries that day.

**Signals** (long only, daily closes; `python -m fund scan` lists them):

| Signal | Rule |
|---|---|
| Momentum | Close above SMA20, SMA20 above SMA50, and a positive 20-day return |
| Breakout | Close above the highest of the prior 20 closes |
| Mean reversion | RSI(2) below 10 while the close is above SMA50 |

**Exits:**
- Stop at close × (1 − 2σ), where σ is the 20-day stdev of daily returns
- Target at close × (1 + 4σ)
- Otherwise out after 5 bars
- No re-entry on the bar of an exit

**Limitations:**
- Shadow fills happen at the close with no spread, so shadow P&L runs about half a spread per side better than real fills would.
- If a daily run is missed, the next run acts on the latest close only. Stops hit on the missed day are taken at the later close.

## Backtest (2026-09-28)

`python backtest/run.py` replays the production shadow book (`Shadow.step` → `risk.check` → `Ledger`) one day at a time over 300 NYSE sessions (2025-07-21 → 2026-09-28) and 299 crypto days (2025-12-03 → 2026-09-27). Signals need 51 closes, so equities trade from 2025-09-30 and crypto from 2026-01-22. Nothing is fitted. Full output is in `backtest/results.json`.

| Run | Return | Max DD | Sharpe | Trades | Win rate | Profit factor |
|---|---|---|---|---|---|---|
| All signals, desk fees only | **+1.75%** | 8.1% | 0.27 | 289 | 48% | 1.09 |
| + 5 bps slippage per side | +0.17% | 8.5% | 0.06 | | | |
| + 10 bps per side | −1.28% | 8.8% | −0.14 | | | |
| Momentum only | +0.57% | 4.8% | | 213 | 49% | 1.04 |
| Breakout only | +3.75% | 3.9% | | 148 | 49% | 1.34 |
| Mean reversion only | +4.68% | 3.7% | | 149 | 52% | 1.46 |
| First half (to 2026-03-15) | −4.27% | 6.3% | −1.56 | | | |
| Second half | +6.35% | 3.6% | 1.43 | | | |
| **SPY buy-and-hold** (from 2025-09-30) | **+14.93%** | | | | | |
| Equal-weight 8 equities, buy-and-hold | +45.41% | | | | | |
| Equal-weight 3 crypto, buy-and-hold (from 2026-01-22) | −6.47% | | | | | |

**Verdict: no edge shown.**
- The combined book trails SPY by about 13 points and is flat to negative once realistic costs are included.
- The result flips sign between the two halves.
- 196 of 289 exits were the 5-bar time stop, so most trades end before the 2σ stop or the 4σ target is reached.
- Average gross exposure was 20%, and the risk rules never vetoed a trade, so this run does not test them.
- Breakout and mean reversion look better on their own, but they were picked after seeing this data. Treat them as hypotheses for the forward shadow run to test, not as findings.

**Biases to keep in mind:**
- About 14 months of one mostly rising regime
- A universe chosen today, which brings survivorship and hindsight bias (AMD rose 285% in the window)
- Daily closes only
- No spread model beyond the slippage runs

## Next up

1. **Event calendar:** the Macro seat supplies upcoming releases so Risk can apply the blackout to shadow entries too (`Shadow.step(..., events=[...])`).
2. **Intraday cadence:** the 15/30-minute scans need a real-time feed with bid/ask (gate 2).
3. **Broker connector** (gate 5) is still blocked on your side.

This desk supports decisions. It is not investment advice, and nothing in it executes trades.

## Dashboard

`python scripts/build_dashboard.py` writes `dashboard.html`: one page showing all four desks (fund limits, SPY gamma map, Kalshi quotes and fill scenarios, sportsbook signals), computed by the desks' own code. CI builds it on every push.

## Live Kalshi scan (read-only)

`python -m kalshi.feed --series KXBTC15M KXETH15M [--log shadow.jsonl]` reads open markets from Kalshi's public API (no key), shows the top of book and the maker pair the desk would rest, and logs it. It only sends GET requests. Markets stay unquoted until TypeSafe verifies their settlement rules. Needs `api.elections.kalshi.com` allowed in the network policy.

## Desks in this repo

Four desks share one TypeSafe judgment layer. Strategy notes and the Heatseeker signal ledger from 456CASH are in `docs/`. Everything runs in paper or shadow mode; nothing places a bet or an order.

| Path | Desk | TypeSafe judgment | Policy in code |
|---|---|---|---|
| `fund/` | Trading (equities + crypto) | `fund/catalyst.py`: material headline risk (Noul) and direction (Choice) | A live answer with p ≥ 0.80 blocks opening size; exits are never blocked |
| `options/` | Options Greeks and GEX map (ported from 456CASH) | none yet | Black-Scholes Greeks, implied vol, dealer-gamma walls, king node and flip from recorded SPY chains in `options/data/chains/` |
| `kalshi/` | Kalshi 15-min BTC/ETH maker | `kalshi/settlement.py`: the rules settle on CF Benchmarks for the stated window (Noul) | Quote a market only after a live yes with p ≥ 0.90; LIVE mode is refused |
| `sportsbook/` | Sportsbook line tracker (ported from 456CASH) | `sportsbook/cause.py`: why the line moved (Choice) | A move counts as sharp only when no news explains it |

`judge/` holds the questions and clients. Without credentials, `judge.from_env()` returns a stub whose answers never count as confident, so every desk behaves as it did before. To go live, set `TYPESAFE_API_KEY`, `TYPESAFE_API_URL` and `TYPESAFE_LIVE=1`, and allow the API host in the network policy. Before that, check `judge.HttpClient` against the [TypeSafe API docs](https://docs.typesafe.ai/api.md); its request format has not been verified.
