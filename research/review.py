"""Nightly review: compare the last N days of paper fills with the strategy spec and past lessons.

Read-only toward the fund. It opens the ledger state file for reading and never writes it, never
builds a preview and never fills. Its only outputs are:

  research/reviews/<date>.md   the night's report: stats, losing trades, at most ONE proposal
  research/lessons.md          appended: one dated rule per evidenced loss pattern, no duplicates

A proposal is not a change. It goes into a new strategy version, which must clear the full
gauntlet (research/gates.py) before it replaces the live one.

The model is optional. With ANTHROPIC_API_KEY set and the anthropic package installed, Opus 5.5
reads the spec, lessons and trades and answers in JSON. Without it the report carries the stats
and losing trades only, and no lessons are written.
"""
import json
import os
import pathlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

MODEL = "claude-opus-5-5"

SYSTEM = (
    "You are the desk reviewer. Compare the live paper trades to the strategy spec and the lessons "
    "already learned. Find root-cause patterns behind losing trades, and only patterns the trades "
    "actually show. Propose at most ONE change. Never place, modify or recommend specific trades.\n\n"
    "Answer with JSON only, in this shape:\n"
    '{"lessons": [{"pattern": "...", "rule": "...", "evidence": "trade refs and numbers"}],\n'
    ' "proposals": [{"strategy": "...", "change": "...", "why": "..."}]}\n'
    "Use an empty list when there is no real pattern or no change worth making."
)


@dataclass
class Review:
    date: str
    stats: dict
    losers: list
    proposal: dict = None
    added_lessons: list = field(default_factory=list)
    notes: list = field(default_factory=list)


class AnthropicModel:
    def __init__(self, model=MODEL, max_tokens=4000):
        import anthropic
        self.client, self.model, self.max_tokens = anthropic.Anthropic(), model, max_tokens

    def create(self, system, user):
        msg = self.client.messages.create(model=self.model, max_tokens=self.max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text")


def model_from_env(env=os.environ):
    if not env.get("ANTHROPIC_API_KEY"):
        return None
    try:
        return AnthropicModel()
    except ImportError:
        return None


def recent_fills(fills, now, days):
    start = now - timedelta(days=days)
    out = []
    for f in fills:
        ts = datetime.fromisoformat(f["ts"])
        if start <= ts <= now:
            out.append(f)
    return sorted(out, key=lambda f: f["ts"])


def stats(trades):
    closed = [t for t in trades if t.get("realized")]
    return {
        "fills": len(trades),
        "closed": len(closed),
        "winners": sum(1 for t in closed if t["realized"] > 0),
        "losers": sum(1 for t in closed if t["realized"] < 0),
        "realized": round(sum(t.get("realized") or 0.0 for t in trades), 2),
        "fees": round(sum(t.get("fee") or 0.0 for t in trades), 2),
    }


def trades_csv(trades):
    rows = ["ts,symbol,side,qty,price,fee,realized,ref"]
    for t in trades:
        rows.append(",".join(str(t.get(k, "")) for k in ("ts", "symbol", "side", "qty", "price", "fee", "realized", "ref")))
    return "\n".join(rows)


def parse_answer(text):
    """Pull the JSON object out of the model's answer; None when there isn't a valid one."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(candidate)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _clean(s):
    return " ".join(str(s or "").split())


def existing_rules(lessons_path):
    p = pathlib.Path(lessons_path)
    if not p.exists():
        return set()
    return {_clean(m.group(1)).lower() for m in re.finditer(r"^- \d{4}-\d{2}-\d{2} · (.+?) — evidence:", p.read_text(encoding="utf-8"), re.M)}


def run(state_path, spec_path, lessons_path, out_dir, now, days=7, model=None):
    fills = json.loads(pathlib.Path(state_path).read_text(encoding="utf-8")).get("fills", [])
    trades = recent_fills(fills, now, days)
    date = now.date().isoformat()
    rv = Review(date, stats(trades), [t for t in trades if (t.get("realized") or 0) < 0])

    if model is None:
        rv.notes.append("no model run (set ANTHROPIC_API_KEY and install anthropic); stats only")
    else:
        spec = pathlib.Path(spec_path).read_text(encoding="utf-8")
        lp = pathlib.Path(lessons_path)
        lessons = lp.read_text(encoding="utf-8") if lp.exists() else "(none yet)"
        user = f"SPEC:\n{spec}\n\nLESSONS:\n{lessons}\n\nTRADES (last {days} days):\n{trades_csv(trades)}"
        data = parse_answer(model.create(SYSTEM, user))
        if data is None:
            rv.notes.append("could not parse the model's answer as JSON; nothing recorded")
        else:
            _apply(rv, data, lessons_path)

    _write_report(rv, out_dir, days)
    return rv


def _apply(rv, data, lessons_path):
    seen = existing_rules(lessons_path)
    new = []
    for item in data.get("lessons") or []:
        if not isinstance(item, dict):
            continue
        rule, evidence = _clean(item.get("rule")), _clean(item.get("evidence"))
        if not rule or not evidence:
            rv.notes.append("skipped a lesson without a rule or evidence")
            continue
        if rule.lower() in seen:
            continue
        seen.add(rule.lower())
        new.append(f"- {rv.date} · {rule} — evidence: {evidence}")
    if new:
        p = pathlib.Path(lessons_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        head = "" if p.exists() else "# Lessons\n\nOne rule per evidenced loss pattern, appended by the nightly review.\n\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(head + "\n".join(new) + "\n")
    rv.added_lessons = new

    props = data.get("proposals")
    if props is None and isinstance(data.get("proposal"), dict):
        props = [data["proposal"]]
    props = [x for x in (props or []) if isinstance(x, dict) and _clean(x.get("change"))]
    if props:
        rv.proposal = {k: _clean(props[0].get(k)) for k in ("strategy", "change", "why")}
    if len(props) > 1:
        rv.notes.append(f"dropped {len(props) - 1} extra proposal(s); one change per night")


def _write_report(rv, out_dir, days):
    s = rv.stats
    lines = [f"# Nightly review {rv.date}", "",
             f"Last {days} days: {s['fills']} fills, {s['closed']} closed ({s['winners']} won, {s['losers']} lost), "
             f"realized {s['realized']:+,.2f}, fees {s['fees']:,.2f}.", "",
             "## Losing trades", ""]
    lines += [f"- {t['ts']} {t['symbol']} {t['side']} {t['qty']} @ {t['price']} → {t['realized']:+,.2f} (ref {t.get('ref')})"
              for t in rv.losers] or ["- none"]
    lines += ["", "## Proposal (not applied)", ""]
    if rv.proposal:
        p = rv.proposal
        lines += [f"- **{p['strategy'] or 'strategy'}:** {p['change']}", f"- Why: {p['why'] or '—'}",
                  "- Next: enter it as a new version and run `python -m research gate` on its report."]
    else:
        lines.append("- none")
    lines += ["", "## Lessons added", ""] + (rv.added_lessons or ["- none"])
    if rv.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in rv.notes]
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{rv.date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
