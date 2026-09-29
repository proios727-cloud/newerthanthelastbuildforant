"""How well calibrated is each JEV question? Scored on closed trades and closed ghosts with live answers.

For every question the battery stores a "bad" probability (material news, crisis regime, poor setup,
illiquid). The outcome is whether the trade lost money. Per question: sample size, base loss rate, mean
predicted probability, Brier score (lower is better; always guessing the base rate scores
base * (1 - base)) and a five-bin reliability table.
"""
BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0001)


def trades(*books):
    for st in books:
        for t in st.get("closed", []) + st.get("ghost_closed", []):
            if t.get("jev_mode") == "live" and t.get("jev_answers"):
                yield t


def report(*books):
    rows = {}
    for t in trades(*books):
        y = 1.0 if t["pnl"] < 0 else 0.0
        for q, p in t["jev_answers"].items():
            if p is not None:
                rows.setdefault(q, []).append((float(p), y))
    out = {}
    for q, pts in sorted(rows.items()):
        n = len(pts)
        base = sum(y for _, y in pts) / n
        brier = sum((p - y) ** 2 for p, y in pts) / n
        bins = []
        for lo, hi in zip(BINS, BINS[1:]):
            b = [(p, y) for p, y in pts if lo <= p < hi]
            if b:
                bins.append({"range": f"{lo:.1f}-{min(hi, 1):.1f}", "n": len(b),
                             "mean_p": round(sum(p for p, _ in b) / len(b), 3),
                             "loss_rate": round(sum(y for _, y in b) / len(b), 3)})
        out[q] = {"n": n, "loss_rate": round(base, 3), "mean_p": round(sum(p for p, _ in pts) / n, 3),
                  "brier": round(brier, 4), "brier_if_base_rate": round(base * (1 - base), 4), "bins": bins}
    return {"questions": out, "trades_scored": sum(1 for _ in trades(*books)),
            "note": "outcome = the trade lost money; ghosts are vetoed sales tracked with no cash"}
