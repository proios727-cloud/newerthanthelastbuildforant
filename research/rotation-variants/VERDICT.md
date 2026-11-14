# Verdict: rotation variants (A: 120 sessions, top 3 · B: 60 sessions, top 2)

**Both rejected under the claim fixed in RULE.md.** The live rule stays as it is. A is logged on paper from
2026-12-01 as a comparison only (`rotation_v120.jsonl`, docs/forward-feed.md); that is not adoption, and adopting it
would need a fresh claim written before its results are seen.

- **B fails on every test.** Over the long history it has a deeper drawdown than the live rule for about the same return.
- **A fails narrowly.** It beats the live rule over 2004–2026 in both baskets. On the 2023–26 daily data, though, it
  loses to the live rule at the median rebalance day. The claim required a variant to pass both, so A is rejected.

All figures use total-return data. Daily costs are 1 + 2 bp; long-history CAGRs are net of 3 bp a side.

## Evidence

**Daily stress, `chart/data/etf_tr`, 2023–26, all 21 rebalance days**

| Rule | CAGR median | CAGR worst day | Worst drawdown | Days Calmar ≥ basket | Median CAGR without GLD |
|---|---|---|---|---|---|
| Live 60 / top 3 | **15.5%** | 8.4% | **−14.4%** | 15 / 21 | **10.3%** |
| A 120 / top 3 | 13.1% | 6.6% | −18.4% | 9 / 21 | 6.1% |
| B 60 / top 2 | 15.6% | 9.7% | −16.0% | 17 / 21 | 11.9% |
| Basket | 11.7% | | −12.8% | | |

Cost ladder, median CAGR at 1+2 / 10+10 / 25+25 bp:

| Rule | 1+2 | 10+10 | 25+25 |
|---|---|---|---|
| Live | 15.5% | 13.4% | 10.1% |
| A | 13.1% | 11.7% | 9.2% |
| B | 15.6% | 13.4% | 10.2% |

**Long history, weekly total return**

| Basket | Rule | CAGR, net 3 bp | Worst drawdown | Months ahead of basket |
|---|---|---|---|---|
| 11 funds, Nov 2004 → | Live | 8.7% | −28.0% | 138 / 259 |
| | **A** | **10.0%** | **−15.2%** | 120 / 256 |
| | B | 9.0% | −32.4% | 136 / 259 |
| | Basket | 10.0% | −46.2% | |
| 13 funds, Jul 2018 → | Live | 8.0% | −25.6% | 52 / 96 |
| | **A** | **14.1%** | **−15.2%** | 46 / 93 |
| | B | 6.8% | −32.4% | 51 / 96 |
| | Basket | 12.8% | −16.6% | |

**Stress windows, 11-fund basket, rule vs basket**

| Window | Live | A | B | Basket |
|---|---|---|---|---|
| 2008 crash | −14.3% | **−0.6%** | −0.8% | −33.9% |
| 2011 | +0.7% | +3.2% | −1.6% | +2.8% |
| 2015–16 | −3.2% | −2.2% | −1.3% | −0.0% |
| 2018 Q4 | −7.6% | −8.3% | −8.5% | −7.7% |
| 2020 Covid | **−9.0%** | −13.4% | −8.8% | −8.9% |
| 2022 bear | −6.1% | **+9.2%** | −10.3% | −8.3% |

## Reading it

- **A's long-history edge comes mostly from two regimes.** In 2008 and 2022 the slower ranking stayed in bonds, gold and
  energy while the market fell. In the fast 2020 crash it was hurt more than the live rule, because it was slower to leave
  equities.
- **A depends on gold.** In 2023–26, dropping GLD cuts its median CAGR to 6.1%, against 10.3% for the live rule.
- **The two datasets disagree on A.** One is 22 years of weekly bars and the other is 3 years of daily bars. The daily
  window is short and covers one regime, which is why the claim needed both. A 13-fund weekly result also starts 3 months
  later than the live rule's, so it skips 2018 Q4.
- **B is the live rule with more concentration and no benefit.** Its daily median matches the live rule's, but over 22
  years its drawdown is deeper and its regime results are mixed.

## What would change the verdict

- **For A:** a daily stress median at least level with the live rule once more daily history is available (pre-2023 daily
  bars are premium), or the forward test showing the live rule trailing in a slow bear market.
- **Watch item:** the live rule trails A by 1.3 points a year over 2004–26. If you'd rather act on the long-history result
  than on the claim fixed in advance, A is the variant to add, as information only. That is your call, not part of this
  verdict.
- **For B:** nothing in this grid.

## Next step

- **Reject both.** No forward log, no dashboard line.
- **Tests run:** 2 variants × 2 baskets, plus 2 daily stress runs, as planned. No other settings were tried.
