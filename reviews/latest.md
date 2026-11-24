# Review 2026-11-24  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1888 records); 3 fork(s) from concurrent writes at line(s) 1322, 1445, 1567, nothing missing
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 638; accuracy 61.4%; mean Brier 0.624 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 12 | 16 | 11 |
| CHOPPY | 176 | 377 | 41 |
| PANIC | 0 | 2 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 42 | -0.21 | -8.67 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 6 | 0.166 | 0.99 |
| 0.45 | 3 | -0.241 | -0.72 |
| 0.50 | 3 | -0.241 | -0.72 |
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

## Threshold changes: none (current take 0.45, regime 0.6)

## Question version in use: 6
Worst regime misses written to review-2026-11-24-packet.json for question rewriting.
