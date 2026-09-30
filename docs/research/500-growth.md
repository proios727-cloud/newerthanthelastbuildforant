# Growing a $500 account: what the evidence supports
*Research date: 2026-09-29. Scope: a US retail user on Robinhood, building a paper-first agent desk (Claude Opus 5.5 orchestrates, Jev can only veto, deterministic code sets risk limits, and a human types EXECUTE). Nothing here was traded. The Robinhood connector was used read-only, for quotes and chains only.*

---

## 0. Bottom line (read this first)

1. **Nothing active plausibly beats the baselines at $500 after costs, measured in dollars.** Even an optimistic edge on $500 is worth about $10 to $60 a year before variance. Risk-free T-bills and high-yield savings (HYSA) pay about **$21/yr** right now, and paying down a 22% credit card is worth **$110/yr, guaranteed**. At this size, what an active stream really gives you is a data set and an infrastructure test. It does not give you income.
2. **If you carry any high-interest debt, that is the #1 use of the $500.** Next is a cash buffer at 4.2–4.5% APY. Next is fractional SPY/VTI.
3. **Among the three streams, only one is worth paper-trading toward real money: defined-risk SPY put credit spreads, 1–2 points wide.** They are the only one with a documented structural premium behind them (the volatility risk premium). Even so, the public evidence says defined-risk index premium selling has earned **roughly T-bill-like returns over 20 years** (CNDR: about 1.6%/yr CAGR, 2006–2026). The short-put leg carries the edge. The long protective leg gives much of it back.
4. **Kalshi 15-minute BTC/ETH maker quoting is the weakest stream. Treat it as a measurement project.** The best public study I found (3,200 windows) shows these markets are huge (about 2.1M contracts per window) and efficient. It also shows adverse selection that grows as your model disagrees more with the market. The claimed profitable backtests come from vendors and assume every resting order fills.
5. **Sportsbook CLV betting is real skill. At a $500 bankroll it is mostly a limit-and-variance trap.** Soft US books limit +EV accounts within about 2–5 weeks. A 2% CLV edge on $5 stakes is about $100/yr of expectation, buried under about ±$160/yr of noise. The one reliable +EV item is sign-up and promo offers, which are one-off. In Florida, Hard Rock Bet is the only legal online book, so there is no line shopping.

---

## 1. Baselines a $500 account has to beat

| Baseline | Current number | $ per year on $500 | Risk | Source |
|---|---|---|---|---|
| 3-month T-bill | **4.24%** (2026-09-25) | ~$21 | none (state-tax-exempt) | Alpha Vantage TREASURY_YIELD, daily |
| Top HYSA | **4.20–4.50% APY** (after last week's Fed hike) | ~$21–22 | FDIC | Bankrate, Fool, CollegeInvestor, Sept 2026 |
| Paying down a credit card | **22.15% APR** avg on accounts accruing interest (Fed G.19, Q2 2026) | **~$110, guaranteed** | none | Fed G.19 via LendingTree/Fool |
| SPY/VTI fractional DCA | SPY price CAGR **~9.1%** Dec 2005 to Sep 2026 (126.02 to 765.61), ~11% with dividends | ~$45–55 expected | -50% drawdowns (2008), -34% (2020) | TradingView AMEX:SPY monthly |
| Cboe PUT index (SPX cash-secured put writing) | **~7.6% CAGR** 2005-12 to 2026-09 (805.66 to 3669.31) | n/a (needs ~$75k/contract) | worst monthly-close drawdown ~-30% (2008) | TradingView CBOE:PUT |
| Cboe BXM (buy-write) | **~6.4% CAGR** same window | n/a | | CBOE:BXM |
| **Cboe CNDR (20-delta / 5-delta iron condor + T-bills)** | **~1.6% CAGR** same window (595.62 to 822.47) | ≈ T-bill return | max DD ~19% | CBOE:CNDR |

*Note: the CBOE:PUT feed has a bad tick (low 150.76 in Mar-2009). I used closes only.*

**What CNDR means for us.** CNDR sells roughly 15–20-delta monthly SPX puts and calls, buys 5-delta wings, and holds the collateral in T-bills. Its return over 20 years is about equal to the T-bill return alone. **Even before retail slippage, the defined-risk short-premium overlay added roughly nothing.** PUT, the unhedged short put, captured about 6 points a year over bills. So the edge sits in the short put. Buying the wing gives most of it back, because far-OTM puts are the most overpriced options and you are now buying them. This matches the ORATS/SteadyOptions test (§3.2) and Israelov/AQR's finding that protective puts are "pathetic protection".

**Is any active stream plausibly ahead of these at $500? Not in dollars.** The best case is a put-spread book that earns the VRP. Put against about $400 of risk capital, that gives a realistic expectation of +0 to +10%/yr on capital at risk, or $0–$40/yr, with a real chance of -$80 to -$400 in a bad month. Compare $21 risk-free, or $110 if there is card debt. The honest reason to go live is to validate the desk at small size so it can be scaled later with outside savings.

---

## 2. Stream-by-stream assessment

### 2.1 Options: short put vs put credit spread (Robinhood)

**Account and permissions**
- Spreads need **Robinhood Level 3**, which is margin-account only. It is not available in cash or retirement accounts. A Robinhood "Instant" account is a margin account type. Credit spreads are collateralized at (width × 100) minus the credit, so no borrowing is needed. FINRA's $2,000 minimum applies to *borrowing* on margin, and Robinhood can impose its own eligibility rules. **Confirm Level 3 approval in the app before assuming the paper plan can go live.**
- **The PDT rule is gone.** The SEC approved the FINRA Rule 4210 amendments on 2026-04-15 (effective 2026-06-04), removing the PDT designation and the $25k minimum. Brokers can phase this in until 2027-10-20, so check Robinhood's current status. It doesn't affect this plan anyway: 30-DTE spreads aren't day trades.
- **Cash-secured puts are impossible at $500.** The SPY 750 put ties up $75,000. Our $22k–$73k figure is right.
- **Early-assignment risk on SPY (American style).** If the short leg goes deep ITM, especially near an ex-dividend date, you can be assigned 100 SPY shares (~$76k) in a $500 account. The long leg caps economic loss, but you face a forced liquidation and possibly a margin call. **XSP is European and cash-settled, so this risk disappears.** That is its main real advantage for a small account.

**Live quotes (Robinhood read-only, SPY 765.6, expiry 2026-10-30 = 31 DTE, prices as of 2026-09-28 close)**

| Structure | Short Δ | Credit (mid / natural) | Max loss | Max loss as % of $500 | Credit/width |
|---|---|---|---|---|---|
| SPY 750/745 put spread | -0.29 / -0.25 | $98.5 / $95 | ~$402–405 | **81%** | 19.7% |
| SPY 745/740 | -0.25 / -0.21 | $81.5 | ~$418 | 84% | 16% |
| **SPY 750/748** | -0.29 / -0.27 | $41.5 / $38 | ~$159–162 | 32% | 21% |
| **SPY 750/749** | -0.29 / -0.28 | $20.5 / $17 | ~$80–83 | **16%** | 20% |
| XSP 750/745 | -0.27 / -0.23 | $89 / **$70** | $411–430 | 82–86% | 18% |

**Cost findings**
- **SPY legs are $0.03–0.04 wide. XSP legs are $0.19 wide**, with open interest of 440 vs 19,192. Crossing the XSP market costs about $19 per 5-wide spread on entry alone, around 20% of the credit. Robinhood also charges a **$0.50/contract index-option fee** plus exchange fees; one snippet (BrokerChooser, a third-party review site) dates the $0.50 to Oct 15, 2026, so verify the current schedule. XSP's Section 1256 60/40 tax treatment is worth only a few dollars on a $500 book. **Verdict: SPY for cost. Use XSP only if you work limit orders at mid and value the removal of assignment risk. Paper-test both fills.**
- Robinhood charges no commission on SPY. Regulatory and OCC fees run a few cents per contract. On the 1-wide spread, the mid-vs-natural gap ($3.50 of $20.50) is **~17% of the credit**, so fills must happen at or near mid.

**Sizing reality.** At $500, a 5-wide SPY spread puts about 80% of the account in one trade. That is a ruin bet. The practical live unit is **one 1-wide ($80 risk) or at most one 2-wide ($160 risk) SPY put spread at a time.**

### 2.2 Kalshi 15-minute BTC/ETH up/down (maker spread capture)

**Fees**
- Taker fee: `ceil(0.07 × C × P × (1−P))`, which is 1.75¢/contract at 50¢.
- Maker fee: `0.0175 × C × P × (1−P)`, charged only on series listed with a maker multiplier. Most standard series have maker = 0.
- The fee rounds up to the cent, which punishes 1-contract orders.
- **Check the live series fee fields for KXBTC15M / KXETH15M through the API. Do not assume "fee-free maker".**
- Volume/Liquidity Incentive Program rewards are capped at $0.005/contract.
- Robinhood's event-contract route charges $0.02/contract ($0.01 Robinhood + $0.01 Kalshi).

**Market quality.** The best public study is `hudsonjoshuaclark/kalshi-bot`: ~100 hours, 3,200 windows, 60 rule sets.
- About **2.1M contracts per BTC 15-minute window**, with a 0.7–1.8¢ spread.
- Taking liquidity **loses at every horizon** (−0.4 to −1.6¢/contract).
- The fair-value model has **negative skill vs the market price** (Brier −1.3% to −4.8%). Its correlation with market prices is 0.976–0.990.
- Trading on bigger model–market disagreement loses *more* (−2.4¢ at 0.02 threshold, −3.8¢ at 0.10), which is the signature of adverse selection.
- The only "profit" found was directional drift. Its correlation with block P&L was 0.98.

**The maker "lock" (YES bid + NO bid < $1)**
- The math: if both legs fill at, say, 48¢ + 49¢, you lock 3¢ per pair (on a maker-fee-free series).
- The problem: fills are not independent. Your YES bid fills when the price is falling, which is exactly when the NO side stops needing your liquidity. You end up one-sided on the losing leg.
- Turbine (a vendor blog) reports a **−15.7 percentage-point adverse-selection gap** (76.0% win when filled vs 91.7% when not), about 4× the spread saved.
- Turbine's other page claims **1,600% ROI / 99% win rate** for KXBTC15M market making, but explicitly **assumes all post-only orders fill with no queue**. **Flag: vendor marketing, not evidence.**
- Professional market makers under Kalshi's confidential Market Maker Agreement get rebates, position limits and cancel protections that retail doesn't. Retail is quoting against them.

**At $500.** Capital isn't the constraint (1¢ ticks, ~$0.50 per contract). The constraint is edge. With realistic both-fill rates, expectancy per contract is likely **≤ 0 after one-sided losses**. Legality is fine in most states for crypto contracts. Sports contracts are unavailable in MD, NJ and NV and face cease-and-desist orders in AZ, IL, MT and OH. Florida currently allows Kalshi.

### 2.3 Sportsbook line-movement / closing line value (CLV)

**Evidence**
- Beating the no-vig closing line, ideally Pinnacle's, is the accepted proxy for long-run edge. Unabated recommends measuring CLV against a **vig-free** closing line. Something like 1–3% CLV is "excellent".
- **Caveats (Unabated, 2026):** CLV means little in props, early-season college sports and the WNBA, because those markets aren't efficient enough for the close to be a true price.
- A Wharton study (Beggy 2023) found full Kelly bankrupted 100% of simulated scenarios. Half-Kelly with a 10% cap performed best, *given* a real edge.

**Limits (community data, r/sportsbook, r/algobetting via SportBot/BetSuite summaries)**
- At $200–500 stakes: BetMGM limited in ~2 weeks, DraftKings ~3, FanDuel ~4, Caesars ~2 months.
- Books that tolerate winners (Pinnacle-style) are offshore or grey. **Don't use those.**
- Reported caps after limiting: $5–50/bet at DraftKings.
- The one broadly agreed reliable +EV is **sign-up and promo offers**. The best-documented r/sportsbook log made ~$7.3k over 2 years mostly from promos.

**At $500**
- Flat 1% ($5) stakes × 1,000 bets × 2% edge ≈ **+$100/yr EV, with a standard deviation of about $160**. You can't tell edge from luck inside a year, and limits arrive first.
- **Florida:** Hard Rock Bet is the only legal online sportsbook (through 2051 under the compact), so there is no multi-book line shopping. Kalshi or Robinhood sports event contracts are legal in FL for now and can be used for the *measurement* version (CLV vs the Pinnacle close) without risking sportsbook limits.

---

## 3. Put credit spreads: what the published tests say

### 3.1 Parameter evidence

| Parameter | Best-supported choice | Evidence / caveats |
|---|---|---|
| Underlying | **SPY** (liquidity), XSP (European, no assignment), IWM (lower price, $1 strikes) | Index > single names: single names carry earnings gaps and less VRP net of jump risk. SPY legs 3–4¢ wide vs XSP 19¢ (live). |
| DTE | **30–45 at entry; exit by ~21 DTE** | tastylive "manage at 21 DTE or 50%"; DaysToExpiry comparison says 30–45 is a sensible default. |
| Short delta | **16–30Δ** | Higher delta = more premium, more tail. Option Alpha used 30Δ/10Δ. Spintwig: lower delta = better Sharpe, higher delta = more total return. |
| Long delta / width | As **far away as affordable**. At $500, width is dictated by risk: 1–2 points. | ORATS: risk-adjusted results get *worse* the closer the long put is to the short put. At $500 we're forced into the worst case (1-wide). |
| Profit take | **50% of credit** | tastylive standard. Option Alpha: adding 50% PT + stop + early close cut the max loss from $12k to $2k (on a $100k account) and raised Sharpe 0.62 → 0.77, at lower total return. |
| Stop | **2× credit** (loss = 1× credit) or none (defined risk) | 25% stops cut too early (Option Alpha). Stops execute worst in selloffs, when bid–ask spreads blow out. |
| Entry filter | IV rank high / VIX above realized | tastylive uses IVR 50–100. Spintwig's proprietary "s1" signal claims improvement (**flag: proprietary, can't verify**). |

### 3.2 Published results (after costs where stated)

- **Bondarenko for Cboe (1986–2018):** PUT 9.54%/yr vs S&P 9.80%, volatility 9.95% vs 14.93%, Sharpe 0.65 vs 0.49. Average VIX 19.3 vs realized 15.1, so the VRP is real. *This is cash-secured puts, not spreads.*
- **ORATS via SteadyOptions (2007–2021, 30 DTE SPY, held to expiry):**
  - 40Δ short put: 6.85%/yr, max DD 36.5%, Sharpe 0.75, 81.7% winners.
  - **40/30Δ put spread at 1× notional: 1.1%/yr**, max DD 11.1%, 76% winners.
  - At 4× notional: 4.5%/yr, **max DD 43.6%**, Sharpe 0.46.
  - Spreads have *worse* risk-adjusted returns than short puts.
- **Cboe CNDR (TradingView, 2006–2026):** ~1.6%/yr total, including T-bill interest. The spread overlay is ≈ 0.
- **Option Alpha (5 years, ~2016–2021, 30Δ/10Δ SPY, 30 DTE):** 93% win rate held to expiry. **No commissions, bull-market window. Treat as optimistic.**
- **SJ Options, tastytrade rules on SPX 2005–2016 (1/3-width credit, 45 DTE, IVR > 50, 50% take, 2× stop):** 61% winners, **negative total return at every allocation** (−7% at 5%, −93% at 50%). **Flag: an options-system seller whose pitch is "tastytrade doesn't work", so it has an incentive. Methodology not published.**
- **Galitics/Shak Mahosa via StockWireX (5 years incl. 2022 and April 2025):** spreads beat naked puts per dollar of capital. A 2-point win-rate shift erased the naked-put edge. **Flag: secondary summary, small sample.**
- **tastylive (2017):** short put spreads at 15/45/75 DTE all had ≥ 88% win rates. Win rate ≠ expectancy.

### 3.3 Break-even math on today's quotes

- **Held to expiry, SPY 750/749:** win +$20, loss up to −$80 (natural fill: +$17 / −$83). **Break-even win rate ≈ 80–83%.** Risk-neutral P(short leg OTM at expiry) ≈ 71–76% by delta and Robinhood's "chance of profit short" (0.76), so you need the VRP to add roughly +5–8 points of win rate.
- **Managed (50% take ≈ +$10, 2× stop ≈ −$20 plus slippage):** break-even win rate ≈ 67–70%. The SJ/tastytrade backtest's 61% would lose.
- **Expected edge if the VRP holds** (index data: short-put excess over bills of ~5–6%/yr on notional, much less for spreads): about **+$1–3 per 1-wide spread per month**, or $10–35/yr for one continuously rolled contract. That is statistically invisible over 30 days.

---

## 4. How builders structure Claude + Jev + code desks

**Patterns (from reddy7356/jev-trader, the buberlo redesign, the drillan survey gist and awesome-jev)**
- **"Code calculates state → Jev interprets → code applies policy → execution places the order."** Every surveyed Jev finance project gives Jev only typed judgments (Choice/Noul/Score) over a compact state (< 400 tokens). Thresholds, risk vetoes and order placement stay in deterministic code.
- **Atomic questions, composed in code.** reddy7356 asks six (regime, direction, toxic_flow, liquidity_stressed, quote_environment, inventory_pressure). To change behavior you change a coefficient, not a prompt.
- **Fallback ladder:**
  - healthy + high confidence → normal
  - low confidence → reduce size
  - past the deadline → hold
  - Jev down → deterministic fallback
  - limit breached → kill switch
- **Calibration loop:** log (state, decision, outcome) triples. Report Brier, log-loss, ECE and a reliability curve. Fit Platt scaling on *your* venue data, because TypeSafe's RLCD calibrates to its own distribution, not yours.
- awesome-jev's caveat: "schema-valid output is not the same as a correct decision". TypeSafe publishes "jaggedness" limits (arithmetic, dates, distractors, adversarial state).

**Recommended roles for this desk**

| Seat | Owns | Must never |
|---|---|---|
| Deterministic code | prices, Greeks, P&L, position limits (max loss/trade, max open risk, daily/weekly loss halt), fee/slippage model, the order ticket, the paper ledger | be overridden by any model |
| Claude Opus 5.5 (head) | research synthesis, choosing *which* pre-approved playbook applies, writing the trade memo, running the post-mortem, proposing parameter changes (applied only after human review) | size positions from verbal confidence; place orders; read raw web text and act on it in the same step |
| Jev (judge) | VETO-only typed checks: `event_risk_in_window?`, `regime_stressed?`, `quote_stale_or_crossed?`, `thesis_contradicted_by_state?`, returned as Noul probabilities with thresholds in code | approve a trade (it can only block); see unsanitized text |
| Human | types EXECUTE after reading the ticket (max loss in $, break-even, exit rules) | approve anything that failed a code limit |

**Failure modes to design against**
1. **Untrusted input.** An arXiv 2026 paper found hidden-text or homoglyph headline edits flipped LLM trading actions and cut returns by up to 17.7 points. TradeTrap and "Poisoning Agentic Alpha" found no multi-agent architecture was inherently robust.
   - Mitigations: strip headlines to ASCII and normalize them; pass only a structured summary (ticker, event type, timestamp) to Jev; treat all fetched text as data.
   - A veto-only Jev means injection can only *block* trades, never create them. Keep it that way.
2. **Calibration.** "The Alpha Illusion" (arXiv 2605.16895): "language confidence is not tradable probability." Never size from Claude's stated confidence. Measure Jev's ECE on your own logged outcomes before trusting any threshold.
3. **Fail-safe.** On any missing data, a stale quote (> N seconds), an API error, a model timeout or a ledger mismatch, the action is **no trade** and the kill switch trips. Reconcile the paper ledger to broker state daily.
4. **Backtest/paper optimism.** Paper fills at mid overstate results. Model fills at natural minus 25% of the width, and log the real quoted bid/ask at decision time.
5. **Overtrading.** Agent desks drift toward more trades. Cap trades per week in code.

---

## 5. Ranked recommendation and staged plan

### 5.1 Allocation of the $500

| Rank | Use | Amount | Why |
|---|---|---|---|
| 0 | **Pay off any credit card or other debt above ~8% APR** | all of it, if applicable | Guaranteed 22% beats every stream |
| 1 | **Core: fractional SPY/VTI (or HYSA if needed within 1–2 years)** | **$300–350** | ~9–11%/yr long-run expected; HYSA/T-bill 4.2–4.5% risk-free |
| 2 | **Options sleeve: SPY 1–2-wide put credit spreads, after a passing paper run** | **$150–200** (cash kept as spread collateral; max 1 open spread, ≤ $80–160 at risk) | Only stream with a documented structural premium; defined risk |
| 3 | Kalshi 15m BTC/ETH maker | **$0 live** (paper/shadow only; ≤ $25 test *if* the shadow run passes) | Public evidence: efficient market, adverse selection; claimed profits are vendor backtests |
| 4 | Sportsbook CLV | **$0 live** (shadow-log CLV only). Optionally claim sign-up promos with a strict no-chase rule. | $500 bankroll + fast limits + variance; Florida has one book |

**Don't do these:**
- 5-wide SPY/XSP spreads at $500 (~80% of the account per trade).
- Naked or cash-secured puts (can't collateralize).
- Long OTM calls or lottery 0DTE.
- Iron condors "for income" (CNDR ≈ T-bills).
- Buy a "Kalshi bot" or a "bot-for-kalshi" strategy.
- Chase sportsbook boosts or parlays.
- Let any model size a position or place an order.
- Use card deposits on Kalshi (up to 2% fee).
- Trade single-name spreads through earnings.

### 5.2 Stages

**Stage 0: 30-day paper run (now).** All three streams in shadow. Log real quotes at decision time, fill at natural, and apply real fees.

**Stage 1: tiny live (only for streams that passed Stage 0).**
- Options: one SPY 1-wide spread at a time (≤ $85 max loss). Weekly loss halt −$100; account halt at −$150 (−30%).
- Run 3 months or 20 live trades, whichever is later.

**Stage 2: scale.** Only with outside savings, not by levering the $500. Move to 2-wide, then 5-wide, once equity allows ≤ 10% of the account at risk per trade (5-wide needs ~$4k+). Revisit XSP when the account is large enough that $0.19 legs matter less than assignment risk.

### 5.3 Go/no-go metrics for the 30-day paper run

**Options (put spreads)**
- ≥ 8 closed paper trades. With 30-DTE spreads this may take more than 30 days; extend rather than lower the bar.
- **Expectancy per $ risked**, net of natural-fill slippage and fees: **> +2%** per trade (e.g. > +$1.60 per $80 of risk). No-go if ≤ 0.
- Realized fill vs mid: **≤ 25% of width** on paper-at-natural. Log what a mid-limit would have achieved.
- Max single-trade loss ≤ planned max loss (no leaks from assignment or gaps). Zero code-limit violations.
- Short-leg realized win rate compared with the delta-implied rate. **Go only if realized minus implied ≥ +5 points *and* the sample isn't in a straight-up market.** Compare the market's return over the same window; if SPY rose > 4%, the result is not evidence.
- Jev veto log: count vetoes and score the P&L of vetoed vs unvetoed trades. **The veto must not be net negative.**

**Kalshi 15m maker**
- ≥ 300 quoted windows in shadow, using real book depth and queue position (assume you sit behind existing size at your price).
- **Both-fill rate ≥ 60%** of quoted pairs *and* **net expectancy per filled contract > +0.5¢** after one-sided losses and fees. Also record the one-sided-fill loss/win ratio.
- Adverse-selection gap (P(win | filled) − P(win | not filled)) **must be < the spread captured**. The public benchmark is −15.7 points, which fails.
- No-go if P&L correlates > 0.8 with BTC drift (it's disguised direction, as in the hudson study).

**Sportsbook / event CLV (shadow)**
- ≥ 200 logged picks, timestamped, against the **no-vig Pinnacle (or sharpest available) close**.
- **Mean CLV ≥ +2%**, with a positive 95% CI lower bound, on sides/totals only. Props and early-season college don't count.
- Share of picks actually available to bet at your book (Hard Rock in FL, or Kalshi sports) at logged prices: ≥ 80%.
- Even if all of that passes, cap live exposure at promo value plus a ≤ $50 bankroll until the account is limited.

**Desk integrity (all streams)**
- 100% of live-eligible tickets carry a max-loss figure and a human EXECUTE record.
- 0 orders originating from model output without the code gate.
- Daily ledger reconciliation error = $0.
- Jev ECE < 0.1 on ≥ 100 logged judgments before any threshold is trusted.

---

## 6. Source-quality flags

- **Marketing / vendor (treat as claims, not evidence):**
  - Turbine (KXBTC15M market making, 1,600% ROI with every fill assumed)
  - botforkalshi.com strategy catalogs
  - SJ Options (sells systems; negative tasty backtest)
  - Spintwig's proprietary s1 signal
  - Underdog "doesn't limit" articles (XCLSV)
  - sportsbook-affiliate CLV explainers
  - Wharton "80%/yr" Kelly result (conditional on a real edge)
- **Better-grounded:**
  - Cboe index data and Bondarenko's paper
  - AQR/Israelov
  - the ORATS-based SteadyOptions test (author runs a put-write strategy, but the method is transparent)
  - Option Alpha (their own tool; no commissions)
  - hudsonjoshuaclark research (open data, negative result, no product to sell)
  - Kalshi fee schedule and CFTC filings
  - the FINRA/SEC PDT change
  - Fed G.19
  - arXiv papers on LLM trading failure modes
- **Community (anecdotal, survivorship-biased):**
  - r/sportsbook limit logs and promo logs (via SportBot/BetSuite summaries; Reddit was not fetched directly)
  - r/thetagang-style win-rate claims. Winners post and blown-up accounts go quiet; the high win rates reported for short premium hide the left tail (see 2008, Feb 2018, Mar 2020, Apr 2025 with VIX 52).

---

## Sources

**Market data (retrieved via connectors, 2026-09-28/29)**
- Robinhood read-only quotes: SPY, IWM; SPY 10/30/2026 puts 740/745/748/749/750; XSP 10/30/2026 puts 745/750
- TradingView monthly: AMEX:SPY, CBOE:PUT, CBOE:BXM, CBOE:CNDR
- Alpha Vantage TREASURY_YIELD 3-month, daily (4.24% on 2026-09-25)

**Options / VRP**
- https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf
- https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/
- https://www.cboe.com/insights/posts/benchmark-indices-series-volatility-management-with-cboes-bfly-and-cndr-indices
- https://ir.cboe.com/news/news-details/2015/CBOE-Introduces-10-Options-Based-Strategy-Performance-Benchmark-Indexes-07-29-2015/default.aspx
- https://s202.q4cdn.com/174824971/files/doc_news/2016/02/study-analyzes-performance-of-cboe-spx-options-selling-indexes-pdf1691637391968.pdf
- https://optionalpha.com/podcast/option-strategy-performance
- https://www.cboe.com/insights/posts/index-insights-august-2026/
- https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/Pathetic-Protection-JAI-Wint19.pdf
- https://www.aqr.com/-/media/AQR/Documents/White-Papers/Understanding-the-Volatility-Risk-Premium.pdf
- https://steadyoptions.com/articles/spy-short-puts-vs-put-spreads-r658/
- https://optionalpha.com/blog/spy-put-credit-spread-backtest
- https://www.sjoptions.com/tastytrade-credit-spreads-do-they-work/
- https://spintwig.com/short-spx-put-45-dte-s1-signal-options-backtest/
- https://earlyretirementnow.com/2021/11/10/passive-income-through-option-writing-part-9-2016-2021-backtest-guest-post-by-spintwig/
- https://www.daystoexpiry.com/blog/best-dte-for-credit-spreads-a-data-driven-comparison-of-30-45-and-60-day-trades
- https://thetaloop.app/learn/bull-put-spread
- https://stockwirex.com/education/naked-short-puts-vs-put-spreads/
- https://stockwirex.com/education/options-strategy-retail-investors/
- https://blog.traderspost.io/article/xsp-options-for-smaller-accounts
- https://cdn.cboe.com/resources/xsp/XSP_Options_Fact_Sheet.pdf
- https://robinhood.com/us/en/learn/articles/what-are-xsp-options/
- https://brokerchooser.com/broker-reviews/robinhood-review/sp500-options-fees
- https://cdn.robinhood.com/assets/robinhood/legal/RHF+Fee+Schedule.pdf

**Robinhood / regulation**
- https://robinhood.com/us/en/support/articles/advanced-options-strategies/
- https://robinhood.com/us/en/support/articles/minimum-margin/
- https://assets.ctfassets.net/5ft2qdzfrz9o/4be9qE9Ftoc33xa1Th6M4Y/4cc68de886dedb16d4e837988ee58402/Robinhood_Instant_Agreement.pdf
- https://www.finra.org/compliance-tools/weekly-archive/04152026
- https://www.sec.gov/files/rules/sro/finra/2026/34-105226.pdf
- https://www.schwab.com/learn/story/sec-approves-scrapping-25000-day-trader-minimum
- https://www.kslaw.com/news-and-insights/finra-adopts-sweeping-changes-to-margin-requirements-for-day-trading

**Kalshi**
- https://kalshi.com/docs/kalshi-fee-schedule.pdf
- https://help.kalshi.com/en/articles/13823805-fees
- https://help.kalshi.com/en/articles/15410219-liquidity-provider-program
- https://help.kalshi.com/en/articles/13823819-how-to-become-a-market-maker-on-kalshi
- https://www.cftc.gov/sites/default/files/filings/orgrules/25/01/rules01132513688.pdf
- https://github.com/hudsonjoshuaclark/kalshi-bot
- https://whirligigbear.substack.com/p/makertaker-math-on-kalshi
- https://www.turbinefi.com/blog/why-prediction-market-trades-get-picked-off-2026 (vendor)
- https://www.turbinefi.com/research/market-making-on-kxbtc15m-with-post-only-resting-orders-can-generat-c90ca2fc0354 (vendor; assumes all orders fill)
- https://www.navnoorbawaresearch.com/p/kalshi-publishes-one-liquidity-subsidy
- https://github.com/gallantfoxapp/kalshi-incentives
- https://www.botforkalshi.com/bot-catalog (marketing)
- https://natlawreview.com/article/place-your-bets-us-district-courts-are-split-whether-commodity-exchange-act
- https://thenevadaindependent.com/article/federal-judge-rules-that-kalshi-must-stop-offering-prediction-contracts-in-nevada
- https://www.si.com/prediction-markets/reviews/kalshi-florida
- https://defirate.com/prediction-markets/robinhood/
- https://www.axios.com/2026/09/08/robinhood-crypto-og-kalshi-prediction-markets

**Sports betting**
- https://unabated.com/articles/getting-precise-about-closing-line-value
- https://unabated.com/articles/finding-positive-ev-wagers-step-by-step-guide
- https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl
- https://wsb.wharton.upenn.edu/wp-content/uploads/2023/05/Beggy_2023__Betting_Kelly.pdf
- https://www.sportbotai.com/blog/reddit-positive-ev-betting
- https://www.sportbotai.com/blog/draftkings-reddit
- https://betsuite.ai/blog/how-to-avoid-getting-limited
- https://betherosports.com/blog/draftkings-review
- https://xclsvmedia.com/underdog-sportsbook-review-2026-last-book-doesnt-limit-winners/ (affiliate)
- https://www.legalsportsreport.com/sports-betting/states/florida/
- https://rotogrinders.com/sports-betting/states/florida

**Baselines**
- https://www.bankrate.com/banking/savings/best-high-yield-interests-savings-accounts/
- https://www.fool.com/money/banks/articles/top-savings-account-rates-today-sept-28-2026/
- https://thecollegeinvestor.com/89432/best-high-yield-savings-rates-for-september-28-2026/
- https://www.lendingtree.com/credit-cards/study/average-credit-card-interest-rate-in-america/
- https://www.federalreserve.gov/releases/g19/hist/cc_hist_tc_levels.html

**Agent architecture / failure modes**
- https://github.com/reddy7356/jev-trader
- https://gist.github.com/drillan/6916b16e8ea31a8ec36c8f59d6483150
- https://github.com/cobanov/awesome-jev
- https://github.com/jarrodwatts/jev-trader
- https://arxiv.org/html/2601.13082v1 (adversarial headlines)
- https://arxiv.org/pdf/2605.16895v1 (The Alpha Illusion)
- https://arxiv.org/pdf/2512.02261 (TradeTrap)
- https://arxiv.org/abs/2608.24069 (Poisoning Agentic Alpha)
- https://cerevisor.com/blog/markets-trading-agent-prompt-injection
