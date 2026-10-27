"""GM x A-S toxicity desk for Kalshi 15-minute crypto markets.

Stages (each one gates the next):
  record   - backfill settled markets / record live trades + books (read-only, public API)
  analyze  - VPIN, spread decomposition, out-of-sample toxicity calibration   (gate 2)
  replay   - GM x A-S vs pure A-S quoting replay on recorded tape, fees in      (gate 3)
  shadow   - live quotes computed and logged, no orders                         (gate 4)
  execute  - SHADOW / DEMO / LIVE executor behind hard caps and an approval word (gates 5-6)
"""
