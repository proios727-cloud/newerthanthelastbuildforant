"""Sportsbook line tracker: fair prices and sharp-action signals from odds snapshots.

Ported from 456CASH `backend/services/line_movement_detector.py` as pure functions, with the
steam check fixed to compare each book against its own earlier line inside the window (the
original only measured spread agreement at one instant). Alerts only — no bets are placed.

Spreads are from the home team's side (−3.5 = home favoured by 3.5).
"""
from dataclasses import dataclass
from datetime import timedelta
from statistics import median

THRESHOLDS = {
    "NFL": {"steam_pts": 1.0, "reverse_pts": 0.5, "volume_gap_pct": 15},
    "NBA": {"steam_pts": 1.5, "reverse_pts": 1.0, "volume_gap_pct": 15},
    "MLB": {"steam_pts": 0.5, "reverse_pts": 0.5, "volume_gap_pct": 15},
    "NHL": {"steam_pts": 0.5, "reverse_pts": 0.5, "volume_gap_pct": 15},
}


def implied_prob(american):
    a = float(american)
    if a == 0:
        raise ValueError("american odds cannot be 0")
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def no_vig(home_american, away_american):
    """Fair (home, away) probabilities with the book's margin removed proportionally."""
    h, a = implied_prob(home_american), implied_prob(away_american)
    return h / (h + a), a / (h + a)


def ev_pct(fair_p, american):
    """Expected return per unit staked when betting `american` odds at true probability `fair_p`."""
    a = float(american)
    payout = a / 100 if a > 0 else 100 / -a
    return (fair_p * payout - (1 - fair_p)) * 100


@dataclass(frozen=True)
class Snap:
    book: str
    spread: float
    ts: object    # aware datetime


def steam(snaps, now, sport="NFL", minutes=10, min_books=3):
    """Books that moved the same way by ≥ threshold within `minutes`. Returns (direction, books) or None."""
    pts = THRESHOLDS[sport]["steam_pts"]
    start = now - timedelta(minutes=minutes)
    by_book = {}
    for s in sorted(snaps, key=lambda s: s.ts):
        by_book.setdefault(s.book, []).append(s)
    moves = {}
    for book, ss in by_book.items():
        before = [s for s in ss if s.ts <= start]
        inside = [s for s in ss if start < s.ts <= now]
        if before and inside:
            moves[book] = inside[-1].spread - before[-1].spread
    toward_home = [b for b, m in moves.items() if m <= -pts]
    toward_away = [b for b, m in moves.items() if m >= pts]
    for direction, books in (("home", toward_home), ("away", toward_away)):
        if len(books) >= min_books:
            return direction, sorted(books)
    return None


def reverse_line_move(open_spread, current_spread, home_bet_pct, sport="NFL", majority=60):
    """Line moved toward the side the betting majority is against — the classic sharp tell."""
    move = current_spread - open_spread          # negative = moved toward home
    pts = THRESHOLDS[sport]["reverse_pts"]
    if home_bet_pct >= majority and move >= pts:
        return "away"                            # public on home, line moved to away
    if home_bet_pct <= 100 - majority and move <= -pts:
        return "home"
    return None


def volume_anomaly(bet_pct, money_pct, sport="NFL"):
    """Money share well above ticket share on one side = fewer, larger bets."""
    return money_pct - bet_pct >= THRESHOLDS[sport]["volume_gap_pct"]


def consensus(snaps):
    """Median latest spread across books."""
    latest = {}
    for s in sorted(snaps, key=lambda s: s.ts):
        latest[s.book] = s.spread
    return median(latest.values()) if latest else None
