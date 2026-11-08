# Review 2026-11-08  (BTCUSDT 15m, last 168h)

- Log integrity: OK (490 records)
- Drex errors: {'regime': 3}
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 405; accuracy 60.5%; mean Brier 0.681 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 44 | 70 | 12 |
| CHOPPY | 45 | 198 | 22 |
| PANIC | 7 | 4 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 9 | -0.27 | -2.45 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 0 | — | 0 |
| 0.45 | 0 | — | 0 |
| 0.50 | 0 | — | 0 |
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

## Question version in use: 4
Worst regime misses written to review-2026-11-08-packet.json for question rewriting.
