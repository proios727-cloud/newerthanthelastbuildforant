# Review 2026-11-04  (BTCUSDT 15m, last 168h)

- Log integrity: OK (97 records)
- Drex errors: {'regime': 1}
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 69; accuracy 34.8%; mean Brier 1.148 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 7 | 35 | 7 |
| CHOPPY | 3 | 17 | 0 |
| PANIC | 0 | 0 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 1 | -1.00 | -1.00 |

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

## Question version in use: 1
Worst regime misses written to review-2026-11-04-packet.json for question rewriting.
