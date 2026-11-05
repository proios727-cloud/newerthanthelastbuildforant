# Verdict: desk-level trend overlay (SPY above its 10-month average, else cash)

**Risk filter, as crash insurance with a steep premium.**
- **Over 2000–2026 it passed on every setting** for SPY and QQQ. It cut SPY's worst drawdown from −55% to −21% for about
  0.3 points a year less return.
- **All of that came from the 2000–02 and 2008 bear markets.** Since 2009 it cost SPY about 6 points a year (9.4%
  against 15.3%) and fails the Calmar test.
- **Not adopted as a standing rule.** It is now logged as a paper regime flag. Rule and grid were fixed before running:
  `RULE.md`. Code: `chart/overlay.py`, `python3 -m chart overlay <csv>`.

## Evidence (weekly total return, decided at month-end, filled at the next open, 1+2 bp, cash at 0%)

**SPY, Oct 2000 → Oct 2026**

| Setting | CAGR | Worst drawdown | Calmar | Invested | Exits | Risk filter |
|---|---|---|---|---|---|---|
| Hold SPY | **8.6%** | −54.6% | 0.16 | 100% | — | — |
| 6-month average | 7.2% | −21.6% | 0.33 | 72% | 28 | pass |
| 8-month | 7.8% | −21.6% | 0.36 | 73% | 23 | pass |
| **10-month** | 8.3% | **−20.7%** | **0.40** | 76% | 17 | pass |
| 12-month | 7.9% | −20.5% | 0.39 | 76% | 14 | pass |

**Robustness, 10-month:**
- **Decision week:** first, second, third or last week of the month all pass. CAGR ranges from 6.1% to 8.5%, and the worst
  drawdown from −21% to −34%.
- **Costs:** at 10+10 bp, 8.0%.
- **Cash yield:** with real T-bill returns (BIL, total return, from Jul 2007; `chart/data/cash/BIL.csv`), time out of
  the market earns 1.4% a year on average. That adds 0.3 points a year to SPY (8.6% vs 8.3% at 0% cash over 2007–2026),
  0.3 to QQQ and 0.5 to IWM. No verdict changes. Holding SPY made 10.6% over the same span.

**Other funds, 10-month:**
- **QQQ:** 9.1% against 9.4%, worst drawdown −28% against −76%. Passes at every setting and every decision week.
- **IWM:** 6.0% against 8.3%, worst drawdown −30% against −58%. Passes only when deciding in the last week of the month;
  in weeks 1–3 it fails, with CAGR as low as 1.3% and a −63% drawdown. Fragile.
- **Sector SPDRs, not searched:** passes on 6 of 9 (XLE, XLF, XLI, XLK, XLU, XLY) and fails on XLB, XLP and XLV.

**By period, SPY:**

| | Overlay | Hold |
|---|---|---|
| Oct 2000 → Mar 2009 | **+6.0%/yr**, drawdown −10% | −4.4%/yr, drawdown −55% |
| Apr 2009 → Oct 2026 | +9.4%/yr, drawdown −21% | **+15.3%/yr**, drawdown −32% |

**Stress windows, SPY (overlay against hold, total return over the window):**

| Window | Overlay | Hold | Read |
|---|---|---|---|
| 2000–02 dot-com | −7.5% | −33.5% | helped |
| 2008 crash | −5.2% | −45.7% | helped |
| 2011 debt scare | −10.5% | −3.2% | hurt: sold low, bought back high |
| 2015–16 slump | −7.6% | −4.8% | hurt |
| 2018 Q4 | −17.0% | −13.4% | hurt |
| 2020 Covid crash | −10.3% | −14.3% | slightly helped |
| 2022 bear | −15.6% | −15.6% | same return, shallower path (−16% vs −22%) |

## Multiple testing

- **12 primary tests** (4 lengths × SPY, QQQ, IWM): all 12 pass at the default decision week.
- **Out-of-sample sectors:** 6 of 9 pass.
- That consistency is not chance. The result is also a well-known one, the 10-month rule, and it holds here for the same
  reason it holds in the literature: slow trend rules sidestep long bear markets.

## What would change the verdict

- **A long bear market** (2000- or 2008-style) is where it pays, by 25–40 points per episode.
- **V-shaped selloffs** (2011, 2015–16, 2018 Q4) are where it loses, by 3–7 points per episode.
- **The cost in a bull market** is about 6 points a year on SPY, as 2009–2026 shows.
- **Cash yield:** measured with BIL since 2007, it is worth 0.3–0.5 points a year. At today's rates (about 4–5%) it would
  narrow the gap more in the months spent out of the market.

## Next step

- **Don't put it on the book.** It would have cost about 6 points a year since 2009.
- **Track it as a regime flag.** `python3 -m chart overlay chart/data/tr/SPY.csv --status` (last decision 2026-09-30:
  hold, SPY 5.4% above its 10-month average) is logged daily by the forward job and shown in the monthly brief, so a
  2008-style break is visible the month it happens.
- **Risk can decide later** whether a flag change should trigger a review of gross exposure. That is a policy choice, not
  a backtest result.
