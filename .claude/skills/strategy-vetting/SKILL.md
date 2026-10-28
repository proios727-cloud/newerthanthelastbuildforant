---
name: strategy-vetting
description: Vet a trading-strategy idea, backtest result or "this beats the market" claim with the repo's chart engine before anyone acts on it. It runs walk-forward on total-return data, every rebalance day, a cost ladder, two decades of weekly history broken out by crash, and a multiple-testing check, then writes a one-page verdict (candidate / risk filter / reject). Use when the user proposes a strategy, shares a backtest, asks whether a signal or rotation "works", or wants something added to the desk or the forward log. Research only; it never places orders.
---

# Strategy vetting

Pipeline: **define → total-return data → walk-forward → robustness → long history → verdict → forward log**.
Every step below exists because skipping it once produced a wrong conclusion in this repo (see `docs/rotation-sleeve.md`).

## 0. Define the rule before looking at results

Write `research/<idea>/RULE.md`:
- **Rule:** the exact entry and exit, rebalance timing (decided at close i, filled at the open of i+1), universe and
  sizing.
- **Benchmark:** what an investor would hold instead (equal-weight basket, the asset itself, SPY).
- **Claim:** what has to be true for this to be worth doing: more return, or the same return with a shallower drawdown.
- **Parameter grid,** fixed now. Widening it after seeing results is curve fitting.

## 1. Use total-return data

- **Use the total-return folders,** `chart/data/tr/` and `chart/data/etf_tr/` (regenerate them with
  `python3 -m chart dividends SRC DST` after a data update).
- **Check the price-only result against them.** Price-only bars flatter anything that holds low-yield assets or cash. Here
  that was about 1.9 points a year for the ETF basket and a third of the rotation rule's 2023–26 edge.
- **Validate first:** `python3 -m chart validate <csvs>`. Any adjustment goes in `chart/adjust.py` and
  `chart/data/SOURCES.md`, never by hand-editing a CSV.

## 2. Walk forward, never fit in-sample

- **Single assets:** `python3 -m chart walkforward <csv> --strategy <name> --rolling` (parameters re-picked before every
  block from earlier bars only).
- **A folder:** `python3 -m chart scan <folder> --all`. Read both verdicts:
  - **Return candidate:** beats holding on return and Sharpe, wins at least half the blocks, and has 3+ trades.
  - **Risk filter:** a drawdown at least a third shallower than holding, a Calmar ratio at least holding's, invested
    at least 30% of the time.

## 3. Robustness

- **Every rebalance day:** `python3 -m chart stress <folder> --lookback N --hold H --top K`. Report the median and the worst
  day, not the best. A result that swings from −0.4% to +32% across rebalance days is luck.
- **Cost ladder:** in the same output, 1+2, 10+10 and 25+25 bp. Say where the edge disappears.
- **Remove the key asset:** the `without` rows. An edge that needs one fund is a bet on that fund.
- **Live calendar:** for a calendar rule, use `python3 -m chart forward rotation-replay` (decide on the first session of the
  month, from data available that day).

## 4. Long history, by regime

- **Rotation rules:** `python3 -m chart longrun` (weekly total return, 2004–2026, broken out by stress window: 2008, 2011,
  2015–16, 2018 Q4, 2020, 2022).
- **Single-asset strategies:** `python3 -m chart longrun <weekly folder> --strategies`. Weekly folders:
  `chart/data/weekly/` (ETFs) and `chart/data/weekly_desk/` (desk stocks).
- **A result that only holds in 2023–26 is a one-regime result.** Say which crashes the rule helped in, and which it didn't.

## 5. Multiple testing

Count the tests run (assets × strategies × variants). If 1 in 20 or fewer passes, assume the passes are chance unless
they hold up in step 4 **and** in a market or period that wasn't searched. Two "candidates" out of 78 is noise.

## 6. Verdict (one page, `research/<idea>/VERDICT.md`)

- **Verdict:** `return candidate`, `risk filter` (say what it costs in return), or `reject`.
- **Evidence:** a table of total-return CAGR, worst drawdown, Calmar and months ahead against the benchmark, for the
  walk-forward run, the stress median and worst day, the long history, and each stress window.
- **What would change the verdict,** and the cost level at which it breaks.
- **Next step:** reject, or add it to the forward paper log. Nothing goes live from a backtest.

## 7. Forward paper log

The forward log is the only evidence that can't be overfit after the fact:
- `python3 -m chart forward record` logs the scan.
- `forward rotation-record [--trend N]` logs a rotation rule.
- The daily `chart-forward` workflow runs both on the `shadow-data` branch and needs the `ALPHAVANTAGE_API_KEY` secret.
- Live use still goes through analyst → Risk Officer → trader → `EXECUTE`.

## Never

- Report the best rebalance day, the best parameter set or an in-sample result as the expected outcome.
- Compare a total-return strategy against a price-only benchmark, or the other way round.
- Call a result an edge before costs, or before the long-history check.
- Edit data by hand, or place, preview or approve an order from this skill.
