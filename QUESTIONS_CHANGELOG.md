# Questions changelog

## v1 — initial
Baseline regime, TAKE/SKIP, book-control and entry questions.

## v2 — 2026-11-04
**Evidence:** 69 scored regime calls, accuracy 34.8%, Brier 1.148 (worse than uniform 0.667). TRENDING was called 49×, realized CHOPPY 35× and PANIC 7×. The 14 confident misses (p 0.97–0.99, e.g. candle_t 1793737800000, 1793721600000, 1793726100000, 1793720700000) were slow grinds: ADX 25–36 but EMA20/50 separation ~0.25%, realized vol ~0.17%, Bollinger width <1%, volume ~0.7× average, book imbalance ~−0.3 against the move; none travelled 2×ATR in the next 12 candles.
**Change:** regime question only. Instructions now state the 12-candle / 2×ATR horizon, that ADX alone is not enough, and to prefer CHOPPY when unsure. TRENDING criterion requires ADX>25 plus EMA separation >~0.4%, expanding bands, volume ≥ average and a non-opposing book. CHOPPY now explicitly covers quiet one-sided grinds with high ADX. Labels, signal questions, thresholds and code unchanged.
