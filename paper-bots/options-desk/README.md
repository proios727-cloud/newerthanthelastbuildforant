# Independent SPY / QQQ long-call paper desk

**Engineering prototype; no verified profitable options backtest yet.** This desk has its own input files, policy, bankroll and report outputs. It does not share cash or positions with crypto or sports. It cannot send orders, obtain credentials, or collect data. Fixtures are synthetic accounting tests, not market success.

Run with Python 3.11+ (numeric/replay core uses the standard library; New York timezone data is additionally required). Windows typically needs the small `tzdata` package:

```powershell
cd paper-bots/options-desk
py -3 -m pip install -r requirements-paper.txt
py -3 -m unittest -v
py -3 data_check.py
py -3 replay.py audit --mode weekly --strategy breakout20 --synthetic --bankroll 1000 --output results/weekly.synthetic.json
py -3 replay.py audit --mode 0dte --strategy breakout20 --synthetic --bankroll 1000 --output results/0dte.synthetic.json
```

Start the commands from your cloned repository root. `data_check.py` inventories the repository's old chain snapshots and explains their limitations; it does not certify a strategy. Change `--bankroll 1000` to your desired virtual starting cash. No deposit or API key is needed for these engineering checks. Historical dataset choices and the actual-data audit are documented in [DATA-REQUIREMENTS.md](DATA-REQUIREMENTS.md).

From the `options-desk` directory on Linux/macOS with system IANA timezone data:

```sh
cd options-desk
python -m unittest -v
python replay.py audit --mode weekly --strategy breakout20 --synthetic --bankroll 1000 --output results/weekly.synthetic.json --trades-csv results/weekly.synthetic.trades.csv
python replay.py audit --mode 0dte --strategy breakout20 --synthetic --bankroll 1000 --output results/0dte.synthetic.json
python replay.py audit --mode weekly --strategy orb --barsfile inputs/spy-bars.csv --quotesfile inputs/spy-calls.csv --bankroll 1000 --fee .65 --target .25 --output results/weekly.actual-replay.json
```

The last command requires **real, aligned underlying one-minute bars and exact-contract option bid/ask quotes**; no production data is bundled. Quotes alone cannot establish ORB/VWAP entries, premium stops, time exits or path-dependent drawdown. Missing inputs block an actual replay rather than manufacture a zero-trade validation.

## Hypotheses and timing

Three separately selectable hypotheses (`--strategy`):

| Hypothesis | Trigger after a closed minute |
|---|---|
| `orb` | First crossing above high of first 15 opening minutes, plus session VWAP / EMA9>EMA21 / relative volume ≥1.2 |
| `vwap-reclaim` | Previous close below previous session VWAP, current close above current VWAP, EMA9>EMA21 and relative volume ≥1.2 |
| `breakout20` | Close above prior 20 minute highs, plus session VWAP / EMA9>EMA21 / relative volume ≥1.2 |

Session VWAP uses typical price × volume. Relative volume compares the latest minute with the preceding 20 minutes. All strategies need at least 21 complete opening-session bars from 09:30 ET; no partial opening window is accepted. Bars are processed when received, never before their close. Entry uses an actual quote source timestamp **strictly later** than the signal's observable availability; it never fills at the signal candle or a quote already seen before that candle became available. Signal age limit is 120 seconds, quote source-to-receipt age limit five seconds. Underlying bars arriving >five seconds after their close are stale and cannot create a fresh entry; `--max-bar-delay-seconds` makes an explicit replay latency assumption configurable.

| Rule | Weekly | 0DTE |
|---|---|---|
| Calendar DTE at quote, in New York | 1–7 | 0 |
| Entry window | 09:45–15:00 ET | 09:45–13:00 ET |
| Time stop | 90 minutes | 20 minutes |
| Target variants | Actual bid reaches 25% or 50% above entry ask | Same |
| Premium stop | Actual bid ≤80% of entry ask | Same |
| Session cutoff | First executable observed quote at/after 15:30 ET | Same |

Only SPY/QQQ long calls with exact OCC-style symbol, root, strike, expiry, 100-share multiplier and independent provenance are accepted. No puts, short options, leverage or overnight exits. Standard entry delta profile uses **externally supplied** delta .45–.65; compare a predeclared low-delta profile with `--delta-min .15 --delta-max .35`. This is a hypothesis comparison, not permission to select the winning profile retrospectively. Missing delta is rejected; delta and IV are never estimated to manufacture option premium prices. Delta may change outside the entry range after purchase without blocking an otherwise valid exit.

Default strike proximity is within 2% of the last observable underlying close. Configure `--near-atm-fraction` or explicitly omit that filter with `--no-near-atm-gate`; delta still must be supplied. Maximum entry premium spread is 10% of ask; risk-reducing exits with valid actual bid and sufficient bid size remain possible when the spread widens. Default $0.65 per contract **per side** is a configurable fee hypothesis, not a verified account fee; include actual fees/other charges before evaluating results.

Each entry's full premium plus entry fee must fit 5% of initial paper bankroll, with a 10% aggregate ceiling. Exactly one position can be open across the correlated SPY/QQQ group. Positions use whole contracts. These limits mean a $1,000 account cannot buy even one call costing more than roughly $0.4935/share under the default fee; cheap fixtures do not establish liquid real opportunities at that price. Real input quotes require explicit ask/bid sizes; these must cover the simulated order. Synthetic fixtures can omit sizes only for isolated engineering tests. No quote-depth or queue guarantees are made.

## Input schema (CSV or JSON)

JSON is an array of row objects or `{"rows": [...]}`. CSV uses the same field names. Numeric strings are accepted. Use explicit timezone offsets or `Z`, preferably UTC. ET conversion determines the trading session and DTE.

| Underlying bar field | Meaning |
|---|---|
| `timestamp` | Start of closed one-minute bar, explicit timezone; minute aligned |
| `receive_time` | Time the completed bar was observable; must be ≥ start +60 seconds |
| `root` | `SPY` or `QQQ` |
| `open`, `high`, `low`, `close`, `volume` | Positive consistent OHLC; nonnegative volume |
| `source` | Identifiable actual dataset/provider; fixtures use `SYNTHETIC_FIXTURE` |
| `session_close` (optional) | Explicit date/time of regular or early session close |

| Option quote field | Meaning |
|---|---|
| `timestamp`, `source_timestamp` | Same independently sourced option quote event time |
| `receive_time` | When quote became observable; event cannot be future or >5 seconds old |
| `root`, `symbol` | Exact root and call symbol, e.g. `SPY261016C00600000`; spaces allowed |
| `strike`, `expiration`, `option_type` | Exact match to symbol; ISO date; `call` only |
| `dte`, `multiplier` | Explicit calendar DTE and `100` |
| `delta` | Externally provided call delta, never derived by this desk |
| `bid`, `ask` | Actual nonnegative bid / positive ask, uncrossed and within spread gate |
| `bid_size`, `ask_size` | Required for real inputs; available whole-contract quantities at the quote |
| `source` | Identifiable actual dataset/provider |
| `session_close` (optional) | Same session metadata as bars; inconsistent values rejected |

`report_complete` is false without both input types/valid bars or with unresolved positions, and `net_total_return` is null for incomplete reports. Realized partial PnL is never presented as a resolved overall return.

Input schemas and example files are in `schemas/` and `fixtures/`. Real replays require separate source/receipt metadata; substituting download time for historical quote time must not be represented as observed historical latency.

## Exit, equity and incompleteness

Exits use the actual bid and deduct both entry and exit fees. IV changes or underlying movement cannot create PnL without observed option prices. A zero bid without explicit positive bid size is not an executable worthless exit. Missing/stale/wide/crossed quotes or insufficient bid size cannot fabricate a fill. Positions without a verified same-session exit remain **UNRESOLVED**, retain their premium at risk, and make final equity/drawdown unavailable. They cannot be liquidated with next-day quotes.

No exchange holiday calendar is implemented. By default provided sessions are assumed regular 16:00 ET sessions; valid early-close days require `session_close` metadata. For a declared 13:00 close, forced exit cutoff becomes 12:30 and the entry window stops no later than 12:00. Every cutoff still requires a valid observed executable quote before the exchange closes; missing quotes remain unresolved. Fully verified holidays/early closes are a launch blocker for any future automation.

Reports contain provenance, DTE policy, actual paper fills, net realized PnL, cash, fees, full premium at risk, sampled equity/drawdown and explicit skip/unresolved reasons. Synthetic reports are prominently flagged as having **no performance evidence**. File/event sorting is deterministic; duplicate bars/quotes and missing bar chronology are rejected. Report generation is a batch replay, not a restart-safe live trading service.
