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
| `chart/intraday.py` | Intraday session backtester (opening-range breakout, gap fade, walk-forward). Data: `chart/data/intraday/`, sources: `docs/intraday-data.md`. **Verdict: reject** (`research/intraday-orb/VERDICT.md`). |
| `chart/breakout.py` | 4-hour trend breakout with an ATR stop, vs buy and hold. Data: `chart/data/crypto/4h/` (BTC, ETH). **Verdict: reject** (`research/crypto-breakout/VERDICT.md`). Daily 2017–2023 test: halves drawdowns but fails the pre-registered bar on trade count (`research/crypto-breakout-daily/VERDICT.md`). |
| `tests/` | unit tests: `python3 -m unittest -v` |

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
2. The market-data feed supports the scan cadence (**blocked**: the free Alpha Vantage key allows 25 requests/day and 1/sec)
3. The paper ledger marks NAV correctly across equity sessions and the crypto day roll (**passed**: `fund/ledger.py`, tests)
4. 30 days of PAPER receipts with no risk-rule breach (**open**)
5. A broker or exchange preview tool returns a real quote (**blocked**: no execution connector)
6. The human replies `EXECUTE` to the first fresh live preview (**open**)

## Probe receipts (2026-09-25)

- `GLOBAL_QUOTE SPY` returned 767.18, prev close 767.81, −0.0821%, last trading day 2026-09-24
- `CURRENCY_EXCHANGE_RATE BTC→USD` hit `rate_limit` on the first call. The retry returned 84,266.90 (bid 84,263.99 / ask 84,267.30)

## Next up

1. **Scheduler:** a Claude Code Routine or cron job that runs each seat on its trigger: mark, scan, preview, then `sync-board`.
2. **Event calendar:** the Macro seat supplies upcoming releases so Risk can apply the blackout (`risk.check(..., events=[...])`).
3. **Start the 30-day PAPER clock** (gate 4) with `python3 -m fund init`, and commit `ledger/` so the receipts persist.
4. **Feed upgrade** (gate 2) and **broker connector** (gate 5) remain blocked on your side.

This desk supports decisions. It is not investment advice, and nothing in it executes trades.

## Dashboard

`python scripts/build_dashboard.py` writes `dashboard.html`: one page showing all four desks (fund limits, SPY gamma map, Kalshi quotes and fill scenarios, sportsbook signals), computed by the desks' own code. CI builds it on every push.

## GEX desk (read-only, research only)

Flow: capture, chain, snapshot, dashboard. Nothing here places, previews, cancels or exercises an order.

1. **Capture.** A Claude session with the Robinhood connector makes READ-ONLY calls: `get_equity_quotes` for `[SYM]` (spot and `venue_last_trade_time`); `get_option_instruments` with `chain_symbol=SYM`, `expiration_dates=<next 0-7 DTE dates>`, `state=active`, following the paging `cursor` until exhausted; then `get_option_quotes` for those instrument ids (20 per call or fewer is safest). Pages run upward by strike, about 100 rows each, and the cursor is base64 of `p=<strike>`. So to jump close to the money, pass `cursor` = base64 of `p=<a strike a few dollars below spot - 3%>`, for example `cD03MTkuMDAwMA==` (`p=719.0000`) for SPY near 732. Then quote only the strikes within ±3% of spot, for each type and each expiry. A full 0–3 DTE SPY capture made this way is 1 equity quote, 6 instrument pages and 6 quote calls, which gives 120 contracts. `options/data/chains/SPY-2026-11-17T2059.json` is one: Nov 18, 19 and 20, calls and puts, strikes 723 to 742. The converter needs all three: equity quote (spot), instruments (id, `chain_symbol`, `strike_price`, `type`, `expiration_date`) and option quotes (`instrument_id`, `implied_volatility`, `open_interest`, `volume`, `gamma`, `vega`, `delta`, `bid_price`, `ask_price`). Contracts with IV below 1% are dropped and counted.
2. **Chain.** `python scripts/rh_chain_from_transcript.py [TRANSCRIPT.jsonl] [OUTDIR] [--since ISO]` joins those results from the session transcript (default: the newest one) into `options/data/chains/<SYM>-<asof>.json` and prints `{saved, symbols, contracts}`. Chains use `type`/`oi`; older files with `option_type`/`open_interest` still load.
3. **Snapshot.** `python scripts/gex_snapshot.py CHAIN.json [--out DIR]` writes `DIR/gex.json` (net GEX, flip, king, walls, regime, strikes within 5% of spot), appends to `DIR/gex_log.jsonl` and prints a 3-line summary.
4. **Dashboard.** `python scripts/build_dashboard.py --gex CHAIN.json` shows that chain in the options panel instead of the sample.

### Nightly GEX capture

Flow: plan, calls, `gex_nightly.sh`. (1) `python scripts/gex_plan.py SPOT [--expiries 3] [--width 10] [--today YYYY-MM-DD]` prints the expiries (next N weekdays from the New York date; exchange holidays are not modeled), the 20 strikes nearest spot (`round(SPOT)-9 .. round(SPOT)+10`), the paging `cursor` (base64 of `p=<strike_lo-4>`; SPOT 732.38 gives strikes 723-742 and `cD03MTkuMDAwMA==`) and the steps: 1 equity quote, then per expiry 2 instrument pages (call, put) and 2 quote calls. (2) The Claude session makes those READ-ONLY connector calls and notes the ISO time it began. (3) `SINCE=<that time> scripts/gex_nightly.sh [SYMBOL=SPY]` (env `BASE`, `GEX_DIR` default `/tmp/gex-nightly`, `DRY_RUN=1`) converts the transcript results from fresh worktrees of `BASE` and `shadow-data`, requires a chain for the symbol with at least 40 contracts (otherwise exit 1, nothing staged; exit 2 if `SINCE` is missing), copies it to `gex-desk/chains/`, runs the snapshot into `gex-desk/` (`gex.json`, growing `gex_log.jsonl`), builds `$GEX_DIR/dashboard.html`, commits as `chart-forward`, pushes (3 tries, `pull --rebase`) and prints one JSON summary line. Research only; no orders.

## Live Kalshi scan (read-only)

`python -m kalshi.feed --series KXBTC15M KXETH15M [--log shadow.jsonl]` reads open markets from Kalshi's public API (no key), shows the top of book and the maker pair the desk would rest, and logs it. It only sends GET requests. Markets stay unquoted until TypeSafe verifies their settlement rules. Needs `api.elections.kalshi.com` allowed in the network policy.

## Kalshi desk scan (read-only, paper)

`python -m kalshi.desk scan --series KXBTC15M KXETH15M [--out DIR] [--min-edge-cents N] [--offline FIXTURE.json]` reads each open market's order book (public GET only, no key) and computes, from the book alone, the YES and NO asks, the both-sides lock cost, its fee-net edge (`100 − cost − taker fees` on both legs, cents per contract, via `kalshi.taker_fee_cents`), spread and top-of-book depth. Rows are ranked by edge; a positive fee-net edge is flagged `LOCK`. Most runs find none, and the summary says so. It writes `scan.json`, `kalshi_desk.json` (a PAPER board config: `python scripts/build_board.py DIR/kalshi_desk.json`) and appends a line to `paper_log.jsonl`. `python scripts/build_dashboard.py --kalshi-scan DIR/scan.json` shows the scan in the dashboard's Kalshi panel. No orders, previews or LIVE mode.

### Nightly Kalshi scan

`scripts/kalshi_nightly.sh` (env: `BASE`, `KALSHI_DIR` default `/tmp/kalshi-nightly`, `SERIES`, `DRY_RUN=1`) runs the scan from fresh worktrees of `BASE` and `shadow-data`, writes `kalshi-desk/scan.json`, `kalshi_desk.json`, the growing `paper_log.jsonl` and a dated `kalshi-desk/scans/YYYY-MM-DD.json` (New York date) into `shadow-data`, builds `$KALSHI_DIR/dashboard.html` with the Kalshi panel, commits as `chart-forward` and pushes (3 tries, `pull --rebase`), then prints one JSON summary line. A failed scan exits non-zero and pushes nothing; `DRY_RUN=1` stages without committing. Public GET only, paper only.

## Desks in this repo

Four desks share one TypeSafe judgment layer. Strategy notes and the Heatseeker signal ledger from 456CASH are in `docs/`. Everything runs in paper or shadow mode; nothing places a bet or an order.

| Path | Desk | TypeSafe judgment | Policy in code |
|---|---|---|---|
| `fund/` | Trading (equities + crypto) | `fund/catalyst.py`: material headline risk (Noul) and direction (Choice) | A live answer with p ≥ 0.80 blocks opening size; exits are never blocked |
| `options/` | Options Greeks and GEX map (ported from 456CASH) | none yet | Black-Scholes Greeks, implied vol, dealer-gamma walls, king node and flip from recorded SPY chains in `options/data/chains/` |
| `kalshi/` | Kalshi 15-min BTC/ETH maker | `kalshi/settlement.py`: the rules settle on CF Benchmarks for the stated window (Noul) | Quote a market only after a live yes with p ≥ 0.90; LIVE mode is refused |
| `sportsbook/` | Sportsbook line tracker (ported from 456CASH) | `sportsbook/cause.py`: why the line moved (Choice) | A move counts as sharp only when no news explains it |

`judge/` holds the questions and clients. Without credentials, `judge.from_env()` returns a stub whose answers never count as confident, so every desk behaves as it did before. To go live, set `TYPESAFE_API_KEY`, `TYPESAFE_API_URL` and `TYPESAFE_LIVE=1`, and allow the API host in the network policy. Before that, check `judge.HttpClient` against the [TypeSafe API docs](https://docs.typesafe.ai/api.md); its request format has not been verified.

## GM toxicity desk (`gmdesk/`)

Glosten-Milgrom × Avellaneda-Stoikov market-making research on Kalshi 15-minute BTC/ETH markets, built
from the `skills/gm-toxicity-mm` skill. Read-only: it records public trades, calibrates a VPIN toxicity
signal out of sample, replays both quoters with fees, and runs a live shadow. **It places no orders.**

```bash
python3 -m gmdesk.record backfill --series KXETH15M --markets 120   # stage 1 (data/ is git-ignored)
python3 -m gmdesk.analyze --series KXETH15M                         # stage 2 gate
python3 -m gmdesk.replay  --series KXETH15M                         # stage 3 gate
python3 -m gmdesk.shadow run --series KXETH15M --minutes 240        # stage 4 (live, no orders)
python3 -m gmdesk.shadow report data/gm/shadow_KXETH15M.jsonl --replay data/gm/replay_KXETH15M.json
python3 -m gmdesk.board_data                                        # board Real-tape data
```

## Router doctor (`skills/router-doctor/`)

Read-only home Wi-Fi diagnosis, plus an agent workflow for tuning the router one approved change at a time. It's the safe version of the viral "Claude Code fixed my router" post. Run it on a machine on your home network; a cloud session can't reach your router.

```bash
python3 skills/router-doctor/scripts/router_doctor.py diagnose --out router_report.json  # verdict + channel congestion
python3 skills/router-doctor/scripts/router_doctor.py diagnose --router eero              # eero: advice as eero app steps
python3 skills/router-doctor/scripts/router_doctor.py watch --minutes 10                  # catch on-and-off drops
python3 skills/router-doctor/scripts/router_doctor.py keychain-cmd --user admin          # store router password in the OS keychain
```

**Windows, no install:** double-click `skills/router-doctor/windows/Check-WiFi.bat`. It watches the router and the internet for a few minutes, tracks the Wi-Fi band and signal, then saves a verdict report (`WiFi-Check-*.txt` plus a CSV) to the Desktop.

## Charting engine and RE Studio

| Path | What it is |
|---|---|
| `chart/` | Indicator engine (SMA, EMA, Wilder RMA, RSI, MACD, Bollinger, ATR) and a bar backtester that fills on the next bar's open, so it never looks ahead. Pure stdlib. Built from published definitions; see `chart/SPEC.md`. |
| `chart/sweep.py` | Parameter sweep, single-split walk-forward, and **rolling walk-forward**: settings are re-picked before every 10-bar test block using only earlier bars, and the blocks are stitched into one continuous out-of-sample run against buy-and-hold. |
| `chart/strategies.py` | Trend-filtered RSI dips, MACD with a trend filter, Bollinger reversion, Donchian breakout. |
| `chart/rotate.py` | Basket momentum rotation (hold the strongest symbol, or cash), scored against an equal-weight basket. |
| `chart/scan.py` | Quant-seat bridge: rolling walk-forward of all 6 strategies on each `chart/data/<SYMBOL>.csv` in the desk universe, plus the basket rotation, emitted as a `signal_list` with a candidate flag and the reasons it was rejected. Research only. |
| `chart/data/` | Daily bars for the desk's 8 equities, 2023-10-02 → 2026-10-26 (770 sessions each), mostly from ThetaData. Sources, the NVDA split adjustment and the two recorded bad-print fixes are in `chart/data/SOURCES.md`. |
| `chart/data/etf/` | Research universe: 11 Select Sector SPDRs plus TLT and GLD, same span. Splits, dropped bad rows and vendor gaps are in `chart/data/SOURCES.md`. |
| `chart/dividends.py`, `chart/data/tr/`, `chart/data/etf_tr/` | Total-return copies of the daily files (dividends back-adjusted; `python3 -m chart dividends SRC DST`). Use them for research verdicts; the raw folders stay the source for live prices. |
| `chart/data/weekly/`, `chart/longrun.py` | The same 13 ETFs as weekly total-return bars back to 1999–2018 (Alpha Vantage weekly adjusted, free tier). `python3 -m chart longrun` runs the rotation rule and its variants over 2004–2026 and breaks results out by stress window (2008, 2011, 2015–16, 2018, 2020, 2022). |
| `chart/report.py`, `chart/report_page.html` | `python3 -m chart report Stocks=chart/data ETFs=chart/data/etf --rotation chart/data/etf --longrun chart/data/weekly --forward <shadow-data dir> --overlay chart/data/weekly_desk/SPY.csv chart/data/tr/SPY.csv --out scorecard.html` writes a self-contained scorecard: verdicts, stats, each strategy's out-of-sample curve against holding, the rotation rule's forward log, stress tests and long history, and the SPY trend-overlay verdict with today's flag. `scripts/build_dashboard.py` shows the flag and the latest rotation picks on the desk dashboard. |
| `chart/robust.py` | `python3 -m chart stress chart/data/etf [--buffer N] [--trend N]` stress-tests a rotation rule from every rebalance day, at several cost levels, and with key funds removed; `--buffer` adds hysteresis, `--trend` a basket trend filter. |
| `chart/doctor.py` | `python3 -m chart doctor` is the forward job's preflight. It checks the Alpha Vantage key, how stale each data folder is and whether any file lags, and gives the next rotation decision date. It exits 1 on any problem. |
| `chart/overlay.py` | `python3 -m chart overlay <csv> [--months 10] [--status]`: a monthly trend overlay on one fund (hold above its N-month average, else cash), with stress windows and the scan's risk-filter verdict. |
| `docs/research-log.md` | Every research finding in order, with the corrections; the README keeps only the current conclusions. |
| `chart/validate.py`, `chart/adjust.py` | Data checks (order, bad prints, one-day jumps, cross-vendor closes) and split/correction handling. |
| `chart/forward.py`, `chart/update.py` | Forward paper test: log each day's signals before the open, score them as bars arrive. Monthly rotation decisions also get paper tickets and a one-page `BRIEF.md` (`chart forward rotation-brief`). `.github/workflows/chart-forward.yml` runs it every weekday on the `shadow-data` branch (needs the `ALPHAVANTAGE_API_KEY` secret). |
| `tests/test_chart.py` | Oracle cases from the spec, including a test that checks the tests can fail and a check that the test slice can't influence parameter choice. |
| `docs/re-studio.md` | Reference for the AI reverse-engineering stack (REA, Ghidra, jadx, Frida…): install, engines, workflows, prompts, legal guardrails. |
| `.claude/skills/re-studio/` | Project skill: scope gate → evidence → SPEC.md → clean-room build → oracle loop. |
| `.claude/skills/strategy-vetting/` | Project skill: the test protocol any strategy idea goes through before the forward log: fixed rule → total-return data → walk-forward → every rebalance day and cost ladder → 20-year weekly history by crash → multiple-testing check → one-page verdict. |

```bash
python3 -m chart backtest prices.csv --strategy sma_cross --fast 10 --slow 30 --fee-bps 1
python3 -m chart backtest prices.csv --strategy rsi_revert --rsi-n 14 --lo 30 --hi 70
python3 -m chart walkforward chart/data/SPY.csv --strategy sma_cross --train 0.7
python3 -m chart walkforward chart/data/SPY.csv --strategy bollinger_revert --rolling
python3 -m chart scan --out ledger/signals.json      # 1-year train, monthly blocks, 1 bp fee + 2 bp slippage
python3 -m chart validate chart/data/*.csv
python3 -m chart forward record && python3 -m chart forward report
python3 -m chart longrun                              # rotation rule 2004-2026, weekly total return, by regime
python3 -m chart doctor                               # forward-job preflight
```

### Current conclusions (Oct 2026)

All on total-return data, after costs, checked over 20+ years of weekly bars. The full history, including claims later
corrected, is in `docs/research-log.md`. New ideas go through `.claude/skills/strategy-vetting/`.

| Question | Answer | Evidence |
|---|---|---|
| Does any strategy beat holding? | **No.** None of the 48 weekly tests on the desk stocks; 2 of 78 on the ETFs (XLRE mean reversion), about what chance produces. | `chart longrun --strategies` |
| ETF momentum rotation (60-day, top 3, monthly) | **No return edge** over two decades (9.0% vs 10.0%/yr). It halved the worst drawdown, mostly in 2008. Paper log only, with a 200-day trend variant alongside. | `docs/rotation-sleeve.md` |
| Trend filters (SMA cross, Donchian, MACD) | **Risk filters at a cost:** they cut drawdowns on about a third of assets and always give up 1–14 points a year. Specific 2023–26 pairings mostly don't carry over. | `chart longrun --strategies` |
| Desk-level overlay: SPY above its 10-month average | **Crash insurance:** −21% worst drawdown vs −55% since 2000, but about 6 points a year behind holding since 2009. Logged as a regime flag, not on the book. | `research/trend-overlay/VERDICT.md` |
| Price-only vs total return | Price-only data understated the basket by about 1.9%/yr and overstated the rotation edge by a third. Research verdicts now use `chart/data/tr/` and `chart/data/etf_tr/`. | `chart/dividends.py` |

The forward paper log (`chart-forward` workflow, needs the `ALPHAVANTAGE_API_KEY` secret) is the evidence that counts next.

The CSV needs `date, open, high, low, close[, volume]` in ascending order. Backtest results are research output, not investment advice.

## Skill: product-pain-miner

`.claude/skills/product-pain-miner/` turns public complaints about everyday items into ranked redesign concepts. Each category is a JSON dataset (`data/<category>.json`, every entry sourced), and the ranked report (`reports/<category>.md`) is generated from it. Ask Claude to "run product-pain-miner on bathroom" to add a category, or to "refresh kitchen" to update one.

```bash
python3 .claude/skills/product-pain-miner/scripts/pain_index.py .claude/skills/product-pain-miner/data/kitchen.json \
  --out .claude/skills/product-pain-miner/reports/kitchen.md
```

The script refuses datasets without sources or with invalid scores, and the tests fail if a report is out of date.
