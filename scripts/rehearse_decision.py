"""Rehearse a decision night of the forward paper test on a copy of shadow-data (docs/forward-feed.md).

Copies chart-forward from a shadow-data checkout into a scratch folder, then plays the nights from the day after the
newest stored bar up to --to. Each night it appends one synthetic bar per fund (a seeded random walk from the last
close, never real data), runs scripts/forward_run.sh exactly as the nightly feed does, and writes what `finish` writes:
the dashboard files, the monthly review, the brief and the digest. It then checks what a decision night has to produce
and prints a pass/fail list, so a broken step shows up before the real night. The copy is thrown away; nothing is
committed or pushed. Research only: nothing here previews, places or approves an order.
    python3 scripts/rehearse_decision.py SHADOW_CHECKOUT --to 2026-12-02 [--out DIR] [--seed 7]
"""
import argparse
import csv
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def _weekdays(after, to):
    d = after + timedelta(days=1)
    while d <= to:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _append_bar(path, day, rng):
    rows = list(csv.reader(path.read_text().splitlines()))
    last = float(rows[-1][4])
    o = round(last * (1 + rng.gauss(0, 0.003)), 4)
    c = round(o * (1 + rng.gauss(0, 0.01)), 4)
    with path.open("a") as f:
        f.write(f"{day.isoformat()},{o},{max(o, c)},{min(o, c)},{c},1000000\n")


def _newest(d):
    return max(date.fromisoformat(next(reversed(p.read_text().splitlines())).split(",")[0])
               for p in [*(d / "data").glob("*.csv"), *(d / "etf").glob("*.csv")])


def _night(d, out, day):
    """One night: forward_run.sh on the copy, then the files `forward_feed.sh finish` writes."""
    empty = out / "incoming"
    empty.mkdir(exist_ok=True)
    env = {**os.environ, "CHART_TODAY": day.isoformat()}    # the doctor's "today" is the night being played
    run = subprocess.run(["bash", str(ROOT / "scripts/forward_run.sh"), str(d.parent), "--from-dir", str(empty)],
                         cwd=ROOT, capture_output=True, text=True, env=env)
    night = out / day.isoformat()
    night.mkdir()
    (night / "run.log").write_text(run.stdout + run.stderr)
    steps = {"forward_run": run.returncode == 0}
    for name, args in (("dashboard", ["forward_dashboard.py", str(d), str(night / "dash")]),
                       ("review", ["rotation_review.py", str(d), str(night / "REVIEW.md")]),
                       ("digest", ["forward_digest.py", str(d), str(night / "DIGEST.md")])):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / args[0]), *args[1:]], capture_output=True, text=True,
                           env=env)
        steps[name] = r.returncode in ((0, 1) if name == "review" else (0,))      # review exits 1 when a check flags
        if r.returncode not in (0, 1):
            (night / f"{name}.err").write_text(r.stderr)
    if (d / "BRIEF.md").exists():
        shutil.copy(d / "BRIEF.md", night / "BRIEF.md")
    return night, steps


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def rehearse(shadow, to, out, seed=7):
    out = pathlib.Path(out)
    d = out / "shadow" / "chart-forward"
    shutil.copytree(pathlib.Path(shadow) / "chart-forward", d)
    before = {name: len(_jsonl(d / name)) for name in ("rotation.jsonl", "rotation_trend200.jsonl", "rotation_v120.jsonl")}
    rng = random.Random(seed)
    nights, results = [], []
    for day in _weekdays(_newest(d), to):
        for p in sorted([*(d / "data").glob("*.csv"), *(d / "etf").glob("*.csv")]):
            _append_bar(p, day, rng)
        night, steps = _night(d, out, day)
        nights.append((day, night, steps))
    checks = []
    ok = lambda name, cond, detail="": checks.append((name, bool(cond), detail))
    for day, night, steps in nights:
        bad = [k for k, v in steps.items() if not v]
        ok(f"{day}: every step ran", not bad, ", ".join(bad) or "forward_run, dashboard, review, digest")
    logs = {name: _jsonl(d / name) for name in before}
    decided = {name: [r["as_of"] for r in rows[before[name]:]] for name, rows in logs.items()}
    for name, days in decided.items():
        ok(f"{name}: one new decision on the decision day", len(days) == 1, ", ".join(days) or "none")
    live = logs["rotation.jsonl"][-1] if decided["rotation.jsonl"] else None
    if live:
        dday = live["as_of"]
        ok("live rule settings unchanged", live.get("rule") == {"lookback": 60, "top": 3}, json.dumps(live.get("rule")))
        ok("variant A logged with lookback 120", logs["rotation_v120.jsonl"] and
           logs["rotation_v120.jsonl"][-1].get("rule", {}).get("lookback") == 120)
        tickets = [t for t in _jsonl(d / "rotation_tickets.jsonl") if t.get("as_of") == dday]
        ok("paper tickets written for the decision", tickets, f"{len(tickets)} ticket set(s)")
        dnight = next(n for day, n, _ in nights if day.isoformat() == dday)
        brief = (dnight / "BRIEF.md").read_text() if (dnight / "BRIEF.md").exists() else ""
        ok("brief written on the decision night", dday in brief)
        ok("brief shows variant A's call", "## Variant A" in brief)
        review = (dnight / "REVIEW.md").read_text() if (dnight / "REVIEW.md").exists() else ""
        ok("review covers the new decision", dday in review)
        ok("review shows variant A's call", "**Variant A" in review and "no decision logged" not in review)
        eve = [n for day, n, _ in nights if day.isoformat() < dday]
        if eve:
            st = json.loads((eve[-1] / "dash" / "status.json").read_text())[0]
            ok("the night before says the decision is next", st.get("next_decision") == dday, str(st.get("next_decision")))
        st = json.loads((dnight / "dash" / "status.json").read_text())[0]
        ok("after deciding, the next decision moves on a month", (st.get("next_decision") or "") > dday, str(st.get("next_decision")))
        last_night = nights[-1][1]
        status = json.loads((last_night / "dash" / "status.json").read_text())[0]
        ok("dashboard status names the new decision", status.get("decided") == dday, str(status.get("decided")))
        ok("dashboard shows variant A's decision", status.get("v120_decided") == dday, str(status.get("v120_decided")))
        if nights[-1][0].isoformat() > dday:
            rot = json.loads((d / "ROTATION.json").read_text())
            ok("new period filled the next session", rot["periods"][-1]["decided"] == dday and rot["periods"][-1]["from"] > dday,
               json.dumps({k: rot["periods"][-1][k] for k in ("decided", "from", "to")}))
            ok("variant A scored from its fill", status.get("v120_from") and status.get("v120_rule_net") is not None,
               f"from {status.get('v120_from')}, net {status.get('v120_rule_net')}")
            ok("live rule over A's sessions computed", status.get("v120_live_net_same_span") is not None,
               str(status.get("v120_live_net_same_span")))
            digest = (last_night / "DIGEST.md").read_text()
            ok("digest compares variant A with the live rule", "against the live rule's" in digest)
    return {"nights": [day.isoformat() for day, _, _ in nights], "decisions": decided, "checks": checks, "out": str(out)}


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("shadow")
    a.add_argument("--to", required=True, type=date.fromisoformat)
    a.add_argument("--out")
    a.add_argument("--seed", type=int, default=7)
    a = a.parse_args(argv)
    out = pathlib.Path(a.out) if a.out else pathlib.Path(tempfile.mkdtemp(prefix="rehearsal-"))
    res = rehearse(a.shadow, a.to, out, a.seed)
    print(f"nights {res['nights'][0]} to {res['nights'][-1]} ({len(res['nights'])}); files in {res['out']}")
    print("decisions: " + json.dumps(res["decisions"]))
    for name, passed, detail in res["checks"]:
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return 0 if all(p for _, p, _ in res["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
