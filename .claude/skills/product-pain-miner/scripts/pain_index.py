#!/usr/bin/env python3
"""Validate a product-pain dataset, score it, and render a ranked Markdown report.

Usage:
  python pain_index.py data/kitchen.json                         # validate only
  python pain_index.py data/kitchen.json --out reports/kitchen.md
  python pain_index.py --overview data --out OVERVIEW.md         # cross-category view

Exit 1 with a readable list of problems if the dataset is invalid. Never renders a broken file.
Stdlib only.
"""
import argparse, json, pathlib, re, sys
from collections import Counter

MODES = {
    "no-feedback": "No feedback",
    "mapping-mismatch": "Mapping mismatch",
    "seller-first": "Seller-first",
    "last-mile-waste": "Last-mile waste",
    "bad-timing": "Bad timing",
    "one-size-fits-all": "One size fits all",
    "wears-out-early": "Wears out early",
}
SCORES = ("frequency", "severity", "annoyance", "workaround", "feasibility")
TEXT = ("item", "complaint", "redesign")
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
URL_RE = re.compile(r"^https?://\S+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate(data):
    problems = []
    if not isinstance(data, dict):
        return ["dataset must be a JSON object"]
    if not isinstance(data.get("category"), str) or not data["category"].strip():
        problems.append("missing 'category'")
    if not isinstance(data.get("updated"), str) or not DATE_RE.match(data["updated"]):
        problems.append("'updated' must be YYYY-MM-DD")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        problems.append("'entries' must be a non-empty list")
        return problems
    seen = set()
    for i, e in enumerate(entries):
        where = f"entries[{i}]"
        if not isinstance(e, dict):
            problems.append(f"{where}: must be an object")
            continue
        eid = e.get("id")
        if not isinstance(eid, str) or not ID_RE.match(eid):
            problems.append(f"{where}: 'id' must be kebab-case")
        elif eid in seen:
            problems.append(f"{where}: duplicate id '{eid}'")
        else:
            seen.add(eid)
            where = f"{where} ({eid})"
        for k in TEXT:
            if not isinstance(e.get(k), str) or not e[k].strip():
                problems.append(f"{where}: missing '{k}'")
        if e.get("failure_mode") not in MODES:
            problems.append(f"{where}: 'failure_mode' must be one of {sorted(MODES)}")
        for k in SCORES:
            v = e.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
                problems.append(f"{where}: '{k}' must be an integer 1-5")
        src = e.get("sources")
        if not isinstance(src, list) or not src:
            problems.append(f"{where}: needs at least one source URL")
        elif not all(isinstance(u, str) and URL_RE.match(u) for u in src):
            problems.append(f"{where}: every source must be an http(s) URL")
    return problems


def score(e):
    # A daily nuisance counts as much as real harm: take whichever bothers people more.
    impact = max(e["severity"], e["annoyance"])
    pain = round(e["frequency"] * impact * e["workaround"] / 125 * 100)
    return pain, round(pain * e["feasibility"] / 5)


def ranked(data):
    rows = [(e, *score(e)) for e in data["entries"]]
    return sorted(rows, key=lambda r: (-r[2], -r[1], r[0]["id"]))


def cell(s):
    return s.replace("|", "\\|").replace("\n", " ")


def render(data):
    rows = ranked(data)
    modes = Counter(e["failure_mode"] for e in data["entries"])
    out = [
        f"# {data['category'].title()}: pain → redesign report",
        "",
        f"_Generated from `data/{data['category']}.json` (updated {data['updated']}). Do not edit by hand._",
        "",
        "**Opportunity** = pain × feasibility. **Pain** = frequency × max(severity, annoyance) × workaround difficulty (0–100). "
        "A nuisance counts as much as harm.",
        "",
        "## Ranked opportunities",
        "",
        "| # | Item | Complaint | Failure | Pain | Opp. | Redesign |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, (e, pain, opp) in enumerate(rows, 1):
        out.append(f"| {n} | {cell(e['item'])} | {cell(e['complaint'])} | {MODES[e['failure_mode']]} "
                   f"| {pain} | **{opp}** | {cell(e['redesign'])} |")
    out += ["", "## Failure-mode mix", "", "| Failure | Entries |", "|---|---|"]
    for m, c in modes.most_common():
        out.append(f"| {MODES[m]} | {c} |")
    weak = [e["id"] for e, _, _ in rows if len(e["sources"]) < 2]
    out += ["", "## Evidence", ""]
    if weak:
        out.append("Single-source entries (confirm before acting): " + ", ".join(f"`{w}`" for w in weak))
        out.append("")
    for e, _, _ in rows:
        prior = f" Prior art: {e['prior_art']}." if e.get("prior_art") else ""
        links = ", ".join(f"[{i}]({u})" for i, u in enumerate(e["sources"], 1))
        out.append(f"- `{e['id']}`: {links}.{prior}")
    return "\n".join(out) + "\n"


def render_overview(datasets):
    rows = sorted(((d["category"], e, *score(e)) for d in datasets for e in d["entries"]),
                  key=lambda r: (-r[3], -r[2], r[0], r[1]["id"]))
    cats = sorted(d["category"] for d in datasets)
    mix = Counter((e["failure_mode"], c) for c, e, _, _ in rows)
    totals = Counter(e["failure_mode"] for _, e, _, _ in rows)
    nuisance = sum(1 for _, e, _, _ in rows if e["annoyance"] > e["severity"])
    updated = max(d["updated"] for d in datasets)
    out = [
        "# Cross-category view: pain → redesign",
        "",
        f"_Generated from {len(datasets)} datasets in `data/` (latest update {updated}). Do not edit by hand._",
        "",
        f"**{len(rows)} complaints** across {len(cats)} categories. "
        f"{nuisance} of them ({round(nuisance / len(rows) * 100)}%) are nuisance-led: annoyance scores higher than harm.",
        "",
        "## Failure modes by category",
        "",
        "| Failure | " + " | ".join(c.title() for c in cats) + " | Total |",
        "|---|" + "---|" * len(cats) + "---|",
    ]
    for m, total in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        counts = " | ".join(str(mix[(m, c)] or "·") for c in cats)
        out.append(f"| {MODES[m]} | {counts} | **{total}** |")
    out += ["", "## Top 15 opportunities overall", "",
            "| # | Category | Item | Failure | Pain | Opp. | Redesign |", "|---|---|---|---|---|---|---|"]
    for n, (c, e, pain, opp) in enumerate(rows[:15], 1):
        out.append(f"| {n} | {c.title()} | {cell(e['item'])} | {MODES[e['failure_mode']]} "
                   f"| {pain} | **{opp}** | {cell(e['redesign'])} |")
    out += ["", "## Every entry by failure mode", ""]
    for m, total in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        out += [f"### {MODES[m]} ({total})", ""]
        for c, e, _, opp in rows:
            if e["failure_mode"] == m:
                out.append(f"- **{cell(e['item'])}** ({c}, opp. {opp}): {e['complaint']}")
        out.append("")
    return "\n".join(out)


def load(path):
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return None
    problems = validate(data)
    if problems:
        print(f"{path}: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return None
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dataset", nargs="?")
    ap.add_argument("--overview", metavar="DATA_DIR", help="render the cross-category view from every dataset in DATA_DIR")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    if bool(args.dataset) == bool(args.overview):
        ap.error("give either a dataset or --overview DATA_DIR")
    if args.overview:
        paths = sorted(pathlib.Path(args.overview).glob("*.json"))
        datasets = [load(p) for p in paths]
        if not paths or None in datasets:
            return 1
        text = render_overview(datasets)
        if args.out:
            pathlib.Path(args.out).write_text(text)
            print(f"wrote {args.out} ({len(datasets)} datasets)")
        else:
            print(text, end="")
        return 0
    data = load(args.dataset)
    if data is None:
        return 1
    if args.out:
        pathlib.Path(args.out).write_text(render(data))
        print(f"wrote {args.out} ({len(data['entries'])} entries)")
    else:
        print(f"{args.dataset}: ok ({len(data['entries'])} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
