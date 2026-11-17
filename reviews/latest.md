# Review 2026-11-17  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1076 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 348; accuracy 62.9%; mean Brier 0.600 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 9 | 15 | 0 |
| CHOPPY | 70 | 210 | 35 |
| PANIC | 2 | 7 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 28 | -0.05 | -1.30 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 4 | 0.892 | 3.57 |
| 0.45 | 2 | 1.594 | 3.19 |
| 0.50 | 1 | 1.522 | 1.52 |
| 0.55 | 0 | — | 0 |
| 0.60 | 0 | — | 0 |
| 0.65 | 0 | — | 0 |
| 0.70 | 0 | — | 0 |
| 0.75 | 0 | — | 0 |
| 0.80 | 0 | — | 0 |
| 0.85 | 0 | — | 0 |
| 0.90 | 0 | — | 0 |

## Realized R by entry type
| entry | n | avg R |
|---|---|---|

## Threshold changes: none (current take 0.65, regime 0.6)

## Question version in use: 5
Worst regime misses written to review-2026-11-17-packet.json for question rewriting.
