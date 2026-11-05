# Questions changelog

## v1 — initial
Baseline regime, TAKE/SKIP, book-control and entry questions.

## v2 — 2026-11-04
**Evidence:** 69 scored regime calls, accuracy 34.8%, Brier 1.148 (worse than uniform 0.667). TRENDING was called 49×, realized CHOPPY 35× and PANIC 7×. The 14 confident misses (p 0.97–0.99, e.g. candle_t 1793737800000, 1793721600000, 1793726100000, 1793720700000) were slow grinds: ADX 25–36 but EMA20/50 separation ~0.25%, realized vol ~0.17%, Bollinger width <1%, volume ~0.7× average, book imbalance ~−0.3 against the move; none travelled 2×ATR in the next 12 candles.
**Change:** regime question only. Instructions now state the 12-candle / 2×ATR horizon, that ADX alone is not enough, and to prefer CHOPPY when unsure. TRENDING criterion requires ADX>25 plus EMA separation >~0.4%, expanding bands, volume ≥ average and a non-opposing book. CHOPPY now explicitly covers quiet one-sided grinds with high ADX. Labels, signal questions, thresholds and code unchanged.

## v3 — 2026-11-05 (requested by the user; outside the nightly 24h rule)
**Scoring fix first (review.py):** the realized-regime rule labelled any ≥4×ATR excursion or ≥3×ATR candle PANIC, even a clean one-way move. The Nov 4 11:30–14:00 rally to $80.8k (+10 to +14 ATR, path efficiency up to 0.84) was being scored as PANIC. A large move is now PANIC only when it is not directional (net ≥2×ATR with efficiency ≥0.35 makes it TRENDING). Rescored: v1 43.6% (majority baseline 54.5%), v2 73.4% (majority baseline 78.1%).
**Evidence for the rewrite:** after rescoring, v2's errors were 13 CHOPPY calls before a TRENDING move, nearly all one squeeze (Nov 4 11:30–14:00, 19:30–19:45): Bollinger width ~0.79% (vs 1.18% on correct CHOPPY calls), ADX ~45 (vs ~28), volume 0.73× average (vs 0.45×). v2's text told Drex that narrow bands and high ADX mean CHOPPY, which caused this. Only 1 genuine disorderly PANIC moment (Nov 4 11:15).
**Change:** regime question only. TRENDING now also covers a squeeze about to release (bands < ~0.9%, ADX > ~40, volume rising toward 0.7×). CHOPPY is limited to an ordinary range (moderate ADX, volume < ~0.5×) and explicitly excludes a coil. PANIC is defined as a large move without a clean one-way path, matching the corrected scorer. "When in doubt choose CHOPPY" removed. Caveat: the squeeze evidence is essentially one episode, so v3 needs several days of scoring before it can be trusted.
