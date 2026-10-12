# Paper quantitative core

Python standard library only. Run from this directory:

```sh
python -m unittest -v
python demo.py
```

`demo.synthetic.json` contains labelled hypothetical data, not current picks. The engine does not connect to any exchange, sportsbook, or broker and cannot submit orders.

- `fair_value_gate`: requires an externally calibrated conservative probability bound, executable bid/ask, explicit per-contract fee and slippage estimates, quote/source timestamps, and freshness/spread/edge limits. Rejects malformed and stale inputs. An accepted gate is eligibility for further paper review, not proof of profit.
- `no_vig`: normalizes decimal odds only when the caller explicitly declares a complete, mutually exclusive outcome set. Completeness must be independently checked by the adapter (including ties/draws where applicable). Normalized bookmaker probabilities remain a reference, not an independent edge.
- `empirical_joint_probability`: counts joint success in aligned simulation scenarios. The caller must preserve the same scenario ordering; equal lengths alone do not establish alignment. Supports correlation rather than multiplying individual probabilities.
- `quarter_kelly`: uses the conservative probability and effective cost including estimated fees/slippage. Returns whole-contract sizing capped by per-position and aggregate cash-risk limits. Bankroll and existing exposure must be refreshed by the calling desk; allocation is a proposal only.
- `kalshi_depth_ask`: consumes `orderbook_fp` dollar bids, derives YES asks from NO bids (and vice versa), and returns exact Decimal depth-weighted cost. Rejects insufficient depth. It does not estimate fees or guarantee future fills.
- `PaperLedger`: SQLite entry/partial exit accounting deducts allocated entry fees and exit fees from realized PnL. Transactions roll back failed fills. Marked open-position gains are not reported as realized profit. Simulated prices/fees must come from execution validation in the calling desk.

The demo uses an in-memory ledger. For persistent paper records instantiate `PaperLedger("paper.sqlite")`. No settlement/rules engine, live adapters, calibrated prediction model, or validated profitable strategy is included; all must be supplied and validated before any live use. Contract settlement of $0 or $1 can be recorded as a full exit only after independent settlement verification.

## Isolated bankroll status

`monitor.py` keeps an immutable initial paper bankroll and desk identity in each SQLite database. Reusing a crypto database for sports (or changing its initial bankroll) is rejected. Atomic entries cannot overdraw cash, which is reconstructed from persisted fills. Crypto quantities are spot asset units with finite prices above $1 supported; use `side="long"` (`yes` is retained as a long alias). Sports quantities are binary contracts with $0–$1 prices. Crypto shorts and leverage are not implemented.

```sh
python quant/monitor.py --desk crypto --bankroll 1000
python quant/monitor.py --desk sports --bankroll 1000
python quant/monitor.py --desk crypto --watch 5
python quant/monitor.py --desk sports --watch 5
```

Run these from the project root. Defaults are separate `desks/crypto/paper.sqlite` and `desks/sports/paper.sqlite`. Existing accounts read their persisted initial bankroll when `--bankroll` is omitted; new accounts require it. `--db` overrides the local path, and `--output` writes a JSON snapshot. Separate processes/files are required per desk; the monitor never aggregates bankrolls.

Marking open positions requires `--marks` with local JSON shaped like `{"1":{"bid":"61000","exit_fee":"0.10","timestamp":1791762000}}`; keys are position IDs, fees are total estimated exit fees for the entire remaining position, and timestamps are Unix seconds. Missing, stale, future or malformed marks leave equity, unrealized PnL and drawdown unavailable. Sampled peak/drawdown use only valid equity snapshots, not continuous market observation. `--watch` only refreshes accounting and rereads supplied local marks: it does not fetch markets, scores, news or prices. `--demo` creates explicitly synthetic fills in an empty account only; fixture gains are accounting tests, not trading performance.
