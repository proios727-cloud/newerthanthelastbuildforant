# Crypto Strategy Candidates for the Agent Desk: Paper-Test Specs

**Date:** 2026-09-29 · **Scope:** research only. No trades placed. The Robinhood connector was used read-only (`get_crypto_quotes`, `get_equity_quotes` only).
**Desk context:** Claude Opus 5.5 does research and orchestration. TypeSafe Jev can only veto. Deterministic Python owns sizing, limits and the kill switch. A human types `EXECUTE` before any real order. The user is a US retail trader in Florida.

**Labels used throughout.** **[SRC]** marks a sourced fact, with its URL and date in the Sources list. **[EST]** marks my own estimate or arithmetic. **[LIVE]** marks data pulled through a connector today. **[UNVERIFIED]** marks something that still has to be checked before it is relied on.

---

## 0. Market snapshot used for all math

| Item | Value | Label |
|---|---|---|
| 3-mo Treasury CMT | **4.24%** (2026-09-25) | [LIVE] Alpha Vantage TREASURY_YIELD |
| BTC (RH mark) | $83,186. RH book showed bid 83,187.08 > ask 83,185.11, a crossed quote and a data-quality flag | [LIVE] RH get_crypto_quotes 13:33 ET |
| ETH / SOL (RH mark) | $2,678.61 (spread ≈0.8 bp) / $118.01 (spread ≈1.5 bp). Routing = "Exchange Routing" | [LIVE] |
| RH crypto fees | Exchange routing at the <$10k tier: **0.95% taker / 0.50% maker**. $10–50k tier: 0.75% / 0.35%. Market-maker routing: "no commission", but RH gets **$0.95 per $100** through the spread | [SRC] RH fee schedule and order-routing page (as of 2026-06-15) |
| Coinbase spot fees | <$10k tier **60 bp taker / 40 bp maker**. $10–50k tier 40 / 25 | [SRC] Coinbase help |
| Spot ETF quotes | IBIT 47.04/47.05 (≈2 bp). ETHA 20.15/20.17 (≈10 bp). BSOL 16.23/16.24 (≈6 bp). FBTC 72.27/72.28 | [LIVE] RH get_equity_quotes 13:35 ET |
| BTC trend state | Close 83,168. SMA20 80,924. SMA100 70,093 → **LONG**. RV30 = 41.6% annualized. Net change over 400 days: −24.5% | [LIVE] TV COINBASE:BTCUSD 1D |
| ETH trend state | SMA20 2,598 > SMA100 2,112 → **LONG**. RV30 44.3% | [LIVE] TV COINBASE:ETHUSD |
| SOL trend state | SMA20 110.4 > SMA100 87.9 → **LONG**. RV30 63.6% | [LIVE] TV COINBASE:SOLUSD |
| Binance BTC perp funding | 30-day average **6.82%** annualized. 12-month average **3.40%**. Negative for 3 straight months (Feb–Apr 2026) | [SRC] Upshift, 2026-09-24, from the Binance public API |
| ETH perp funding (cross-venue) | Binance 30-day average 5.07%. Hyperliquid 30-day average 9.91% (floor rate ≈11% annualized) | [SRC] yieldo.me, 2026-09-24 |
| Coinbase CDE BIP funding | Snapshot 0.0003%/hr (≈2.6% annualized). The page shows "Jul 2026", so the date is uncertain | [SRC] coinbase.com BIP page |
| CME BTC basis | Sep 2026 settled ≈**5.3%** (range 5–6%). Aug 7: Aug 7.89%, Sep 6.25%, Dec 5.69% gross | [SRC] cryptoinsider 2026-09-19; CryptoSlate 2026-08-11 |
| Binance quarterly basis history | Median 5.7% (BTC). Above 10% on 24% of days. 2026 YTD median 3.1%, below the bill on 64% of days | [SRC] tradewize 2026-09-13 |
| Stablecoin yields | Coinbase USDC reward 3.5% APY. Aave USDC supply 3.62% (Sep 24). sUSDe 4.67% (Sep 24), down from a 10.6% average | [SRC] Forbes 2026-05-20; Upshift 2026-09-24 |

**The key structural fact.** Retail crypto spot at the entry tier costs 0.4–0.95% per side, while spot ETFs in a brokerage cost about 2–10 bp per side. Every candidate below that needs spot exposure therefore uses **spot ETFs (IBIT/ETHA/BSOL)** where possible and treats crypto spot as a fallback.

**Legality flag.** Hyperliquid's Terms (updated 2026-06-15) list US persons as "Restricted Persons" [SRC]. The existing **S1.1 Carry Desk may use Hyperliquid only as a data/signal source**. It is not an execution venue for a Florida resident. The US-legal perp venue is **Coinbase Derivatives (CDE) "perp-style" futures** (BIP 0.01 BTC, ETP 0.1 ETH, plus many alts), which trade through Coinbase Financial Markets, a CFTC-registered FCM [SRC]. The CFTC also approved a KalshiEX bitcoin perpetual on 2026-05-29 [SRC, secondary: hyperliquidguide]. Coinbase's *international* perps (INTX/Bermuda) are **not available to US persons** [SRC].

---

## 1. Ranked summary

| Rank | Strategy | Type | Est. edge vs T-bill (my estimate, before paper validation) | $500 verdict | $10k verdict |
|---|---|---|---|---|---|
| 1 | **S-TREND**: 20/100 trend, BTC/ETH(/SOL) via spot ETFs, vol-targeted, long/flat | Directional | Wide range, −3% to +8%/yr excess; mainly drawdown control | Survives (costs ≈0.2%/yr); edge ≈$0–40/yr | Survives; ≈$0–800/yr, DD risk $2–3k |
| 2 | **S-CARRY-PERP**: long IBIT/ETHA + short CDE nano perp; gated on funding | Market-neutral carry | Positive only when CDE funding ≥ ~7.2% annualized | **Not viable** (one BTC unit needs ≈$1.33k; one ETH unit earns ≈$13/yr vs $21 in T-bills) | Break-even at 7% funding; +$300/yr above T-bill at 12% |
| 3 | **S-BASIS-DATED**: long ETF + short dated CME Micro / CDE nano future; lock basis | Market-neutral carry (locked) | Positive only when annualized basis ≥ ~7.8% | Not viable for BTC. ETH nano is marginal, [UNVERIFIED] size | Alert-only; fires on an estimated 15–25% of days historically |
| 4 | **S-UNLOCK**: short CDE alt perp-style futures around large team/investor cliff unlocks | Event-driven | Gross ≈0.5–2%/trade (sourced effect sizes); evidence conflicts | Marginal (contract sizes [UNVERIFIED]) | Testable, small allocation |
| 5 | **S-FUNDX**: BTC funding-extreme overlay (de-risk at top decile; small confirmed long after negative-funding recovery) | Mean-reversion / risk overlay | Standalone edge statistically weak; more useful as a gate for #1 and #2 | Overlay only | Overlay plus a small tactical sleeve |

**Rejected, with reasons (section 7):** (d) cross-sectional top-20 momentum, (e) stablecoin/on-chain yield, (f-weekend) weekend/overnight effects, (g-ETF) ETF-flow chasing.

---

## 2. S-TREND: Time-series trend, vol-targeted, long/flat (RANK 1)

### 2.1 Spec (machine-readable)
```json
{
  "id": "S-TREND",
  "universe": ["IBIT (BTC)", "ETHA (ETH)", "BSOL (SOL, optional sleeve)"],
  "signal_source": ["COINBASE:BTCUSD", "COINBASE:ETHUSD", "COINBASE:SOLUSD"],
  "timeframe": "1D bars, computed 20:00 UTC daily; orders only in the US cash session next day",
  "features": {"sma_fast": 20, "sma_slow": 100, "rv_window_days": 30, "vol_target_ann": 0.30},
  "entry": "close > 0 AND SMA20 > SMA100 on the signal asset (crypto 24/7 close), confirmed on 2 consecutive daily closes",
  "exit": "SMA20 < SMA100 on 2 consecutive closes OR hard stop: asset close < 0.80 * entry-peak (trailing 20%)",
  "sizing": "w_i = min(1, vol_target / RV30_i) * sleeve_budget_i; sleeves BTC 50%, ETH 30%, SOL 20% of strategy capital; rebalance only if |w - w_held| > 20% of w_held",
  "cash_leg": "unallocated capital in T-bill ETF / broker sweep (benchmark 4.24%)",
  "holding_period": "weeks-months; est. 3-8 round trips/asset/yr [EST]",
  "costs": {"etf_spread_bp": {"IBIT": 2, "ETHA": 10, "BSOL": 6}, "commission": 0, "expense_ratio": "~0.20-0.25%/yr on held exposure [UNVERIFIED — check prospectus]"},
  "risk_limits": {"max_gross_exposure": 1.0, "max_single_asset": 0.5, "strategy_dd_kill": 0.20, "no_leverage": true},
  "venue": "Robinhood equities (IBIT/ETHA/BSOL) — US-legal, FL OK; fallback Coinbase spot (40-60 bp/side)"
}
```
**Current state [LIVE]:** all three assets are LONG. Target weights at a 30% vol target: BTC 0.30/0.416 ≈ 0.72 × 50% = 36% of capital. ETH 0.68 × 30% = 20%. SOL 0.47 × 20% = 9%. Total ≈65% invested, with 35% in the cash leg.

### 2.2 Expected edge (sourced vs estimated)
- [SRC] Zarattini et al. (SSRN 5209907, 2025) use an ensemble Donchian trend on a top-20 rotational crypto portfolio. They report net-of-fees **Sharpe > 1.5** and **10.8% annual alpha vs BTC**.
- [SRC] Kang & Ryu (Risk Management 28(3), Sep 2026) find that **slow (~12-week) signals beat fast signals** in BTC.
- [SRC] Tripathi (Financial Economics Letters 2026) finds a BTC EMA trend with 3× stressed costs stays positive: max DD −44.8% / −51.5% across regimes. That paper is from a minor journal, so treat it as weak evidence.
- [SRC] The desk's own shadow backtest of BTC/ETH/SOL momentum/breakout showed **no edge**. That result is prior evidence *against* this strategy. The 20/100 variant has to be tested on the same harness.
- [EST] Forward net Sharpe is probably 0.3–0.6, not the published 1.5, because of publication bias, 2021–2024 bull-sample dominance, and 2026's chop (BTC −24% over 400 days with a sharp June drawdown). Excess over T-bills is −3% to +8%/yr on strategy capital. The main value is **cutting the left tail**: flat through the June 2026 drop from $73k to $58k.

### 2.3 Costs and survivability [EST]
- Trades: 4–8 round trips/yr/asset. Each round trip costs about 2 × half-spread (1–5 bp), so under 0.1%/yr. The expense ratio on average exposure (~55%) is about 0.13%/yr. **Total drag ≈0.2%/yr.**
- **$500:** RH fractional shares make it feasible. Cost ≈$1/yr. Expected excess ≈ −$15 to +$40/yr. A 20% strategy DD is $100. **Survives on costs, but the dollar edge is trivial.** Treat it as a learning and discipline exercise.
- **$10k:** cost ≈$20/yr. Expected excess ≈ −$300 to +$800/yr. The 20% DD kill equals $2,000. **Survives.**
- Crypto-spot fallback on RH at the <$10k tier: 0.5–0.95% per side × 6 round trips × 2 sides ≈ 6–11%/yr drag. **Do not use RH crypto spot for this strategy.**

### 2.4 Jev questions (veto-only)
| # | Type | Instruction | Criteria | Code rule |
|---|---|---|---|---|
| J1 | noul | "Given this signal packet (SMA20, SMA100, RV30, last 10 closes, pending order), is there a data error (stale bar, crossed/zero quote, split/NAV anomaly, ETF halted)?" | Check timestamps < 26h old, ETF bid<ask and >0, crypto close vs ETF-implied price within 1.5% | Veto if answer = yes/unsure |
| J2 | choice | "Classify the next 5 trading days' known event risk: {none, macro_scheduled (FOMC/CPI), crypto_structural (exchange hack, ETF regulatory action), unknown}" | Use economic calendar + Bigdata.com news provided in packet only | Veto new **entries** (not exits) if `crypto_structural` |
| J3 | score 0–100 | "How likely is the order to be a mechanical mistake (wrong ticker/side/size vs spec)?" | Compare order JSON vs spec JSON | Veto if score ≥ 20 |
Jev may never trigger or upsize. Exits and kill-switch actions cannot be vetoed by Jev. The code enforces this.

### 2.5 Data
- Daily OHLCV: **TradingView RH_TV_HFT `mcp-tv-get-ohlcv`** (COINBASE:BTCUSD/ETHUSD/SOLUSD), confirmed working. The backup is Alpha Vantage `DIGITAL_CURRENCY_DAILY`.
- ETF quotes: **Robinhood `get_equity_quotes`** (read-only), confirmed working.
- T-bill hurdle: **Alpha Vantage `TREASURY_YIELD` (3month, daily)**, confirmed working.
- News for J2: **Bigdata.com `bigdata_search`**, RH_TV `get-economic-calendar`.

### 2.6 Thesis / catalyst / crowding / bear case / invalidation
- **Thesis:** crypto returns cluster in trends driven by retail leverage and attention. The BIS carry paper describes trend-chasing small investors [SRC]. Slow signals avoid noise.
- **Catalyst:** all three assets have been in uptrends since mid-August 2026, and ETF inflows were $3.52B in August [SRC].
- **Crowding:** CTAs and managed futures already run crypto trend via CME. CME leveraged funds flipped net long in August 2026 [SRC]. Crowding raises whipsaw risk at turns.
- **Bear case:** range-bound chop, such as July–August 2026 when BTC sat at $60–66k, produces repeated false crosses. Also gap-downs larger than 20% over weekends while the ETF is closed: crypto trades 24/7, but IBIT only trades in the cash session, so the fill is Monday's open.
- **Invalidation:** walk-forward on 2018–2026 using the desk harness shows net Sharpe < 0.3 or excess vs T-bills < 0. Or live paper tracking error vs the model is > 1%/month.

### 2.7 Paper-test go/no-go
| Window | GO if | NO-GO if |
|---|---|---|
| 30 d | 0 execution/data errors. Fills within 5 bp of model. Signal packets delivered daily 100%. Jev false-veto rate < 10% | Any missed exit. Any crossed-quote order sent |
| 90 d | Walk-forward backtest (desk harness, 2018–2026) net Sharpe ≥ 0.5 **and** paper P&L within ±2σ of model **and** max DD ≤ 15% | Backtest Sharpe < 0.3, OR paper DD > 20% (kill) |
Ninety days of live P&L cannot prove edge (at most 1–3 trades). The go decision rests mainly on the out-of-sample backtest plus execution fidelity.

---

## 3. S-CARRY-PERP: US-regulated funding carry (RANK 2)

### 3.1 Spec
```json
{
  "id": "S-CARRY-PERP",
  "legs": {"long": "IBIT (or ETHA) in Robinhood brokerage", "short": "Coinbase CDE nano Bitcoin Perp Style (BIP, 0.01 BTC) or nano Ether Perp Style (ETP, 0.1 ETH)"},
  "hedge_ratio": "IBIT BTC/share = IBIT_px / BTC_px (today 47.045/83186 = 0.0005655) -> 1 BIP ~= 17.7 IBIT sh; ETHA ETH/share = 20.16/2678.6 = 0.007526 -> 1 ETP ~= 13.3 ETHA sh",
  "features": ["CDE hourly funding (premium TWAP, alpha=0.75 smoothing)", "trailing 7d and 30d annualized funding", "Binance/Hyperliquid funding as leading indicators (data only)", "T-bill 3m"],
  "entry": "trailing 7d CDE funding_ann >= hurdle AND trailing 30d >= hurdle - 1pp, where hurdle = T-bill + 3.0pp (today 7.24%)",
  "exit": "trailing 7d funding_ann < T-bill OR 3 consecutive days negative OR margin ratio alert OR hedge drift > 3% notional",
  "holding_period": "weeks-months",
  "margin": "keep short-leg account at >= 2x overnight initial margin (Coinbase example uses 25% IM [SRC]; actual overnight IM varies [UNVERIFIED])",
  "risk_limits": {"max_strategy_capital_pct": 0.5, "rebalance_band": 0.03, "kill_if_unhedged_minutes": 60, "no_weekend_entries": true},
  "venue": "US-legal: CDE via Coinbase Financial Markets (CFTC FCM) + RH equities; NOT Hyperliquid (US persons restricted)"
}
```

### 3.2 Edge
- [SRC] BIS WP 1087 (Schmeling, Schrimpf & Todorov; 2023, rev. 2025): crypto carry averaged about 7% p.a. (Apr 2019–Jul 2024). After the ETF launches it fell by about 3pp everywhere and by an extra 5pp on CME. **High carry predicts crashes.**
- [SRC] Ethena docs: BTC/ETH funding averaged 7.8–9% over roughly 3 years. That is stale bull-sample data. Current sUSDe pays 4.67%, and USDe supply fell from $14.8B to $4.9B, which is evidence the carry has compressed.
- [SRC] Binance BTC funding 12-month average 3.40%, 30-day average 6.82% (to 2026-09-24).
- [SRC] CDE funding is **premium-only**: TWAP of (futures − spot)/spot/24, smoothed. Binance adds a fixed interest component that CDE lacks, so **CDE funding is likely structurally lower than Binance/Hyperliquid [EST]**. The only CDE snapshot found is about 2.6% annualized. **This must be measured before anything else.**
- [SRC] An independent GitHub falsification study found the Binance timing-gated carry with 24h holds **negative OOS in every symbol** (cost floor 0.48%/trade). This spec therefore holds for weeks, not days.

### 3.3 Costs and survivability [EST]
Per BTC unit: $832 notional. Capital ≈ $832 ETF + ~$250 margin + ~$250 rally buffer = **$1,330**. Round trip ≈ ETF 2 bp × 2 + CDE fees (exchange $0.10/side [SRC] + Coinbase commission, historically 0.05% [SRC, possibly stale]) ≈ 0.16%. ETF expense ratio about 0.25%/yr drags the long leg.

Return on capital ≈ (F − 0.25 − 0.16) × 832/1330:

| CDE funding F (ann.) | 3% | 5% | 7% | 9% | 12% |
|---|---|---|---|---|---|
| Return on capital | 1.6% | 2.9% | 4.1% | 5.4% | 7.3% |
| vs T-bill 4.24% | −2.6 | −1.4 | −0.1 | +1.1 | +3.0 |

- **$500:** a BTC unit is infeasible (needs $1,330). One ETH unit (≈$400 capital) at 5% funding earns ≈(5 − 0.41)% × $268 ≈ **$12/yr vs $21 from T-bills on $500**. **NOT VIABLE.**
- **$10k:** 7 BTC units ($5.8k notional, $9.3k capital). At 7% funding that is ≈$384 vs $424 T-bill (**break-even**). At 12% it is ≈$680 (+$256 vs T-bill). **Viable only in a hot-funding regime. The gate is essential.**
- Tax [EST, consult CPA]: CDE futures get 60/40 treatment. The ETF leg is ordinary capital gains, so hedged P&L can be **mismatched in tax character**. This is a hidden drag.

### 3.4 Jev questions
| # | Type | Instruction | Criteria | Code rule |
|---|---|---|---|---|
| J1 | noul | "Do both legs reference the same underlying and do quantities match the hedge ratio within 3%?" | Uses the order JSON plus the ratio | Veto on no/unsure |
| J2 | choice | "Funding regime: {broad_positive, venue_specific_only, turning_negative, unclear}" | CDE vs Binance vs Hyperliquid 7-day series in the packet | Veto entry unless `broad_positive` |
| J3 | score 0–100 | "Probability that funding goes negative within 14 days, given the last 90 days of series and BIS finding that high carry precedes crashes" | Calibrated estimate only | Veto entry if ≥ 40. **Never used to upsize** |
| J4 | noul | "Any venue/regulatory event (CDE halt, FCM notice, ETF premium/discount > 0.5%)?" | News plus ETF NAV vs price | Veto on yes/unsure |

### 3.5 Data
- **CDE funding and marks:** Coinbase Advanced Trade API, US derivatives endpoints (documented [SRC]). The specific product/funding endpoint paths are **[UNVERIFIED]**: read them from the official docs before coding. They are not connectors available here.
- Binance funding history: the public futures REST API. US IPs may be geo-blocked (HTTP 451) **[UNVERIFIED]**.
- Hyperliquid funding history: public info API. It is read-only data, but the ToS restricts US persons from the interface. **Legal gray area; flag to the user.**
- TradingView `BINANCE:BTCUSDT.P` returns perp *price* bars [LIVE confirmed]. **No funding symbol was confirmed on TV.**
- IBIT/ETHA quotes: RH `get_equity_quotes`. T-bill: Alpha Vantage.

### 3.6 Thesis, bear case, invalidation
- **Thesis:** retail leverage demand makes longs pay shorts on average, and arbitrage capital stays scarce (BIS).
- **Catalyst:** 30-day funding rose to 6.8% (Binance) and ETH to 10% (Hyperliquid) in September 2026.
- **Crowding:** Ethena, basis funds and CTAs all run this. USDe shrinking 67% shows the returns are already arbitraged down.
- **Bear case:** Feb–Apr 2026 was three months of negative funding [SRC]. A sharp rally pushes the short leg into margin calls while the ETF gain sits in a *different account* (RH vs Coinbase), so there is **cross-margin risk**. ETF closed on weekends.
- **Invalidation:** the 30-day CDE funding series averages below T-bill + 1pp for 60 days, or realized hedge slippage exceeds 0.5%/month.

### 3.7 Paper-test go/no-go
| Window | GO | NO-GO |
|---|---|---|
| 30 d | A CDE funding series is collected hourly with ≥ 99% coverage. Modeled carry vs Binance correlation is reported. Hedge drift is always < 3% | CDE 30-day average funding < T-bill (then the strategy stays dormant rather than killed) |
| 90 d | Gated paper P&L beats the T-bill benchmark on the same capital by ≥ 1pp annualized **and** there were 0 margin breaches | Any modeled liquidation, or carry < T-bill while the gate was ON |

---

## 4. S-BASIS-DATED: cash-and-carry with dated futures (RANK 3)

### 4.1 Spec
```json
{
  "id": "S-BASIS-DATED",
  "legs": {"long": "IBIT / ETHA", "short": "CME Micro Bitcoin (MBT, 0.1 BTC) or CDE nano Bitcoin Futures (BIT, 0.01 BTC) / nano Ether Futures (ET) dated contract"},
  "feature": "annualized basis = (F/S - 1) * 365 / DTE using settlement vs benchmark spot (CME BasisWatch-style 4pm ET matching) [SRC methodology]",
  "entry": "annualized basis - T-bill - annualized round-trip cost >= 3.5pp (today => basis >= ~7.8-8.5%) AND DTE between 30 and 120",
  "exit": "hold to expiry (cash-settle) OR early close if basis captured >= 80% of locked amount",
  "holding_period": "30-120 days",
  "risk_limits": {"max_strategy_capital_pct": 0.5, "margin_buffer": "2x IM", "no_roll_if_basis_below_hurdle": true},
  "venue": "CME via a futures-enabled broker, or CDE via Coinbase Financial Markets — US-legal"
}
```

### 4.2 Edge
- [SRC] CME BTC basis about 5.3% (Sep 2026). Dec contract 5.69% gross on Aug 7. Binance Dec 4.7% on Sep 12.
- [SRC] tradewize: the carry beat the 3-month bill on 16 of 21 BTC quarterlies, but **lost in most of 2022–23 and in 2026 YTD** (basis under the bill on 64% of days). Basis > 10% on 24% of days, mostly in 2021 and 2024. Rank correlation with funding is +0.75 (BTC).
- [SRC] BIS: the ETF launch cut the CME basis by about 97% of its mean effect. CME OI fell to about $7.2B in April 2026.
- [EST] Return on capital ≈ (B − 0.25 ER − 0.73 annualized cost) × 0.63. It beats 4.24% only when **B ≥ ~7.8%**. **Today it is NOT triggered.**

### 4.3 Survivability [EST]
- **$500:** BTC nano ($832) and CME micro (~$8.3k) are both infeasible. The ETH nano dated contract size and availability are **[UNVERIFIED]** (the fee schedule lists "nano Ether Futures ET"). Even if feasible, at 5% basis it earns ≈$10/yr. **Not viable.**
- **$10k:** CDE nano BIT is feasible (7 units). CME MBT at 0.1 BTC needs ≈$8.3k ETF plus ~$2–3k margin, which is marginal. At B = 5.3% it earns ≈$230/yr vs $424 T-bill (**loses**). At B = 11% it earns ≈$590 (**+$166**). **Alert-only.**

### 4.4 Jev questions
| # | Type | Instruction | Code rule |
|---|---|---|---|
| J1 | noul | "Is the basis computed from time-matched spot and futures prices (≤ 5 min apart) and correct DTE?" | Veto on no/unsure |
| J2 | score | "Probability the basis print is an artifact (illiquid settlement, stale spot)" | Veto if ≥ 25 |
| J3 | choice | "Is basis elevated because of {broad_leverage_demand, single_venue_squeeze, data_error, unclear}?" | Veto unless `broad_leverage_demand` |

### 4.5 Data
- CME settlements: the CME daily settlement bulletin and BasisWatch [SRC exists]. Access method (web vs paid DataMine) is **[UNVERIFIED]**.
- CDE dated futures prices: the Coinbase Advanced Trade API [SRC docs].
- TV: CME micro symbols such as `CME:MBT1!` may exist on TradingView **[UNVERIFIED, not tested]**.
- Spot/ETF: RH and TV. T-bill: Alpha Vantage.

### 4.6 Thesis, bear case, invalidation
- **Thesis:** locked, known-at-entry carry. It is the closest thing crypto has to a bond. **Catalyst:** basis spikes during rallies, e.g. above 40% around the Nashville event [SRC].
- **Crowding:** heavy. Institutional ETF-basis capital is ready to return when basis beats SOFR.
- **Bear case:** fires rarely. When it fires, spot is in a euphoric rally and the BIS finds carry predicts crashes. The locked return is safe only if margin survives the path.
- **Invalidation:** after 12 months, a triggered-trade count below 2 means the capital is better off in T-bills permanently.

### 4.7 Go/no-go
- **30 d:** the basis monitor logs daily for CME and CDE with 0 gaps, and alerts fire correctly on synthetic tests.
- **90 d:** if ≥ 1 trigger occurred, the paper trade's realized convergence matches the locked basis within 0.3pp. If there were 0 triggers, keep it dormant as a monitor (not a failure).

---

## 5. S-UNLOCK: Token-unlock event short via CDE alt perp-style futures (RANK 4)

### 5.1 Spec
```json
{
  "id": "S-UNLOCK",
  "universe": "tokens with CDE perp-style futures (fee schedule lists e.g. SUI, AVAX, LINK, DOT, ADA, HBAR, XLM, DOGE, ENA, ONDO, AAVE, NEAR, ZEC) [SRC fee schedule 2026-03-02]",
  "features": ["unlock size as % circulating supply", "recipient class (team/investor/ecosystem)", "cliff vs linear", "7d pre-event return vs BTC", "CDE funding"],
  "entry": "cliff unlock >= 2% of circulating supply, recipient in {team, investor}, not ecosystem; open short at T-7d close (UTC)",
  "exit": "close at T+4d, OR stop if token outperforms BTC by +8% since entry, OR take-profit -10%",
  "optional_hedge": "long BIP sized to 60-day beta vs BTC (only at $10k)",
  "holding_period": "~11 days",
  "risk_limits": {"max_per_event_capital": 0.1, "max_concurrent": 3, "no_trade_if_catalyst": "product launch / listing / buyback within window"},
  "venue": "CDE via Coinbase Financial Markets — US-legal; contract sizes per alt [UNVERIFIED]"
}
```

### 5.2 Edge (conflicting evidence)
- [SRC] Keyrock (2024-12, n > 16,000): **90% of unlocks create negative pressure**. The decline starts about 30 days before. Team unlocks are worst (about −25%). Ecosystem unlocks are positive (+1.18%).
- [SRC] Animoca Research (2025-01): a 1% unlock gives about −0.3% in the week before and −0.3% in the week after. The strongest days are T−2 and T+3/T+4.
- [SRC] Messari via Gate (2024-09): ≥ 5% circulating supply matters most; often priced in.
- [SRC] unlocks.app (2024): private-investor cliffs averaged **+20% at 15 days**, which contradicts the others. A 236-event study also says drops are "mostly priced in before the unlock".
- [EST] Net expectancy ≈ +0.5 to +1.5% per trade gross on a ≥ 3% unlock. Hit rate is about 55–60%. Tails are fat: the Springer 2025 paper shows single-coin jumps crash short legs.

### 5.3 Survivability [EST]
- Costs per round trip: CDE exchange fee ~$0.10/side plus commission (~0.05%) ≈ 0.1–0.15%. Funding is received if positive.
- **$500:** 12–24 events/yr × ~$150–300 notional × 1% ≈ **$20–70/yr gross**, with high variance. Roughly equal to T-bills ($21) at the low end. **Marginal, and still depends on the contract sizes being verified.**
- **$10k:** 10% per event ($1k notional) × 18 events × 1% ≈ $180/yr on the sleeve, **+1.8% on total capital**. Tail loss per event is capped by the +8% stop at ≈$80. **Testable.**

### 5.4 Jev questions
| # | Type | Instruction | Code rule |
|---|---|---|---|
| J1 | noul | "Is the unlock confirmed by ≥ 2 independent sources with matching date and size?" | Veto on no/unsure |
| J2 | choice | "Recipient class: {team, investor, ecosystem, mixed, unknown}" | Veto unless team or investor |
| J3 | noul | "Is there a positive catalyst (launch, listing, buyback, ETF filing) inside the window?" | Veto on yes/unsure |
| J4 | score | "Squeeze risk 0–100 (funding deeply negative, high short OI, small float)" | Veto if ≥ 50 |

### 5.5 Data
- Unlock calendar: Tokenomist (formerly Token Unlocks), DefiLlama Unlocks, Messari. API access and pricing are **[UNVERIFIED]**. None is a connected tool here, so use Exa `web_fetch_exa` to scrape public pages as a fallback.
- Price bars: TradingView (e.g. `COINBASE:SUIUSD`) [EST that symbols exist]. News/catalysts: Bigdata.com.
- CDE alt contract specs: the Coinbase Derivatives spec PDFs [SRC for BIP/ETP; others UNVERIFIED].

### 5.6 Thesis, bear case, invalidation
- **Thesis:** predictable supply overhang plus unsophisticated team selling [Keyrock].
- **Crowding:** high. Market makers pre-hedge 1–4 weeks ahead [Keyrock], so the edge may already sit before T−7.
- **Bear case:** crowded short plus positive news leads to a squeeze. Alt perps on CDE may be thin.
- **Invalidation:** after 20 paper events, mean return vs BTC is ≥ 0 or the hit rate is < 50%.

### 5.7 Go/no-go
- **30 d:** ≥ 3 events are logged with pre-registered entries. Calendar accuracy is 100%, verified post-event.
- **90 d:** ≥ 8 events. Mean excess vs BTC is ≤ −0.5% (the short profits), after costs. No single loss exceeds the stop plus 2%.

---

## 6. S-FUNDX: BTC funding-extreme overlay and small mean-reversion sleeve (RANK 5)

### 6.1 Spec
```json
{
  "id": "S-FUNDX",
  "mode": ["overlay on S-TREND and S-CARRY-PERP", "tactical sleeve (<=10% capital, $10k only)"],
  "features": "BTC funding percentile vs trailing 180d (Binance and CDE, whichever available; Hyperliquid as data-only cross-check), BTC daily return, OI change",
  "overlay_rule": "if funding >= p90 of trailing 180d for >= 24h: S-TREND BTC weight *= 0.5 for 72h; S-CARRY-PERP allowed (it earns the high funding) but capital cap halved due to BIS crash-predictor finding",
  "sleeve_entry": "funding <= p10 of trailing 180d AND funding recovers to >= 0 AND BTC daily close > prior close (price confirmation) -> long IBIT",
  "sleeve_exit": "24h-72h time exit or -3% stop",
  "venue": "IBIT on Robinhood (cash session only) — US-legal"
}
```

### 6.2 Edge (weak, conflicting)
- [SRC] Memon, Anklesaria-Dalal & Mishra (2026-08, Binance 2019–2026): extreme **negative** funding is followed by **+0.506% 24h BTC return** (HAC +0.49pp, FDR-robust). There is no effect after extreme positive funding.
- [SRC] markettrace (2026-07, 789 days, 6 assets): **BTC top-decile funding → −1.18% median 72h** (n = 37). Bottom decile **predicted nothing** (BTC +0.04%, n = 111).
- [SRC] Gate Research (2026-09): only **"price-confirmed"** deleveraging signals (funding recovery plus an up close) show positive 1–14d returns (+0.35% to +1.04%, n = 22). Not robust.
- [SRC] Arthur Hayes / BitMEX (2017): mean reversion at extremes, with the returns mostly from collecting funding. That was a different era.
- [EST] Standalone expectancy is about 0.2–0.4% per trade at ~3% per-trade SD. With ~30–50 episodes/yr, t ≈ 0.5–1. **It cannot be validated in 90 days.** The value is as a **risk gate**.

### 6.3 Survivability [EST]
- IBIT round trip ≈ 4 bp. At $500 the sleeve (10% = $50) is meaningless, so use it **only as an overlay** (cost 0). At $10k the $1k sleeve × 40 × 0.3% ≈ $120/yr gross with large variance.

### 6.4 Jev questions
| # | Type | Instruction | Code rule |
|---|---|---|---|
| J1 | noul | "Is the funding percentile computed from ≥ 150 of the last 180 days with no venue gaps?" | Veto on no/unsure |
| J2 | choice | "Is the extreme {market_wide, single_venue, data_glitch}?" | Veto unless market_wide |
| J3 | score | "Probability a scheduled macro event in the next 24h dominates" | Veto sleeve entry if ≥ 50 |

### 6.5 Data
- Funding: the same sources as S-CARRY-PERP.
- OI: CFTC COT for CME [SRC exists]. CoinGlass is paid **[UNVERIFIED]**.
- Price: TradingView.

### 6.6 Thesis, bear case, invalidation
- **Thesis:** the long-crowding signal on BTC works because spot demand routes through ETFs, so the marginal perp long is levered [markettrace hypothesis].
- **Bear case:** the published results contradict each other on direction and horizon, so overfitting risk is high.
- **Invalidation:** over the paper period, the overlay-on vs overlay-off S-TREND variant shows no DD reduction.

### 6.7 Go/no-go
- **30 d:** the percentile engine reproduces published BTC top/bottom decile hours within ±10%.
- **90 d:** the A/B overlay reduces S-TREND paper DD or volatility by ≥ 10% without cutting return more than 1pp annualized. Otherwise demote it to a log-only feature.

---

## 7. Rejected / substituted candidates

| Candidate | Why rejected (numbers) |
|---|---|
| (d) Cross-sectional momentum, top-20 | [SRC] Liu-Tsyvinski-Wu (JF 2022): quintile spreads of about 2.5–4.1%/week, but in a 2014–2018 long-short sample that includes small coins. [SRC] Springer FMPM 2025: momentum crashes of −255% in a week from a single coin. [SRC] The Gbadebo 2025 CS result is gross of costs and is worse than TS. [EST] A weekly long-only rotation of 5 coins at retail fees (0.4–0.95%/side, ~50% weekly turnover) costs **≈20–50%/yr** of drag. Shorting alts is feasible only on the few CDE perps. **Dead at $500 and $10k.** The trend-rotation version (Zarattini) is folded into S-TREND as a future universe expansion for $25k+. |
| (e) Stablecoin / on-chain yield | [SRC] Coinbase USDC reward 3.5%, Aave USDC 3.62%, sUSDe 4.67% (depegs recorded during stress), all **at or below the 4.24% T-bill**. They carry smart-contract, issuer and exchange risk plus GENIUS Act rule uncertainty (OCC proposal would extend the yield ban to affiliates; effective by Jan 2027). **Risk-adjusted, T-bills dominate.** Keep them only as a monitored benchmark. |
| (f) Weekend/overnight effect | This pass found no primary or peer-reviewed source with current effect sizes **[UNVERIFIED]**. The ETF leg can't trade weekends, and at RH crypto fees there is no cost room. Not specced. |
| (g) ETF-flow momentum | [SRC] Hekaton/CryptoSlate: flows lag the basis and cannot be linked to hedges. There is no tested edge. It is better used as a Jev J2 context feature. |

---

## 8. Ranked recommendation

1. **S-TREND (paper now):** the only candidate that survives costs at both $500 and $10k, because the ETF implementation drives drag to about 0.2%/yr. It should earn its slot through a desk-harness walk-forward backtest (Sharpe ≥ 0.5), because the desk's earlier momentum backtests failed.
2. **S-CARRY-PERP (collect data now, trade only when gated):** first build the CDE hourly funding recorder. Re-point the S1.1 Carry Desk from Hyperliquid execution assumptions to **CDE + ETF hedge**. Break-even is about 7.2% funding. Not viable at $500.
3. **S-BASIS-DATED (monitor/alert only):** it triggers only when basis ≥ ~7.8%. Today's 5.3% is not enough.
4. **S-UNLOCK (small paper sleeve, $10k context):** the best "uncorrelated-ish" idea, but the evidence conflicts and CDE alt contract specs are unverified.
5. **S-FUNDX (overlay):** use it as a risk gate, not a profit center.

**At $500 the honest answer stands:** none of these beats T-bills with confidence after risk. S-TREND is the only one worth paper-trading at that size, and mainly to build the process. **At $10k**, S-TREND plus gated carry plus a small S-UNLOCK sleeve is a reasonable 90-day paper portfolio.

---

## 9. WHAT COULD I BE WRONG ABOUT?

- **Correlation between strategies.** S-TREND, the S-UNLOCK optional hedge and the S-FUNDX sleeve are all BTC-beta. S-CARRY-PERP and S-BASIS-DATED are the *same* bet: basis and funding have rank correlation +0.75 [SRC tradewize]. They are both highest in euphoric rallies, which the BIS paper says **predict crashes**. In a crash, trend goes flat late (20/100 lag), carry flips negative, and margin calls hit the short-perp leg while the ETF gain sits at another broker. The five strategies may amount to about two independent bets.
- **Regime change.** 2026 already shows it: basis below the bill on 64% of days, funding negative for February–April, USDe down 67%. ETF and institutional arbitrage capital has compressed carry since 2024 [BIS; CME OI down to $7.2B]. Trend literature is dominated by the 2017/2020–21/2024 bull runs. If crypto volatility converges toward equities (BTC RV30 is 42% now), trend Sharpe falls. The GENIUS/CLARITY rules could change stablecoin and exchange economics overnight. The CLARITY Act failed cloture on 2026-09-15 [SRC].
- **Exchange/data failure.** RH returned a **crossed BTC quote** today (bid > ask). Binance public APIs may be geo-blocked from US IPs. No TradingView funding symbol was confirmed. Hyperliquid data use sits in a ToS gray zone for a US person. CDE funding methodology differs from offshore venues, so offshore funding is not a valid proxy. Weekend gaps hit ETFs while crypto moves. FCM and spot balances are in different legal entities at Coinbase (CFM vs CBI) [SRC], and RH is a third. Every kill switch has to assume one venue is down.
- **Jev being confidently wrong.** Jev sees only what the packet shows it. A confident "no data error" on a stale bar lets a bad order through, and a confident false veto on an exit would be dangerous. That is why **exits and kill-switch actions are unvetoable in code** and Jev scores are never used to size up. Log every Jev answer against outcome and compute calibration (Brier score) monthly. If J3-type score questions are uncalibrated (e.g. "40% chance funding turns negative" realizes at 10% or 80%), disable them.
- **Edges already priced in.** Likely for all five. Carry is arbitraged by Ethena, basis funds and CME hedge funds, who have now flipped net long because basis stopped paying. Unlock drift is pre-hedged by market makers 1–4 weeks out [Keyrock], so the T−7 window may be late. Funding-extreme results contradict each other across studies, a classic sign of noise. Published trend Sharpes (>1.5) are almost certainly inflated by selection. **The T-bill at 4.24% is the default winner, and each strategy has to beat it net of costs on the same capital during the paper test.**
- **My own numbers.** Capital-efficiency figures assume ~25% overnight margin (the Coinbase example, not a quote). The ETF expense ratios (~0.25%) and CDE commission (0.05% "beta" rate) may be stale. The contract sizes for CDE alt perps and the nano-ether dated contract are unverified. All [EST] edge ranges are judgment calls, not backtests.

---

## Sources (accessed 2026-09-29 unless noted)

1. BIS WP 1087 "Crypto carry" (Schmeling, Schrimpf, Todorov), 2023-04, rev. to Jul 2024 data: https://www.bis.org/publications/working-paper-1087-crypto-carry and https://www.bis.org/publ/work1087.pdf
2. Liu, Tsyvinski & Wu, "Common Risk Factors in Cryptocurrency", J. Finance 77(2) 2022: https://onlinelibrary.wiley.com/doi/pdfdirect/10.1111/jofi.13119 ; NBER w25882: https://www.nber.org/papers/w25882
3. Zarattini et al., "Catching Crypto Trends", SSRN 5209907 (2025): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907
4. Kang & Ryu, "Time-series momentum and market timing in Bitcoin", Risk Management 28(3), Sep 2026: https://ideas.repec.org/a/pal/risman/v28y2026i3d10.1057_s41283-026-00234-7.html
5. Tripathi, Financial Economics Letters 5(2) 2026: https://www.anserpress.org/journal/fel/5/2/53
6. "Cryptocurrency momentum has (not) its moments", FMPM, 2025-03-27: https://link.springer.com/article/10.1007/s11408-025-00474-9
7. Gbadebo, TS vs CS momentum in crypto (2025): https://www.journals.vu.lt/BATP/en/article/download/44540/42590/138419
8. Franz et al., "Crypto Carry" (perp funding), SSRN 3774118: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3774118
9. Memon, Anklesaria-Dalal & Mishra, "Extreme Perpetual Futures Funding and Subsequent Bitcoin Returns" (2026-08-29): https://exa.ai/library/publication/fsrkl2870s4
10. markettrace, "What happens after extreme funding rates?" (2026-07-13), community/vendor research: https://markettrace.ai/blog/funding-rate-extremes
11. Gate Research, deleveraging and rebound (2026-09-11), exchange research: https://www.gate.com/research/article/gate-research-can-deleveraging-predict-a-rebound-a-time-series-analysis-of-btc-price-oi-funding-and-liquidation-volume
12. BitMEX / Hayes, funding mean reversion (2017-10-12): https://www.bitmex.com/blog/xbtusd-funding-mean-reversion-strategy
13. Funding-carry falsification study (GitHub, community, flagged): https://github.com/Mykola-Quant/funding-rate-carry-falsification
14. Upshift, funding rate arbitrage with Binance API data (2026-09-24): https://www.upshift.finance/blog/funding-rate-arbitrage
15. yieldo.me ETH funding cross-venue (2026-09-24): https://yieldo.me/funding/eth
16. WEEX/OKX funding snapshot (2026-09-23): https://www.weex.com/learn/articles/funding-rate-crypto-what-btc-and-eth-are-paying-right-now-osl7blmgavw13778vmu10yd9
17. Ethena docs, funding risk: https://docs.ethena.fi/protocol-overview/risks/funding-risk ; CoinStats sUSDe analysis (Sep 2026): https://coinstats.app/ai/a/investment-analysis-ethena-staked-usde
18. BlockBeats on Ethena equity perps (2026-09-26): https://en.theblockbeats.news/news/63795
19. tradewize, "How to Read the Basis" (2026-09-13): https://tradewize.io/blog/how-to-read-the-basis
20. CryptoSlate, CME carry vs Treasury (2026-08-11): https://cryptoslate.com/bitcoin-futures-carry-treasury-yield-etf-flows/
21. CryptoInsider, September CME basis (2026-09-19): https://cryptoinsider.media/september-cme-bitcoin-basis-shifts-as-institutional-premiums-diverge/
22. Hekaton, "BTC Spot ETF and the End of the Basis Trade" (2026-03-10): https://hekatontrading.substack.com/p/btc-spot-etf-and-the-end-of-the-basis
23. MEXC News, CME OI 14-month low (2026-04-10): https://www.mexc.co/news/1016135
24. TRESORFX, CME leveraged funds net long (Aug 2026): https://tresorfx.com/article.php?slug=hedge-funds-flip-net-long-bitcoin-on-cme-what-the-structural-short-unwind-means-for-crypto-markets
25. Coinbase Derivatives nano BTC Perp Style spec: https://assets.ctfassets.net/7ca8qfn907uv/36uUBfnoAFKfWNAgfZDepf/a802f97a4feeb9a85fe0845ec07102d3/nano_Bitcoin_Perp_Style_Spec.pdf ; CFTC filing 2025-32: https://www.cftc.gov/filings/ptc/ptc06262524818.pdf
26. Coinbase Derivatives nano Ether Perp Style spec: https://assets.ctfassets.net/7ca8qfn907uv/1rsuwIgOFcofkdd0gKgeCS/4bf41b164aba229d8cded67f7c25393b/nano_Ether_Perp_Style_Spec.pdf
27. Coinbase BIP product page: https://www.coinbase.com/futures/BIP-20DEC30-CDE ; US Perpetual Futures 101: https://www.coinbase.com/learn/futures/us-perpetual-futures-101
28. Coinbase Derivatives fee schedule (eff. 2026-03-02): https://assets.ctfassets.net/o10es7wu5gm1/6LbrWZkWY1BUS67poRlVe/10ca89e22a46b899389678b8f3352c10/Fee_Schedule_3.2.2026.pdf
29. Coinbase futures leverage and margin: https://help.coinbase.com/en/coinbase/trading-and-funding/derivatives/futures-leverage-margin ; Advanced Trade US derivatives API guide: https://coinbase-cloud.mintlify.app/coinbase-app/advanced-trade-apis/guides/futures
30. Coinbase Exchange fees: https://help.coinbase.com/en/exchange/trading-and-funding/exchange-fees ; Coinbase Advanced Perpetuals (non-US only): https://www.coinbase.com/advanced-perpetuals
31. Robinhood crypto order routing: https://robinhood.com/us/en/support/articles/crypto-order-routing/ ; RHC fee schedule: https://cdn.robinhood.com/assets/robinhood/legal/rhc-fee-schedule.pdf
32. Hyperliquid Terms (US persons restricted): https://app.hyperliquid.xyz/terms ; HypeBasis verification (2026-08-26): https://hypebasis.io/united-states ; hyperliquidguide (2026-03-02, notes the CFTC KalshiEX BTC perp approval 2026-05-29): https://hyperliquidguide.com/privacy/hyperliquid-us-availability
33. Keyrock, 16,000+ token unlocks (2024-12-05): https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/
34. Animoca Research via Smartkarma (2025-01-08): https://www.smartkarma.com/insights/the-impact-of-token-unlock-events-on-cryptocurrency-prices-an-empirical-analysis
35. unlocks.app analysis (2024-03-08): https://insights.unlocks.app/unlock-analysis-project-type/ ; Messari summary via Gate Learn (2024-09-25): https://www.gate.com/learn/articles/trading-token-unlocks-essential-findings/4226
36. CRS, "The Stablecoin Yield Debate": https://www.congress.gov/crs_external_products/IF/PDF/IF13174/IF13174.2.pdf ; GENIUS Act P.L. 119-27: https://www.congress.gov/119/plaws/publ27/PLAW-119publ27.htm
37. Perkins Coie on OCC GENIUS proposal (2026-03-04): https://www.ashurstperkinscoie.com/en/insights/stablecoin-interest-yield-and-rewards-occ-proposes-sweeping-regulations-under-the-genius-act/ ; Forbes (2026-05-20): https://www.forbes.com/sites/digital-assets/2026/05/20/the-genius-act-stablecoin-yield-ban-has-a-coinbase-shaped-hole/ ; Baker Botts (2026-05): https://www.bakerbotts.com/thought-leadership/publications/2026/may/genius-act-proposal-examining-the-impact-of-proposed-regulatory-framework
38. Live connector pulls (2026-09-29): Robinhood `get_crypto_quotes` (BTC/ETH/SOL), `get_equity_quotes` (IBIT/ETHA/BSOL/FBTC); TradingView `mcp-tv-get-ohlcv` (COINBASE:BTCUSD 400/130 bars, ETHUSD/SOLUSD 101 bars, BINANCE:BTCUSDT.P); Alpha Vantage `TREASURY_YIELD` 3month daily (4.24% on 2026-09-25).

Community/vendor sources (markettrace, the GitHub studies, yieldo, WEEX, CoinStats, TRESORFX, MEXC, Gate) are flagged as lower-grade evidence. Bigdata.com (https://bigdata.com) was loaded but not needed for this pass; it is the recommended feed for the Jev J2 news packets.

---

## 10. Implementation cards (top 3). Paper books of $500 and $10k

**Common daily inputs.** At 20:05 UTC pull `TREASURY_YIELD(maturity=3month, interval=daily)` from Alpha Vantage, which gives the hurdle `TB`. During the US cash session, read `get_equity_quotes([IBIT,ETHA,BSOL])` from Robinhood (read-only).

**Guards on all three strategies:**
- Reject any quote where `bid<=0`, `ask<=0` or `bid>ask`. Today's RH BTC crypto quote was crossed.
- Reject any bar whose timestamp is more than 26h old.
- Jev can only veto. Exits and kills bypass Jev.

### Card A: S-TREND
```
inputs (daily, 20:05 UTC): TV mcp-tv-get-ohlcv symbol in {COINBASE:BTCUSD, COINBASE:ETHUSD, COINBASE:SOLUSD}, interval=1D, count=130
for each asset i:
  sma20=mean(close[-20:]); sma100=mean(close[-100:]); rv30=stdev(logret[-30:])*sqrt(365)
  on_i = (sma20>sma100 on last 2 closes) ; off_i = (sma20<sma100 on last 2 closes)
  trail_stop_i = close < 0.80*max(close since entry)
  target_w_i = (on_i and not trail_stop_i) ? sleeve_i*min(1, 0.30/rv30) : 0   # sleeve BTC .50 ETH .30 SOL .20
  if off_i or trail_stop_i: target_w_i = 0
  trade ETF proxy (IBIT/ETHA/BSOL) next cash session only if |target-held| > 0.20*held or target crosses 0; limit at mid+1 tick
kill: strategy equity DD >= 20% from peak -> flat all, human review
```
Sizing today (all LONG, RV30 BTC .416 / ETH .443 / SOL .636):
- **$500 book:** IBIT $180, ETHA $102, BSOL $47, cash $171.
- **$10k book:** IBIT $3,600, ETHA $2,040, BSOL $940, cash $3,420.

Jev:
- J1 noul "data error?". Veto if yes or unsure.
- J2 choice {none, macro_scheduled, crypto_structural, unknown}. Veto new entries if crypto_structural.
- J3 score "order-mistake probability". Veto if >= 20.

### Card B: S-CARRY-PERP (US-legal: long ETF + short CDE perp-style)
```
inputs hourly: CDE BIP/ETP funding + mark via Coinbase Advanced Trade API US-derivatives endpoints [paths UNVERIFIED - read docs]
               cross-check (data only): Binance GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT (may 451-block US IPs)
               Hyperliquid POST https://api.hyperliquid.xyz/info {"type":"fundingHistory","coin":"BTC","startTime":<ms>} (ToS restricts US persons; data use = gray area, flag)
F7 = mean(CDE hourly funding, 7d)*24*365 ; F30 likewise
hurdle = TB + 3.0   # pp; today 7.24%
ENTER if F7 >= hurdle and F30 >= hurdle-1 and no position and weekday cash session
   ETF_sh = round(n_contracts*0.01*BTC_px/IBIT_px)   # 1 BIP ~= 17.7 IBIT today; ETH: 1 ETP ~= 13.3 ETHA
EXIT  if F7 < TB or funding<0 for 3 consecutive days or margin_ratio alert or |hedge drift|>3%
REBAL if |ETF_BTC - perp_BTC| / perp_BTC > 3%
```
Sizing:
- **$500:** BTC is infeasible (1 unit needs ≈$1,330). As a data-only paper unit, use 1 ETP short + 13 ETHA (≈$262) with $238 as margin and buffer. At 5% funding this earns about $12/yr, against $21/yr from T-bills, so treat it as a test only.
- **$10k:** short 7 BIP + long 124 IBIT (≈$5.83k notional), with ≈$3.5k margin/buffer at CFM and $0.6k spare. Break-even vs T-bills is at F ≈ 7.2%. At F = 12% it earns about +$256/yr over T-bills.

Jev:
- J1 noul "legs match within 3%?". Veto if no or unsure.
- J2 choice {broad_positive, venue_specific_only, turning_negative, unclear}. Veto unless broad_positive.
- J3 score "P(funding<0 within 14d)". Veto entry if >= 40.
- J4 noul "venue/regulatory event or ETF prem/disc > 0.5%?". Veto if yes or unsure.

### Card C: S-BASIS-DATED (alert-first)
```
inputs daily 20:00 UTC (4pm ET match): CDE nano BTC dated (BIT, 0.01 BTC) mark via Coinbase Advanced Trade API [UNVERIFIED path];
       CME MBT settlement (CME bulletin; TV CME:MBT1! [UNVERIFIED]); spot = TV COINBASE:BTCUSD 1D close
B = (F/S - 1) * 365/DTE ; cost_ann = 0.16% * 365/DTE ; net = B - 0.25 - cost_ann
ENTER if net - TB >= 3.5 and 30 <= DTE <= 120      # today B~5.3% -> NO
EXIT  at expiry (cash settle) or if >= 80% of locked basis captured early; margin alert -> reduce
```
Sizing:
- **$500:** log-only; no feasible BTC unit.
- **$10k:** when triggered, short 7 BIT + long 124 IBIT, with ≈$3.5k margin reserve.

Jev:
- J1 noul "time-matched prices and DTE correct?". Veto if no or unsure.
- J2 score "artifact probability". Veto if >= 25.
- J3 choice {broad_leverage_demand, single_venue_squeeze, data_error, unclear}. Veto unless broad_leverage_demand.
