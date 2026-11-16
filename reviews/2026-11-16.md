# Review 2026-11-16  (BTCUSDT 15m, last 168h)

- Log integrity: OK (957 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 338; accuracy 58.9%; mean Brier 0.638 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 9 | 25 | 0 |
| CHOPPY | 80 | 190 | 25 |
| PANIC | 2 | 7 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 23 | -0.44 | -10.15 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 3 | -0.159 | -0.48 |
| 0.45 | 2 | 0.261 | 0.52 |
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
Worst regime misses written to review-2026-11-16-packet.json for question rewriting.
