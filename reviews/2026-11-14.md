# Review 2026-11-14  (BTCUSDT 15m, last 168h)

- Log integrity: OK (701 records)
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 219; accuracy 57.1%; mean Brier 0.709 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 11 | 21 | 7 |
| CHOPPY | 38 | 114 | 25 |
| PANIC | 1 | 2 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 5 | -0.40 | -1.99 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 1 | -1.0 | -1.0 |
| 0.45 | 1 | -1.0 | -1.0 |
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
Worst regime misses written to review-2026-11-14-packet.json for question rewriting.
