# Decision: what to do with the ETF rotation rule

**Rule:** rank the 13 research ETFs (11 Select Sector SPDRs, TLT, GLD) by 60-session return, then hold the top 3 that are up,
in equal weight. It decides at the close of the first session of each month and fills at the next open
(`python3 -m chart forward rotation-record`).

**Status: research, paper only.** Nothing here places an order. Any live use still goes through the desk's analyst →
Risk Officer → trader → `EXECUTE` path.

## Bottom line (updated Oct 2026, after the long-history test)

The 2023–2026 "edge" doesn't hold up. Two problems:

1. **The daily tests ignored dividends.** The daily files are price-only. The equal-weight basket yields about 1.9% a year
   (TLT 4.3%, XLE 3.1%, XLU 2.9%), while the rule mostly holds lower-yield momentum funds. On total-return daily bars
   (`chart/data/etf_tr/`), the 2023–26 live-calendar replay edge shrinks from +1.8 to +1.2 points a year: +16.9% against
   +15.8%. The stress-test median is +15.4% against +11.7%. About a third of the edge was missing dividends; the rest
   holds on this window.
2. **Over two decades the rule earns less than the basket.** From 2005 to 2026 (weekly total-return bars) it made 9.0% a
   year against 10.0% for holding the basket, and about 7.0% after 10+10 bp costs. From 2018 to 2026 with all 13 funds it
   made 8.3% against 12.8%.

What it does do is **cut deep drawdowns**. Its worst month-end drawdown was −28% against the basket's −46%, and nearly all
of that came from 2008 (−14% against −34%). In 2018, 2020 and 2015–16 it fell as much as the basket or more. It helped
again in 2022 (−6% against −8% on 11 funds, −6% against −12% on 13).

**Recommendation: keep it as a paper-only research log, not a sleeve.**
- **Don't add the ETFs to the desk universe for now** (this withdraws option B below). The forward log runs without
  that change.
- **Log the defensive variant next to it.** It goes to cash when the basket is below its 200-session average. Over the
  long history it came closest to the basket's return (9.5% against 10.0%) and cut the worst drawdown from −46% to −18%.
  From 2018 to 2026 it did no better than the basket (−15% against −17%). The daily job now logs both.
- **Revisit after 12 months of forward results,** or sooner if a bear market arrives, since that is the only case where
  either version has shown a benefit.

## Long history: weekly total-return bars, 2004–2026

Source: Alpha Vantage weekly adjusted bars, free tier (see `chart/data/SOURCES.md`). On weekly bars the rule becomes
12-week momentum, decided on the first weekly bar of each month and filled at the next weekly open (`python3 -m chart
longrun`). Over 2024–2026 that weekly version matches the daily rule's return (+15.3% a year against +15.35%).

**11 funds (no XLRE or XLC), Mar 2005 → Oct 2026**

| Variant | CAGR | After 10+10 bp | Worst drawdown | Months ahead |
|---|---|---|---|---|
| Equal-weight basket | **10.0%** | — | −46.2% | — |
| Adopted rule | 9.0% | 7.0% | −28.0% | 138/259 |
| Hysteresis (keep while in top 4) | 8.9% | 7.1% | −27.8% | 138/259 |
| Trend filter, about 150 days | 8.3% | 6.4% | **−14.1%** | 131/259 |
| Trend filter, about 200 days | 9.5% | 7.6% | −18.1% | 135/259 |

**13 funds, Oct 2018 → Oct 2026:** basket 12.8% (−16.6% worst drawdown). Adopted rule 8.3% (−25.6%). 200-day trend filter
11.6% (−15.1%).

**Stress windows, 11 funds (rule against basket):**

| Window | Rule | Basket |
|---|---|---|
| 2008 crash | −14.3% | −33.9% |
| 2011 debt scare | +0.7% | +2.8% |
| 2015–16 slump | −3.2% | −0.0% |
| 2018 Q4 | −7.6% | −7.7% |
| 2020 Covid crash | −9.0% | −8.9% |
| 2022 bear | −6.1% | −8.3% |

**Volatility-weighted top 3** (inverse 12-week volatility, a scratch test with no code added) trimmed the worst drawdown by
1–4 points but cost 0.3–0.8 points a year in every case. Not adopted.

## The original 2023–2026 daily evidence (price only; total-return figures in the bottom line)

| Test | Rule | Equal-weight basket |
|---|---|---|
| Stress test, all 21 rebalance days, 1+2 bp | median +13.8%/yr (worst +8.0%) | +9.7%/yr |
| Same, 10+10 bp | median +12.0%/yr | +9.6%/yr |
| Live-calendar replay, Jan 2024 → Oct 2026, before costs | +15.2%/yr | +13.5%/yr |
| Live-calendar replay: worst month-end drawdown | −7.5% | −5.7% |

Hysteresis (keep a fund while it ranks in the top 4 or 5) and a basket trend filter were tested on this window too. Neither
earned a change there (table on the scorecard). Turnover is about 1.2 of 3 holdings a month.

## Options, as first framed

| | A. Separate sleeve with its own limits | B. Inside the existing desk caps |
|---|---|---|
| Size | e.g. 20% of NAV | 3 × 5% = 15% of NAV |
| Needs | new limits in `fund/risk.py` and `desk.json` | the 13 ETFs added to the `desk.json` universe |
| Status | **off the table**: there is no return edge to scale | **withdrawn for now**: the long history doesn't support it |

## What the daily job produces

- **On the first session of each month,** for both the adopted rule (`rotation.jsonl`) and the defensive variant
  (`rotation_trend200.jsonl`):
  - the decision is logged before the fill;
  - `rotation-tickets` writes paper tickets (5% of `starting_nav` per fund, limits ±0.5%, changed funds only);
  - `rotation-brief` writes a one-page `BRIEF.md` with the picks, momentum ranks, tickets, the variant's call, the forward
    record and any blockers.
- **Every run:** `chart doctor` fails the run if the API key is missing or bars are more than 3 weekdays old.
- **Everything lands on the `shadow-data` branch.** None of it is sent anywhere.
