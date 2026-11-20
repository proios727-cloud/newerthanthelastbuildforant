# Review 2026-11-20  (BTCUSDT 15m, last 168h)

- Log integrity: BROKEN at line 1322 (1322 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 636; accuracy 62.1%; mean Brier 0.600 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 19 | 24 | 9 |
| CHOPPY | 154 | 373 | 43 |
| PANIC | 2 | 9 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 50 | -0.02 | -0.85 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 11 | 0.53 | 5.83 |
| 0.45 | 6 | 0.623 | 3.74 |
| 0.50 | 5 | 0.414 | 2.07 |
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

## Threshold changes: {'take_threshold': 0.55} (current take 0.6, regime 0.6)

## Question version in use: 6
Worst regime misses written to review-2026-11-20-packet.json for question rewriting.
