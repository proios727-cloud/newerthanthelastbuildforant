"""One armed kill switch for every paper book. While armed, no book opens anything; exits still run.

  python -m fund kill status
  python -m fund kill arm "reason"          # anyone (a routine, the desk, you) may arm it
  python -m fund kill disarm DISARM         # human-only: the routine and agents never disarm

It arms itself when a receipt shows a breach or a book falls through its floor (AUTO_FLOORS). The real
book's preview gate refuses opening orders while it is armed.
"""
import json
from datetime import datetime, timezone

AUTO_FLOORS = {"putbook": 0.90, "spreadbook": 0.70}   # share of starting NAV; $90k and $350


def load(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"armed": False, "reason": None, "since": None, "by": None, "history": []}


def save(ks, path):
    path.write_text(json.dumps(ks, indent=1) + "\n", encoding="utf-8")


def arm(ks, reason, by="desk", now=None):
    if ks["armed"]:
        return False
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    ks.update(armed=True, reason=reason, since=ts, by=by)
    ks["history"].append({"ts": ts, "action": "arm", "reason": reason, "by": by})
    return True


def disarm(ks, confirm, now=None):
    if confirm != "DISARM":
        raise ValueError("disarm needs the exact word DISARM")
    if not ks["armed"]:
        return False
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    ks["history"].append({"ts": ts, "action": "disarm", "reason": ks["reason"], "by": "human"})
    ks.update(armed=False, reason=None, since=None, by=None)
    return True


def floor_breaches(navs, starts):
    """[(book, nav, floor)] for every book at or below its floor."""
    return [(b, navs[b], round(AUTO_FLOORS[b] * starts[b], 2)) for b in AUTO_FLOORS
            if b in navs and navs[b] <= AUTO_FLOORS[b] * starts[b]]
