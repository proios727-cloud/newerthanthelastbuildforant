# Verdict: ETH daily trend breakout as crash protection

**Fails the pre-registered bar on 2 of 5 tests, so it is not adopted.** Under `RULE.md`, that closes the 20/10 breakout
family on crypto. The behaviour it was meant to show is strong, though, and is recorded here plainly.

- **The crash protection held on data the 4-hour study never touched.** Over 2017–2023 the worst drawdown was −34%
  against buy and hold's −94%. Return per unit of drawdown (Calmar) was 1.60 against 0.40.
- **It lost far less in every named crash:**
  - 2018 bear: +1% against −82%;
  - March 2020: −22% against −54%;
  - 2022 bear: −10% against −68%.
- **BTC confirms the pattern:** worst drawdown −43% against −83%, and Calmar 0.74 against 0.52.
- **But there are only 18 trades.** The average trade's t-stat is 1.47, so the evidence is thin. ETH was also in the
  market 28% of the time, just under the 30% minimum. Both are failures, and the bar is not moved after the fact.

Rule fixed before the data was fetched: `RULE.md`. Run it with:
```bash
python3 -m chart breakout chart/data/crypto/1D/ETHUSDT.csv chart/data/crypto/1D/BTCUSDT.csv --daily --end 2023-12-31 --window 2018bear:2018-01-01:2018-12-31 --window covid:2020-02-15:2020-03-31 --window 2022bear:2022-01-01:2022-12-31
```
Full tables: `results_2017_2023.md` (primary) and `results_full.md`.

## Evidence: primary window, 2017-08-17 → 2023-12-31, 10 bp fee + 10 bp slippage per side

| | ETH strategy | ETH hold | BTC strategy | BTC hold |
|---|---|---|---|---|
| Total return | **+1,452%** | +658% | +480% | **+892%** |
| CAGR | **+53.7%** | +37.4% | +31.7% | **+43.3%** |
| Max drawdown | **−33.6%** | −94.0% | **−42.7%** | −83.2% |
| CAGR ÷ max DD | **1.60** | 0.40 | **0.74** | 0.52 |
| 2018 bear | **+1.2%** | −82.1% | **−13.8%** | −73.0% |
| Mar 2020 crash | **−21.6%** | −53.5% | **−10.1%** | −38.0% |
| 2022 bear | **−9.5%** | −67.5% | **−8.2%** | −64.2% |
| Trades · win · t-stat | 18 · 56% · 1.47 | | 23 · 43% · 1.11 | |
| Time in market | 28% | 100% | 29% | 100% |
| At 25+25 bp | +1,308% | | +413% | |

The years it lags are bull markets: in 2017, 2020 and 2023 it was in the market only part of the time, and holding did
far better. It pays for its crash protection with missed rallies, the same trade-off as the repo's SPY trend overlay
(`research/trend-overlay/VERDICT.md`).

**2024 → 2026-11-01**, a period the 4-hour study had already seen (informational only): ETH +23.6% against −0.3% for
holding; BTC +55.3% against +85.3%.

## Against the pass bar (ETH, 2017–2023)

| Test | Result | |
|---|---|---|
| 1. Max drawdown ≥ ⅓ shallower than holding | −34% vs −94% | pass |
| 2. Calmar ≥ holding's | 1.60 vs 0.40 | pass |
| 3. In the market ≥ 30% of the time | 28% | **fail** |
| 4. Positive at 10+10 bp, with ≥ 30 trades | +1,452%, but only **18 trades** | **fail** |
| 5. Smaller loss in each named crash | 3 of 3 | pass |
| BTC confirmation (tests 1 and 2) | −43% vs −83%; 0.74 vs 0.52 | pass |

## What this means
- Daily bars plus a trend filter cut crypto drawdowns roughly in half across 2018, 2020 and 2022, on both coins. That
  is consistent, but it rests on fewer than 20 trades per coin. A handful of big trend years (2020, 2021) make most of
  the return.
- It is **not a day-trading strategy.** Trades last weeks, and it is in the market about a quarter of the time.
- Under the pre-registered rule this line of research closes. Logging it as a paper regime flag (like the SPY overlay)
  would mean overriding that rule. That is a decision for the account owner, not for the backtest.
