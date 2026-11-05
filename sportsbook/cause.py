"""Why did the line move? (TypeSafe) — separates news-driven moves from sharp action.

A steam or reverse move right after an injury report is the market repricing public information;
the same move with no news is the stronger sharp signal. Code detects the move; the judgment reads
the news gathered for the game and labels the cause. Stub answers label everything `unknown`.
"""
import judge

LABEL_MIN_P = 0.70

QUESTION = judge.Question(
    "cause", "choice",
    "The point spread for `game` moved `move.points` points toward `move.toward` between `move.from` and "
    "`move.to`. Using only the items in `news` (each has a time and text), which explanation best accounts "
    "for that move?",
    {"injury": "A player injury, illness or availability update published before or during the move.",
     "lineup": "A starting lineup, rotation or depth-chart change not caused by injury.",
     "weather": "A weather or venue-condition report relevant to the game.",
     "other_news": "Another public report (suspension, travel, coaching) that plausibly moves the line.",
     "unknown": "No item in `news` plausibly explains the move, or the items came after it."})


def label(client, game, move, news):
    a = judge.ask(client, {"game": game, "move": move, "news": list(news)[:30]}, [QUESTION])["cause"]
    return a.value if a.confident(LABEL_MIN_P) else "unknown"


def is_sharp(signal, cause):
    """A detected move counts as sharp only when no public news explains it."""
    return bool(signal) and cause == "unknown"
