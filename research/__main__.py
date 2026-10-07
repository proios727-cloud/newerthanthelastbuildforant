"""Research CLI.

  python -m research gate REPORT.json [--desk desk.json] [--json]
      Exit 0 = DEPLOYABLE, 1 = BLOCKED, 2 = unreadable report or config.
  python -m research review --spec STRATEGY.md [--days 7] [--state ledger/state.json]
                            [--lessons research/lessons.md] [--out research/reviews] [--offline]
"""
import argparse
import json
import pathlib
import sys

from fund import clock
from fund.config import ROOT

from . import gates, review


def cmd_gate(a):
    try:
        report = json.loads(pathlib.Path(a.report).read_text(encoding="utf-8"))
        card = gates.load_scorecard(a.desk)
    except (OSError, ValueError) as e:
        print(f"cannot read input: {e}", file=sys.stderr)
        sys.exit(2)
    res = gates.check(report, card)
    name = report.get("strategy", pathlib.Path(a.report).stem) if isinstance(report, dict) else a.report
    print(json.dumps(res.to_dict(), indent=2) if a.json else gates.render(res, name))
    sys.exit(0 if res.deployable else 1)


def cmd_review(a):
    model = None if a.offline else review.model_from_env()
    rv = review.run(a.state, a.spec, a.lessons, a.out, now=clock.now(), days=a.days, model=model)
    print(f"review {rv.date}: {rv.stats['closed']} closed, {rv.stats['losers']} losers, "
          f"{len(rv.added_lessons)} lesson(s) added, proposal: {rv.proposal['change'] if rv.proposal else 'none'}")
    print(f"report: {pathlib.Path(a.out) / (rv.date + '.md')}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m research")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gate")
    p.add_argument("report"); p.add_argument("--desk", default=str(ROOT / "desk.json"))
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("review")
    p.add_argument("--spec", required=True); p.add_argument("--days", type=int, default=7)
    p.add_argument("--state", default=str(ROOT / "ledger" / "state.json"))
    p.add_argument("--lessons", default=str(ROOT / "research" / "lessons.md"))
    p.add_argument("--out", default=str(ROOT / "research" / "reviews"))
    p.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    {"gate": cmd_gate, "review": cmd_review}[a.cmd](a)


if __name__ == "__main__":
    main()
