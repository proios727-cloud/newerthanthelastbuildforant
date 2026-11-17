# Desk ledger — running journal

As of 2026-11-17. Rebuilt from the append-only journals after each close; never edited by hand.

## Net by book

| Book | Trades | Closed | Wins / losses | Realized | Open (marked) | Net |
|---|---|---|---|---|---|---|
| Real account | 2 | 2 | 0 / 2 | −$198 | +$0 | −$198 |
| Paper: other | 1 | 0 | 0 / 0 | +$0 | +$0 | +$0 |
| Paper: premium screener | 3 | 3 | 2 / 1 | +$443 | +$0 | +$443 |
| Paper: swing buyer | 1 | 0 | 0 / 0 | +$0 | +$46 | +$46 |
| **All books** | 7 | | | **+$245** | **+$46** | **+$291** |

Heat Seeker (scored in R, no dollars): 27 signals logged, 22 no-trade, 5 not triggered, **0 triggered**, total +0.00 R.

## Every trade

| Opened | Book | Contract | Side | Entry | Exit / mark | Status | P&L | Note |
|---|---|---|---|---|---|---|---|---|
| 2026-11-02 | Paper: premium screener | SPY 2026-12-11 720 put | short | 6.03 | 12.38 | closed 2026-11-06 | −$635 | stop: debit 12.38 >= 2x credit (12.06) |
| 2026-11-05 | Paper: premium screener | QQQ 2026-12-11 600 put | short | 9.69 | 4.27 | closed 2026-11-09 | +$542 | take profit: debit 4.27 <= 50% of credit (4.85) |
| 2026-11-05 | Paper: premium screener | TSLA 2026-12-11 300 put | short | 7.80 | 2.44 | closed 2026-11-09 | +$536 | take profit: debit 2.44 <= 50% of credit (3.90) |
| 2026-11-06 | Paper: other | PFE 2028-01-21 30 call | long | 3.03 | — | open | — | no quote snapshot |
| 2026-11-09 | Real account | IWM 2026-11-10 287 call | long | 0.23 | 0.00 | closed 2026-11-10 | −$23 | expired worthless: IWM well below 287 |
| 2026-11-09 | Real account | QQQ 2026-11-10 685 call | long | 1.75 | 0.00 | closed 2026-11-10 | −$175 | expired worthless: QQQ closed 674.81 < 685 |
| 2026-11-12 | Paper: swing buyer | KO 2026-12-18 100 call | long | 1.62 | 2.08 | open | +$46 |  |
