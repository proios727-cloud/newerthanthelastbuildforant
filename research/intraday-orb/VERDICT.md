# Verdict: SPY/QQQ opening-range breakout and gap fade

**Reject. Both rules fail.** Do not alert on them or trade them.

- **On 2026 15-minute bars, none of the 36 variants makes money after costs.** The opening-range breakout loses even with
  zero costs in walk-forward, on both SPY and QQQ.
- **On 2023–26 hourly bars, the one positive walk-forward result fails the bar.** SPY's 60-minute breakout made +9.2% at
  1+1 bp, but with t = 0.97 (2.0 needed). It turns negative at 2+2 bp and loses on QQQ (−15.2%).
- **All the positive years are 2025,** the tariff-shock year. In 2023, 2024 and 2026 almost every variant lost money.
  That makes it a one-regime result.

Rule, data and grid were fixed before any result was seen: `RULE.md`. Code: `chart/intraday.py`, tests:
`tests/test_intraday.py`. Run it with `python3 -m chart intraday chart/data/intraday/15m` (or `.../1h`). Full tables:
`results_15m.md`, `results_1h.md`.

## Evidence: walk-forward, out-of-sample (variant re-picked each month from earlier sessions only)

| Data | Symbol | Strategy | OOS trades | Mean / trade @1+1 | t | Total @0 | @1+1 | @2+2 | @5+5 | Buy & hold |
|---|---|---|---|---|---|---|---|---|---|---|
| 15m, Mar–Oct 2026 | SPY | ORB | 83 | −8.5 bp | −2.00 | −3.7% | −6.9% | −9.9% | −18.5% | +10.2%¹ |
| | SPY | Gap fade | 40 | −6.1 bp | −0.82 | −0.9% | −2.4% | −4.0% | −8.5% | |
| | QQQ | ORB | 96 | −10.7 bp | −1.55 | −6.4% | −9.9% | −13.3% | −22.8% | +11.4%¹ |
| | QQQ | Gap fade | 38 | −8.4 bp | −0.66 | −1.8% | −3.3% | −4.7% | −9.0% | |
| 1h, Mar 2023–Oct 2026 | SPY | ORB | 238 | +3.9 bp | +0.97 | +20.1% | +9.2% | −0.7% | −25.4% | +96.6%¹ |
| | SPY | Gap fade | 76 | +0.1 bp | +0.01 | +2.9% | −0.2% | −3.2% | −11.7% | |
| | QQQ | ORB | 583 | −2.7 bp | −1.10 | +7.1% | −15.2% | −32.8% | −66.7% | +157.0%¹ |
| | QQQ | Gap fade | 246 | −4.1 bp | −0.93 | −0.7% | −10.0% | −18.5% | −39.3% | |

¹ Buy and hold over the whole file, for context only. An intraday rule is flat every night, so its real benchmark is 0%.

**Against the claim in `RULE.md`:**

| Test | Needed | Best case (SPY 1h ORB) | Result |
|---|---|---|---|
| Out-of-sample return at 1+1 bp | > 0 | +9.2% | pass |
| Survives 2+2 bp | > 0 | −0.7% | **fail** |
| t-stat of the mean trade | ≥ 2 | 0.97 | **fail** |
| Out-of-sample trades | ≥ 100 | 238 | pass |
| Same parameters work on SPY and QQQ, on 15m and 1h | all four positive | QQQ 1h −15.2%; SPY 15m −6.9% | **fail** |

**Multiple testing:** 48 tests were run. In-sample, 7 of the 24 hourly variants were positive at 1+1 bp, and none had
t > 0.8. That is what chance alone would produce.

## Why it fails
- **Costs are as large as the edge.** The average gross move captured is 0–5 bp a trade, and a realistic round trip is
  2–4 bp. SPY and QQQ are the most efficiently priced instruments in the world, and a public, well-known rule on 15- or
  60-minute bars has no information advantage.
- **Breakouts pay only when volatility is high.** 2025 (tariff shock) was the one year breakouts and gap fades worked. A
  volatility-regime filter is the obvious next hypothesis. But it was suggested by these results, so it must be
  registered as a new rule and tested on data this study has not seen. Otherwise it is curve fitting.

## What would change the verdict
- A pre-registered rule (for example, a breakout only when the prior day's range or VIX is in its top third) that passes
  every test in `RULE.md` on data not used here: 1-minute or 5-minute bars from 2018–2022, from a paid or free source
  (`docs/intraday-data.md`).
- Forward paper results. Nothing goes live from a backtest.

## Data caveats
- 15-minute history from the free feed starts on 2026-01-02 (209 sessions), so the 15-minute walk-forward covers only
  8 months.
- Hourly bars are coarse. The hourly ORB fills at 10:30 at the earliest, and stops and targets are checked on hourly
  highs and lows. Because the stop wins ties, results are biased slightly against the rule, not for it.
- The last bar's close is the last trade before 16:00, not the closing auction. In 8 of 1,950 symbol-day comparisons it differs from the
  official close by more than 15 bp (index-rebalance and tariff days). That changes the exit price on those days only.
