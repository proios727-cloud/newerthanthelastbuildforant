# Review 2026-11-23  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1781 records); 3 fork(s) from concurrent writes at line(s) 1322, 1445, 1567, nothing missing
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 639; accuracy 63.4%; mean Brier 0.596 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 12 | 12 | 9 |
| CHOPPY | 172 | 390 | 39 |
| PANIC | 0 | 2 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 49 | +0.01 | +0.45 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 9 | 0.59 | 5.31 |
| 0.45 | 5 | 0.443 | 2.22 |
| 0.50 | 4 | 0.138 | 0.55 |
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
Worst regime misses written to review-2026-11-23-packet.json for question rewriting.
