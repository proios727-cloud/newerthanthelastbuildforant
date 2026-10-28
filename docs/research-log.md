# Research log: chart engine and strategy research

Findings in the order they were made. Later work corrected several earlier claims; corrections are noted inline and the
current conclusions are in the README ("Current conclusions"). Kept so the reasoning and its mistakes stay auditable.

## Oct 2026: daily scan (Oct 2024 → Oct 2026), then the long-history and total-return corrections

**Rolling scan, 25 out-of-sample months (Oct 2024 → Oct 2026), 128 tests across both universes.** A strategy is judged two ways: as a *return candidate* (beats holding on return and Sharpe, and wins at least half the months) and as a *risk filter* (a drawdown at least a third shallower than holding, with an equal or better Calmar ratio).

- **ETF momentum rotation: over two decades it cut drawdowns, not returns.** On weekly total-return bars from 2005 to 2026 (`chart longrun`), the rule made 9.0%/yr against 10.0% for holding the basket. Its worst drawdown was −28% against −46%, almost all of that in 2008. From 2018 to 2026 it made 8.3% against 12.8%. The daily tests below are price-only, so they miss the basket's roughly 1.9%/yr of dividends. On total-return daily bars, the 2023–26 replay edge shrinks from +1.8 to +1.2 points a year, so about a third of it was missing dividends. It stays a paper-only research log, with a 200-day trend-filter variant logged next to it (9.5% against 10.0%, worst drawdown −18%). See `docs/rotation-sleeve.md`.
- **The 2023–26 daily rotation tests:** the headline number was mostly luck, and a smaller edge survived stress testing.
  - The +28.8%/yr winner (vs +9.7% for the equal-weight basket) leaned on a 5-day lookback. Shifting its rebalance day by 1–4 sessions moved the result anywhere from −0.4% to +32%/yr, and without XLK the edge disappears.
  - What survives is the textbook rule: **60-day momentum, monthly rebalance, hold the top 3**, trading only the funds that change. Across all 21 possible rebalance days it made a median +13.8%/yr (worst +8.0%) vs +9.7% for the basket, with a similar drawdown (median −12.7% vs −13.5%), a Sharpe of 0.96 vs 0.85, and a better Calmar ratio on 16 of 21 days.
  - That edge thins at 10 bp fees plus 10 bp slippage (+12.0%/yr, about the same Sharpe as the basket) and goes at 25+25 bp. It also needs GLD and TLT in the basket: on sectors only it doesn't beat holding.
  - Verdict: a modest, cost-sensitive edge worth forward paper-testing as a rule, not a deployable result.
  - **Live-calendar version** (decide on the first session of each month, fill next open; `chart forward rotation-replay`): +15.2%/yr vs +13.5% for the basket before costs, from Jan 2024 to Oct 2026. It was ahead in 17 of 33 months, with a −7.5% vs −5.7% worst month-end drawdown. About 1.2 of 3 holdings change each month, so the net edge is about +1.4 points/yr at low costs and about zero at 10+10 bp. The daily `chart-forward` job now logs this rule's decisions before each fill. The decision memo is `docs/rotation-sleeve.md`. Each decision also becomes paper order tickets (`chart forward rotation-tickets`). The tickets trade only the funds that change, at 5% of NAV each, and are for desk review only.
  - **Tested and rejected:** hysteresis (keep a fund while it ranks in the top 4 or 5) barely cut trades and cost 3–6 points/yr. A basket trend filter trimmed drawdown at 150 days but not at 200, so the gain depends on the setting. The rule is unchanged (table in the memo and on the scorecard).
- **Over 20+ years, trend filters cut drawdowns at a cost in return.** This is the general pattern, not any one pairing. On weekly total-return bars (`chart longrun --strategies`), SMA cross, Donchian and MACD each qualify as risk filters on 3–5 of 13 ETFs and on SPY, QQQ, AAPL, NVDA, AMD and IWM. Every one gives up 1–14 points a year. The 2023–26 SMA-cross list mostly fails: XLB (0.4%/yr vs 8.9%), XLI and IWM (0.2% vs 8.8%) fail, and only XLC passes (history from 2020). On total-return daily bars, the 2023–26 list itself changes: XLB and XLC drop out and XLV comes in. Across 120 weekly tests, no strategy beats holding the desk stocks, and the two ETF "candidates" (mean reversion on XLRE) are about what chance produces.
- **The earlier MACD-trend risk filters on TSLA and AMD didn't hold up on the ETFs.** MACD-trend matched holding's Calmar on only 1 of 13, so treat those two as likely luck.
- **On the 8 desk stocks, nothing beats holding.** They were picked with hindsight in a strong bull market.

Two years of one market regime is a short test; the weekly long history and the forward paper test are the checks that count.

## Oct 2026: desk-level trend overlay

SPY above its 10-month average, else cash, on weekly total return from 2000: a risk filter at every setting (worst
drawdown −21% vs −55%) but about 6 points a year behind holding since 2009. Full verdict: `research/trend-overlay/VERDICT.md`.

## Corrections made along the way

- **The +28.8%/yr rotation headline:** luck. It came from a 5-day lookback and the choice of rebalance day.
- **"The rotation edge was mostly missing dividends":** wrong. On total-return daily bars it was about a third
  (+1.8 → +1.2 points a year over 2023–26). Over two decades, the rule trails the basket anyway.
- **"SMA cross works as a risk filter on IWM, XLC, XLI, XLB":** a 2023–26 result. Over 20+ years XLB, XLI and IWM fail,
  and on total-return daily data XLB and XLC drop out.
- **MACD-trend filters on TSLA and AMD:** likely luck. They matched holding's Calmar on only 1 of 13 ETFs.
