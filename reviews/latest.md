# Review 2026-11-22  (BTCUSDT 15m, last 168h)

- Log integrity: OK (1688 records); 3 fork(s) from concurrent writes at line(s) 1322, 1445, 1567, nothing missing
- Drex errors: none
- No closed trades

## Regime calls vs realized (next 12 candles)
Scored 659; accuracy 65.7%; mean Brier 0.567 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 11 | 12 | 9 |
| CHOPPY | 163 | 419 | 36 |
| PANIC | 1 | 5 | 3 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 52 | +0.20 | +10.30 |

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

## Threshold changes: {'take_threshold': 0.45} (current take 0.5, regime 0.6)

## Question version in use: 6
Worst regime misses written to review-2026-11-22-packet.json for question rewriting.
