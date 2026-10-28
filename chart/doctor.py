"""Preflight for the forward test: say plainly what would make tonight's run a silent no-op.

Checks the Alpha Vantage key, how many weekdays each data folder's newest bar is behind, and when the rotation rule
next decides (the first weekday of next month; exchange holidays are not modelled, so a holiday pushes it a day).
"""
import os
import pathlib
from datetime import date, timedelta

from . import load_csv


def weekdays_between(a, b):
    """Weekdays after date `a` up to and including date `b` (0 when b <= a)."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


def next_decision(today):
    """The rotation rule's next decision day: the first weekday of the month after `today` (or today's month, if its
    first weekday is still ahead)."""
    first = today.replace(day=1)
    while first.weekday() >= 5:
        first += timedelta(days=1)
    if first >= today:
        return first
    nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def check(folders, today=None, env=None, max_stale=3):
    today = today or date.today()
    env = os.environ if env is None else env
    problems, data = [], {}
    if not env.get("ALPHAVANTAGE_API_KEY"):
        problems.append("ALPHAVANTAGE_API_KEY is not set: `chart update` cannot fetch bars, so nothing new is logged. "
                        "Add it under Settings → Secrets and variables → Actions.")
    for folder in folders:
        files = sorted(pathlib.Path(folder).glob("*.csv"))
        if not files:
            problems.append(f"{folder}: no CSVs")
            continue
        last = {f.stem.upper(): load_csv(f)[-1].ts for f in files}
        newest, oldest = max(last.values()), min(last.values())
        behind = weekdays_between(date.fromisoformat(newest), today)
        data[str(folder)] = {"files": len(files), "newest_bar": newest, "oldest_last_bar": oldest,
                             "weekdays_behind": behind}
        if behind > max_stale:
            problems.append(f"{folder}: newest bar {newest} is {behind} weekdays old (limit {max_stale})")
        lagging = sorted(s for s, t in last.items() if t < newest)
        if lagging:
            problems.append(f"{folder}: {', '.join(lagging)} end before {newest}; the rotation only uses dates "
                            "every fund has, so one lagging file stalls it")
    nd = next_decision(today)
    return {"ok": not problems, "today": today.isoformat(), "problems": problems, "data": data,
            "next_rotation_decision": nd.isoformat(), "days_to_decision": (nd - today).days}
