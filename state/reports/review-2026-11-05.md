# Review 2026-11-05  (BTCUSDT 15m, last 168h)

- Log integrity: OK (198 records)
- Drex errors: {'regime': 3}
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 147; accuracy 37.4%; mean Brier 1.110 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 11 | 45 | 27 |
| CHOPPY | 5 | 37 | 12 |
| PANIC | 2 | 1 | 7 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 2 | +0.12 | +0.24 |

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

## Question version in use: 2
Worst regime misses written to review-2026-11-05-packet.json for question rewriting.
