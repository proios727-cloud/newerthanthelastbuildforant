# Review 2026-11-18  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1197 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 444; accuracy 60.8%; mean Brier 0.616 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 10 | 15 | 0 |
| CHOPPY | 113 | 260 | 37 |
| PANIC | 2 | 7 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 36 | +0.18 | +6.64 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 8 | 1.104 | 8.83 |
| 0.45 | 4 | 1.435 | 5.74 |
| 0.50 | 3 | 1.357 | 4.07 |
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

## Question version in use: 6
Worst regime misses written to review-2026-11-18-packet.json for question rewriting.
