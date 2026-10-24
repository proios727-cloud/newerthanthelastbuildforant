# S&P 500 Evidence-First Research Run — Status Report
**As of:** 2026-10-05 22:15 UTC · **Universe:** S&P 500 (504 lines) → 98 passed screen → 15 researched
**Result: NO RANKING PUBLISHED.** 0 of 15 candidates clear all seven hard gates in RUBRIC.md.
Under the stop conditions, an incomplete verification blocks the ranking. This is research, not investment advice.

## Why no name qualifies
| Gate | Result |
|---|---|
| 4 · No going-concern / auditor resignation | **UNVERIFIABLE for all 15.** The Robinhood SEC feed serves no filing text and EDGAR is blocked, so no audit opinion or 8-K Item 4.01 could be read. |
| 5 · Company-confirmed catalyst ≤180d | Fails for 9 names. Most Q3 dates are not yet announced by the company; only third-party estimates exist. |
| 1 · Verifier PASS | 8 names fail: unsupported thesis, contradicted premise, or Tier-3-only evidence. |
| 6 · Bear independence | **PASS for all 15** on the transcript audit (verify/GATE6_AUDIT.md). The bear agents' self-reported timestamps were unreliable and are not used. |

## Gate matrix
| Ticker | Verify | G4 | G5 catalyst | Blocking reason |
|---|---|---|---|---|
| **SNDK** | PASS w/ caveats | UNVERIF. | PASS (10-29) | Gate 4 only |
| **PGR** | PASS w/ caveats | UNVERIF. | PASS (10-14) | Gate 4 only |
| ALL | PASS w/ caveats | UNVERIF. | FAIL | Q3 date not announced |
| WDC | PASS | UNVERIF. | FAIL | Q3 date conflict |
| APP | PASS | UNVERIF. | FAIL | Q3 date conflict |
| EXPE | PASS w/ caveats | UNVERIF. | FAIL | Q3 date conflict |
| LULU | PASS w/ caveats | UNVERIF. | FAIL | Q3 date estimate only; unread 9/14 8-K |
| BKNG | FAIL | UNVERIF. | FAIL | P/E inflated by a $1.12B non-operating swing; no TTM EV/EBIT |
| GEV | FAIL | UNVERIF. | FAIL | EV/EBIT ~141x; $4.0B one-time gain; cash flow comes from deposits |
| CF | FAIL | UNVERIF. | PASS | "Cheap gas" premise unsourced and contradicted |
| AMP | FAIL | UNVERIF. | PASS | Mispricing thesis unsupported |
| ERIE | FAIL | UNVERIF. | FAIL | Claimed "discount" is a +6.6% premium |
| ZTS | FAIL | UNVERIF. | PASS | Thesis contradicted by guidance cut; distorted peer median |
| EME | FAIL | UNVERIF. | FAIL | No Tier-1 data; peer-backlog premise unsupported |
| PODD | FAIL | UNVERIF. | PASS | Three unread Sept 8-Ks; guidance conflict |

## Nearest qualifiers (not a recommendation)
**SNDK (Sandisk).**
- Why it may be mispriced: FY26 revenue was $20.25B (+204% vs FY24) and FCF $11.49B; debt is fully repaid; forward P/E ~8x [Tier 1, 10-K FY26].
- What breaks it: the memory price cycle turns. Receivables rose 327% against revenue +175% [Tier 1]. Asia is ~70% of revenue.
- Next catalyst: FQ1-27 results on 2026-10-29 [Tier 2, company PR 9/29].
- Uncertain or unavailable: Form 4 buy/sell direction, gate 4.

**PGR (Progressive).**
- Why it may be mispriced: P/E ~10.5 on an ROE of ~38% [Tier 1 inputs, own calculation].
- What breaks it: margins have peaked. The August combined ratio was 89.3 vs 83.1, and monthly net income fell 22% [Tier 2, 8-K 9/18].
- Next catalyst: Sept/Q3 results on 2026-10-14 [Tier 2, IR page].
- Uncertain or unavailable: YTD combined ratio, gate 4.

## Dissent
- **SNDK:** the bear case holds that an ~8x P/E at peak memory margins is the classic cyclical trap. The receivables build supports that view.
- **PGR:** a premium P/B of 3.56x against peers at 1.79x leaves little room if the combined ratio keeps deteriorating.
- **ALL:** earnings are helped by a $634M reserve release while catastrophe losses run high ($1.72B in Q2).

## What would unblock a ranking
1. **EDGAR access in a new session** (the network change did not reach this container). It clears gate 4 and lifts Tier-2 excerpts to Tier 1.
2. **Company Q3 date announcements**, most expected within ~2 weeks. These clear gate 5 for ALL, WDC, APP, EXPE and LULU.
3. **Your decision:** whether to treat gate 4 as "UNVERIFIABLE → caveat" instead of a fail. That would admit SNDK and PGR, as 2 names below the 5-name floor.

## Data-quality issues found
- Bear agents wrote unreliable completion timestamps.
- Several "VERIFIED_FACT" labels sat on Tier-2/3 sources or on absent values; the verifiers downgraded them.
- Arithmetic errors were caught: BKNG EV units, EXPE net-cash sign, ERIE premium/discount, SNDK Asia share.

Files: `work/` (screen, regime memo, bull/bear/fill/verify per ticker). Schema: `equity_candidate.schema.json`. Rubric: `RUBRIC.md`.
