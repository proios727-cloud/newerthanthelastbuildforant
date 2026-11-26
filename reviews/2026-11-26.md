# Review 2026-11-26  (BTCUSDT 15m, last 168h)

- Log integrity: OK (2126 records); 3 fork(s) from concurrent writes at line(s) 1322, 1445, 1567, nothing missing
- Drex errors: none
- Paper P&L (closed): -19.96 over 1 trades, win rate 0%

## Regime calls vs realized (next 12 candles)
Scored 638; accuracy 61.6%; mean Brier 0.630 (lower is better, 0.667 = uniform)

| called \ actual | TRENDING | CHOPPY | PANIC |
|---|---|---|---|
| TRENDING | 7 | 19 | 12 |
| CHOPPY | 148 | 386 | 62 |
| PANIC | 1 | 3 | 0 |

## TAKE / SKIP replay (resolved signals)
| decision | n | avg R | total R |
|---|---|---|---|
| SKIP | 37 | -0.39 | -14.37 |
| TAKE | 1 | -1.00 | -1.00 |

## TAKE threshold sweep
| p ≥ | n | avg R | total R |
|---|---|---|---|
| 0.40 | 2 | -1.0 | -2.0 |
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
| LIMIT | 1 | -1.25 |

## Threshold changes: none (current take 0.45, regime 0.6)

## Question version in use: 6
Worst regime misses written to review-2026-11-26-packet.json for question rewriting.
