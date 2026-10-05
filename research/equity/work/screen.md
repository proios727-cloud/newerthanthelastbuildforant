# S&P 500 Quality-at-a-Discount Screen

As of 2026-10-05. Universe: TradingView "S&P 500" index filter, 504 lines. Sole data source: TradingView screener (RH_TV_HFT). Raw data: `work/tv_raw_2026-10-05.json`.

## Thresholds
- **fcf**: free_cash_flow_ttm > 0
- **quality**: return_on_invested_capital > sector median OR return_on_equity > sector median (TV sector classification, medians over all S&P 500 members in sector, nulls excluded)
- **valuation**: any of P/E TTM, non-GAAP forward P/E (next FY), EV/EBIT TTM <= 40th percentile of positive values within sector (linear interpolation); negative/missing multiples ignored
- **leverage**: net_debt_fq / ebitda_ttm < 3.0; net cash passes; skipped for TV sector "Finance" (includes REITs, e.g. SBAC)
- **discount**: close / price_52_week_high - 1 <= -10%
- **catalyst**: 0 <= earnings_release_next_date - 2026-10-05 <= 60 days
- **ranking**: score = (ROIC, else ROE) / |sector median ROIC| + (pct below 52w high)/20; GOOG dropped as duplicate share class of GOOGL

## Shortlist (all 6 filters passed)

|#|Ticker|Company|CIK|Sector (TV)|% vs 52wH|Next EPS (days)|FCF TTM|ROIC%|ROE%|P/E TTM|Fwd P/E|EV/EBIT|ND/EBITDA|
|-|-|-|-|-|-|-|-|-|-|-|-|-|-|
|1|BKNG|Booking Holdings Inc|1075531*|Consumer Services|-28.5|2026-11-04 (30)|9.54B|74.9|UNAVAILABLE|17.5|15.1|12.3|0.30|
|2|WDC|Western Digital Corporation|106040*|Electronic Technology|-44.9|2026-10-22 (17)|3.51B|108.9|131.4|18.2|21.6|34.5|-0.08|
|3|APP|Applovin Corp|1751008*|Technology Services|-61.4|2026-11-11 (37)|4.53B|77.7|203.7|21.9|18.1|18.0|0.08|
|4|SNDK|Sandisk Corp|2023554*|Electronic Technology|-27.2|2026-10-29 (24)|11.49B|84.2|91.6|23.5|8.1|19.8|-0.36|
|5|GEV|GE Vernova|1996810*|Producer Manufacturing|-17.0|2026-10-28 (23)|12.44B|80.7|91.5|28.4|32.6|116.0|-3.02|
|6|CF|CF Industries Holdings|UNAVAILABLE|Process Industries|-17.1|2026-11-04 (30)|1.91B|24.1|39.2|8.7|7.9|6.9|0.28|
|7|ALL|The Allstate Corporation|899051*|Finance|-19.1|2026-11-04 (30)|12.25B|36.6|46.1|4.5|6.3|UNAVAILABLE|skip (fin)|
|8|AMP|Ameriprise Financial|UNAVAILABLE|Finance|-13.8|2026-10-29 (24)|8.22B|32.1|63.4|11.9|10.6|7.4|skip (fin)|
|9|ERIE|Erie Indemnity|UNAVAILABLE|Finance|-33.6|2026-10-22 (17)|0.55B|24.8|24.8|20.0|17.3|13.4|skip (fin)|
|10|ZTS|Zoetis|UNAVAILABLE|Health Technology|-52.1|2026-11-05 (31)|2.37B|22.9|64.4|11.7|11.4|10.3|1.86|
|11|EXPE|Expedia Group|UNAVAILABLE|Consumer Services|-23.3|2026-10-29 (24)|4.46B|32.7|199.1|16.4|12.5|11.1|-1.09|
|12|PGR|Progressive Corp|UNAVAILABLE|Finance|-14.2|2026-10-08 (3)|15.95B|28.8|34.9|10.6|11.6|UNAVAILABLE|skip (fin)|
|13|EME|EMCOR Group|UNAVAILABLE|Industrial Services|-17.2|2026-10-22 (17)|1.17B|35.3|40.4|24.4|23.9|19.3|-0.19|
|14|PODD|Insulet Corp|UNAVAILABLE|Health Technology|-61.9|2026-11-04 (30)|0.29B|15.8|26.0|26.8|20.8|19.0|0.65|
|15|LULU|lululemon athletica|UNAVAILABLE|Consumer Non-Durables|-59.1|2026-12-03 (59)|1.35B|22.8|30.9|7.6|9.6|5.7|0.30|

\* CIK reported by Alpha Vantage COMPANY_OVERVIEW; NOT confirmed on EDGAR (blocked). Company names without a CIK are unverified labels.

## Sector thresholds

|Sector|n|ROIC med|ROE med|P/E p40|Fwd P/E p40|EV/EBIT p40|
|-|-|-|-|-|-|-|
|Commercial Services|15|13.6|19.8|24.3|16.1|15.1|
|Communications|4|6.3|16.8|11.1|9.4|12.7|
|Consumer Durables|11|9.8|12.8|16.0|14.8|13.0|
|Consumer Non-Durables|28|14.1|22.5|20.0|14.4|14.1|
|Consumer Services|28|8.7|14.9|17.1|15.4|14.7|
|Distribution Services|9|21.4|37.5|24.5|17.8|17.4|
|Electronic Technology|57|14.1|21.9|33.8|23.8|27.7|
|Energy Minerals|14|10.8|14.5|15.1|9.2|12.0|
|Finance|96|6.9|12.6|14.8|13.6|21.5|
|Health Services|11|7.9|14.4|14.9|13.1|12.4|
|Health Technology|42|9.9|13.8|29.4|18.4|20.5|
|Industrial Services|11|9.1|17.3|24.4|21.5|19.3|
|Miscellaneous|1|36.4|36.6|44.3|37.3|35.3|
|Non-Energy Minerals|7|10.3|15.3|16.8|14.2|16.6|
|Process Industries|20|4.3|7.6|19.0|15.5|16.0|
|Producer Manufacturing|33|13.3|20.9|28.5|22.1|21.6|
|Retail Trade|23|21.4|41.1|19.4|16.3|15.7|
|Technology Services|47|16.9|27.2|20.2|16.9|18.7|
|Transportation|15|10.8|24.4|23.1|21.0|19.4|
|Utilities|32|4.1|10.1|19.4|16.9|20.9|

## Data gaps
- 98 of 504 passed all six; 13 constituents had at least one filter undeterminable (UNAVAILABLE) and were excluded: AMCR (earnings_within_60d), AZO (fcf_positive), CI (net_debt_ebitda_lt3), CNC (net_debt_ebitda_lt3), COIN (valuation_bottom40_sector), ELV (net_debt_ebitda_lt3), FDXF (fcf_positive/net_debt_ebitda_lt3), HONA (fcf_positive/quality_roic_or_roe_gt_sector_median/valuation_bottom40_sector/net_debt_ebitda_lt3), HUM (net_debt_ebitda_lt3), MRNA (valuation_bottom40_sector), UNH (net_debt_ebitda_lt3), VRSN (quality_roic_or_roe_gt_sector_median), VYLR (fcf_positive/quality_roic_or_roe_gt_sector_median/valuation_bottom40_sector/net_debt_ebitda_lt3/earnings_within_60d)
- Field null counts across 504: {'return_on_equity': 33, 'enterprise_value_to_ebit_ttm': 49, 'ebitda_ttm': 44, 'price_earnings_ttm': 30, 'non_gaap_price_to_earnings_per_share_forecast_next_fy': 10, 'earnings_release_next_date': 2, 'free_cash_flow_ttm': 4, 'return_on_invested_capital': 3, 'net_debt_fq': 1}
- SEC EDGAR (www.sec.gov, data.sec.gov) blocked by egress proxy: no CIK confirmed on EDGAR; no EDGAR cross-check of FCF/debt
- Alpha Vantage free key hit 25/day limit after 6 successful COMPANY_OVERVIEW calls; CIK UNAVAILABLE for 9 of 15; EARNINGS/CASH_FLOW/BALANCE_SHEET/GLOBAL_QUOTE not pulled
- All filter values are single-source (TradingView); not independently verified
- TV return_on_equity/return_on_invested_capital are TTM-basis per TV defaults; *_ttm column variants returned null
