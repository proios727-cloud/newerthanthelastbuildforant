# Review 2026-11-19  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1321 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 540; accuracy 62.6%; mean Brier 0.593 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 15 | 17 | 0 |
| CHOPPY | 138 | 320 | 38 |
| PANIC | 2 | 7 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 42 | +0.02 | +0.64 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 10 | 0.683 | 6.83 |
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

## Threshold changes: {'take_threshold': 0.6} (current take 0.65, regime 0.6)

## Question version in use: 6
Worst regime misses written to review-2026-11-19-packet.json for question rewriting.
