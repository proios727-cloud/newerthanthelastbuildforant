#!/usr/bin/env python3
"""Skill Gate: pre-install safety triage for agent skills and plugins.

Runs NVIDIA SkillSpector (static, offline by default), then sorts every finding
by WHERE it lives. A raw scan of a healthy repo is mostly noise: test fixtures
that contain attack strings, benchmark scripts that read an API key, docs that
mention ~/.claude/settings.json. What matters is the code and instructions an
agent actually loads after install. This tool separates the two and returns a
verdict a person can act on.

  python skill_gate.py scan  <dir|git-url> [--out gate_out] [--llm] [--subdir plugin]
  python skill_gate.py triage report.json  [--out gate_out] [--name NAME]

Verdicts
  CLEAN   no HIGH/CRITICAL finding in anything that runs or instructs the agent
  REVIEW  HIGH/CRITICAL findings in active code or instructions: read each one
  BLOCK   a hard signal in agent instructions (override / exfiltration wording)

The tool never says "safe". CLEAN means the static patterns found nothing in
active surfaces, not that the plugin has been proven harmless.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath

SEV_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

# Surfaces. "code" and "instructions" are what an install actually activates.
CODE, INSTR, DEV = "code", "instructions", "dev"
ACTIVE = {CODE, INSTR}

DEV_DIRS = {
    "tests", "test", "__tests__", "spec", "benchmarks", "benchmark", "bench",
    "examples", "example", "samples", "fixtures", "demo", "demos", "docs", "doc",
    ".github", "evals", "eval", "i18n", "assets", "node_modules", ".git",
}
INSTR_DIRS = {"skills", "agents", "commands", "references", "prompts", "rules"}
INSTR_FILES = {"skill.md", "claude.md", "agents.md", "agent.md", "gemini.md"}
TEST_FILE = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|^conftest\.)", re.I)

# Rule ids that mean "the agent is being told to do something hostile". Only
# BLOCK when they sit in text the agent will read. Everything else is REVIEW.
HARD_INSTRUCTION_RULES = {"P1", "P3", "E4"}


def classify(path: str, scanner_surface: str | None = None) -> str:
    """Return CODE, INSTR or DEV for a repo-relative file path."""
    p = PurePosixPath(path.replace("\\", "/"))
    parts = [x.lower() for x in p.parts]
    name = parts[-1] if parts else ""
    dirs = parts[:-1]
    if TEST_FILE.search(name) or scanner_surface == "tests":
        return DEV
    is_md = name.endswith((".md", ".mdx", ".txt", ".rst"))
    if name in INSTR_FILES:
        # A top-level or skills/ SKILL.md is read by the agent. Under docs it is an example.
        return DEV if set(dirs) & {"docs", "doc", "examples", "example", "tests", "test", "fixtures"} else INSTR
    if is_md and set(dirs) & INSTR_DIRS and not (set(dirs) & DEV_DIRS):
        return INSTR
    if set(dirs) & DEV_DIRS:
        return DEV
    if is_md:
        return DEV  # README, CHANGELOG, etc.: documentation, not loaded by the agent
    return CODE


def sev(i: dict) -> int:
    return SEV_ORDER.get(str(i.get("severity", "")).upper(), 0)


def location(i: dict) -> tuple[str, int | None]:
    loc = i.get("location") or {}
    if isinstance(loc, dict):
        return str(loc.get("file") or "?"), loc.get("start_line")
    occ = (i.get("occurrences") or [{}])[0]
    return str(occ.get("file") or "?"), occ.get("start_line")


def triage(report: dict, name: str = "") -> dict:
    """Group findings by surface, decide the verdict, keep the evidence."""
    issues = report.get("issues") or []
    tiers: dict[str, list] = {CODE: [], INSTR: [], DEV: []}
    for i in issues:
        f, line = location(i)
        tier = classify(f, i.get("surface"))
        tiers[tier].append({
            "id": i.get("id"), "pattern": i.get("pattern") or i.get("category"),
            "severity": str(i.get("severity", "")).upper(), "confidence": i.get("confidence"),
            "file": f, "line": line, "tier": tier,
            "finding": re.sub(r"\s+", " ", str(i.get("finding") or ""))[:240],
            "snippet": re.sub(r"\s+", " ", str(i.get("code_snippet") or ""))[:240],
            "remediation": re.sub(r"\s+", " ", str(i.get("remediation") or ""))[:240],
        })

    def serious(rows):
        return sorted((r for r in rows if SEV_ORDER.get(r["severity"], 0) >= 3),
                      key=lambda r: (-SEV_ORDER[r["severity"]], r["file"], r["line"] or 0))

    active_serious = serious(tiers[CODE]) + serious(tiers[INSTR])
    hard = [r for r in serious(tiers[INSTR]) if r["id"] in HARD_INSTRUCTION_RULES]
    comp = report.get("analysis_completeness") or {}
    notes = []
    if comp and not comp.get("is_complete", True):
        notes.append("Scan was partial (%s%% of components). Unscanned files are unchecked."
                     % comp.get("coverage_percent", "?"))
    if report.get("execution_successful") is False:
        notes.append("The scanner reported an unsuccessful run. Treat results as incomplete.")

    if hard:
        verdict = "BLOCK"
    elif active_serious:
        verdict = "REVIEW"
    else:
        verdict = "CLEAN"

    raw = report.get("risk_assessment") or {}
    return {
        "name": name or (report.get("skill") or {}).get("name") or "unnamed",
        "verdict": verdict,
        "raw_scanner": {"score": raw.get("score"), "severity": raw.get("severity"),
                        "recommendation": raw.get("recommendation")},
        "counts": {t: dict(Counter(r["severity"] for r in rows)) for t, rows in tiers.items()},
        "total_findings": len(issues),
        "dev_only_serious": len(serious(tiers[DEV])),
        "to_review": active_serious,
        "hard_signals": hard,
        "notes": notes,
        "tiers": tiers,
    }


def group(rows: list[dict]) -> list[dict]:
    """Collapse repeats of one rule in one file so a reader sees 1 row, not 20."""
    g: dict[tuple, dict] = {}
    for r in rows:
        k = (r["id"], r["file"])
        if k not in g:
            g[k] = dict(r, count=0, lines=[])
        g[k]["count"] += 1
        if r["line"]:
            g[k]["lines"].append(r["line"])
    return list(g.values())


GUIDE = {
    CODE: "Runs on your machine after install (hooks, scripts, runtime). Open the file:line and decide.",
    INSTR: "Text the agent reads and obeys (SKILL.md, agents, references). Hostile wording here is the real risk.",
    DEV: "Tests, benchmarks, docs, examples. Not loaded at runtime. Informational only.",
}


def to_markdown(t: dict) -> str:
    icon = {"CLEAN": "PASS", "REVIEW": "REVIEW", "BLOCK": "BLOCK"}[t["verdict"]]
    raw = t["raw_scanner"]
    out = [f"# Skill Gate: {t['name']}", "",
           f"**Verdict: {icon}**  (raw scanner: {raw.get('severity')} {raw.get('score')}, "
           f"\"{raw.get('recommendation')}\")", "",
           f"{t['total_findings']} raw findings. {len(t['to_review'])} serious in active code or "
           f"instructions; {t['dev_only_serious']} serious but dev-only (tests, benchmarks, docs).", ""]
    for n in t["notes"]:
        out.append(f"> Note: {n}")
    if t["notes"]:
        out.append("")
    if t["hard_signals"]:
        out += ["## Hard signals in agent instructions", ""]
        for r in group(t["hard_signals"]):
            out.append(f"- **{r['severity']} {r['id']}** `{r['file']}:{r['line']}` {r['finding']}")
        out.append("")
    out += ["## Read these before installing", ""]
    rows = group(t["to_review"])
    if not rows:
        out.append("Nothing serious in active surfaces.")
    for r in rows:
        where = f"{r['file']}:{r['line']}" + (f" (x{r['count']})" if r["count"] > 1 else "")
        out.append(f"- **{r['severity']} {r['id']}** [{r['tier']}] `{where}`  \n  {r['pattern']}: {r['finding']}")
    out += ["", "## Where findings landed", "", "| Surface | CRITICAL | HIGH | MEDIUM | LOW | What it means |", "|---|---|---|---|---|---|"]
    for tier in (CODE, INSTR, DEV):
        c = t["counts"][tier]
        out.append(f"| {tier} | {c.get('CRITICAL', 0)} | {c.get('HIGH', 0)} | {c.get('MEDIUM', 0)} | "
                   f"{c.get('LOW', 0)} | {GUIDE[tier]} |")
    out += ["", "CLEAN is not a safety guarantee: static patterns only, no semantic review unless --llm was used."]
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--mute:#5b6572;--line:#dfe3e8;--ok:#0a7d4b;--warn:#a15c00;--bad:#b3261e;--okbg:#e3f4ec;--warnbg:#fdf0d9;--badbg:#fbe4e2}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1216;--card:#171b21;--ink:#e8ebef;--mute:#98a2b0;--line:#2a313a;--ok:#4cc38a;--warn:#e5a23c;--bad:#ff7b72;--okbg:#10281d;--warnbg:#2c2210;--badbg:#32171a}}
:root[data-theme=dark]{--bg:#0f1216;--card:#171b21;--ink:#e8ebef;--mute:#98a2b0;--line:#2a313a;--ok:#4cc38a;--warn:#e5a23c;--bad:#ff7b72;--okbg:#10281d;--warnbg:#2c2210;--badbg:#32171a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:920px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute)}
.sub{color:var(--mute);margin:0 0 16px}
.verdict{display:flex;align-items:center;gap:14px;padding:16px;border-radius:12px;border:1px solid var(--line);background:var(--card)}
.badge{font-weight:700;font-size:18px;padding:6px 14px;border-radius:999px;letter-spacing:.03em}
.CLEAN{background:var(--okbg);color:var(--ok)}.REVIEW{background:var(--warnbg);color:var(--warn)}.BLOCK{background:var(--badbg);color:var(--bad)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.stat b{display:block;font-size:22px}.stat span{color:var(--mute);font-size:13px}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0;padding:0}
summary{cursor:pointer;padding:10px 12px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;list-style:none}
summary::-webkit-details-marker{display:none}
.sv{font-size:12px;font-weight:700;padding:2px 8px;border-radius:6px}
.CRITICAL,.HIGH{background:var(--badbg);color:var(--bad)}.MEDIUM{background:var(--warnbg);color:var(--warn)}.LOW{background:var(--okbg);color:var(--ok)}
code{font:13px ui-monospace,Menlo,Consolas,monospace;word-break:break-all}
.body{padding:0 12px 12px;color:var(--mute);font-size:14px}.body pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px;color:var(--ink);font:12.5px ui-monospace,Menlo,Consolas,monospace}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600}
.note{background:var(--warnbg);color:var(--warn);padding:10px 12px;border-radius:10px;margin:10px 0}
.foot{color:var(--mute);font-size:13px;margin-top:28px}
@media (max-width:560px){th:nth-child(6),td:nth-child(6){display:none}}
"""


def to_html(t: dict) -> str:
    e = html.escape
    raw = t["raw_scanner"]
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
             f"<meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>Skill Gate {e(t['name'])}</title><style>{CSS}</style></head><body><main>",
             f"<h1>Skill Gate: {e(t['name'])}</h1><p class=sub>Pre-install triage of SkillSpector findings by where they live.</p>",
             f"<div class=verdict><span class='badge {t['verdict']}'>{t['verdict']}</span>"
             f"<div>{len(t['to_review'])} serious finding(s) in active code or instructions.<br>"
             f"<span class=sub>Raw scanner said {e(str(raw.get('severity')))} {e(str(raw.get('score')))}, "
             f"&ldquo;{e(str(raw.get('recommendation')))}&rdquo;.</span></div></div>"]
    parts.append("<div class=stats>"
                 f"<div class=stat><b>{t['total_findings']}</b><span>raw findings</span></div>"
                 f"<div class=stat><b>{len(t['to_review'])}</b><span>to review (active)</span></div>"
                 f"<div class=stat><b>{t['dev_only_serious']}</b><span>serious, dev-only</span></div>"
                 f"<div class=stat><b>{len(t['hard_signals'])}</b><span>hard signals</span></div></div>")
    for n in t["notes"]:
        parts.append(f"<div class=note>{e(n)}</div>")
    parts.append("<h2>Read these before installing</h2>")
    rows = group(t["to_review"])
    if not rows:
        parts.append("<p class=sub>Nothing serious in active surfaces.</p>")
    for r in rows:
        cnt = f" &times;{r['count']}" if r["count"] > 1 else ""
        parts.append(
            f"<details><summary><span class='sv {r['severity']}'>{e(r['severity'])}</span>"
            f"<b>{e(str(r['id']))}</b><code>{e(r['file'])}:{e(str(r['line']))}</code>{cnt}"
            f"<span class=sub>{e(str(r['pattern']))}</span></summary><div class=body>"
            f"<p><b>Surface:</b> {e(r['tier'])}. {e(GUIDE[r['tier']])}</p>"
            f"<p><b>Matched:</b> {e(r['finding'])}</p>"
            + (f"<pre>{e(r['snippet'])}</pre>" if r["snippet"] else "")
            + (f"<p><b>Scanner advice:</b> {e(r['remediation'])}</p>" if r["remediation"] else "")
            + "</div></details>")
    parts.append("<h2>Where findings landed</h2><table><tr><th>Surface<th>Crit<th>High<th>Med<th>Low<th>Meaning</tr>")
    for tier in (CODE, INSTR, DEV):
        c = t["counts"][tier]
        parts.append(f"<tr><td>{tier}<td>{c.get('CRITICAL', 0)}<td>{c.get('HIGH', 0)}<td>{c.get('MEDIUM', 0)}"
                     f"<td>{c.get('LOW', 0)}<td>{e(GUIDE[tier])}</tr>")
    parts.append("</table><p class=foot>CLEAN is not a safety guarantee: static patterns only unless the "
                 "LLM pass was used. Static rules cannot tell a test fixture from a live payload by "
                 "content alone, so this tool judges by file location.</p></main></body></html>")
    return "".join(parts)


def write_outputs(t: dict, out: str) -> dict:
    os.makedirs(out, exist_ok=True)
    paths = {"json": os.path.join(out, "verdict.json"), "md": os.path.join(out, "report.md"),
             "html": os.path.join(out, "report.html")}
    slim = {k: v for k, v in t.items() if k != "tiers"}
    with open(paths["json"], "w") as f:
        json.dump(slim, f, indent=1)
    with open(paths["md"], "w") as f:
        f.write(to_markdown(t))
    with open(paths["html"], "w") as f:
        f.write(to_html(t))
    return paths


def find_scanner() -> str | None:
    env = os.environ.get("SKILLSPECTOR")
    if env and os.path.exists(env):
        return env
    return shutil.which("skillspector")


def resolve_target(target: str, workdir: str) -> tuple[str, str]:
    """Return (local_path, display_name). Clone only; never execute anything from it."""
    if re.match(r"^(https://|git@)", target) or re.match(r"^[\w.-]+/[\w.-]+$", target) and not os.path.exists(target):
        url = target if "://" in target or target.startswith("git@") else f"https://github.com/{target}"
        dest = os.path.join(workdir, "clone")
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, dest], check=True, timeout=300,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        return dest, url.rstrip("/").split("/")[-1].removesuffix(".git")
    p = os.path.abspath(target)
    if not os.path.isdir(p):
        sys.exit(f"not a directory: {target}")
    return p, os.path.basename(p)


def cmd_scan(a) -> int:
    scanner = find_scanner()
    if not scanner:
        sys.exit("skillspector not found. Install: uv tool install git+https://github.com/NVIDIA/skillspector.git "
                 "(or set SKILLSPECTOR=/path/to/skillspector)")
    with tempfile.TemporaryDirectory() as wd:
        path, name = resolve_target(a.target, wd)
        scan_path = os.path.join(path, a.subdir) if a.subdir else path
        raw_json = os.path.join(a.out, "skillspector.json")
        os.makedirs(a.out, exist_ok=True)
        cmd = [scanner, "scan", scan_path, "--format", "json", "--output", os.path.abspath(raw_json)]
        if not a.llm:
            cmd.append("--no-llm")  # keeps skill contents on this machine
        try:
            subprocess.run(cmd, check=True, timeout=a.timeout, cwd=a.out)
        except subprocess.TimeoutExpired:
            sys.exit(f"scan exceeded {a.timeout}s. Large repos: scan the installable part with --subdir "
                     "(e.g. plugin, skills) or raise --timeout.")
        with open(raw_json) as f:
            report = json.load(f)
    return finish(report, a.out, a.name or name)


def finish(report: dict, out: str, name: str) -> int:
    t = triage(report, name)
    paths = write_outputs(t, out)
    print(f"{t['name']}: {t['verdict']}  ({len(t['to_review'])} to review, "
          f"{t['dev_only_serious']} dev-only serious, {t['total_findings']} raw)")
    print("report:", paths["html"])
    return {"CLEAN": 0, "REVIEW": 1, "BLOCK": 2}[t["verdict"]]


def cmd_triage(a) -> int:
    with open(a.report) as f:
        report = json.load(f)
    return finish(report, a.out, a.name or "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-install triage for agent skills and plugins")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="run SkillSpector on a dir / git URL / owner/repo, then triage")
    s.add_argument("target")
    s.add_argument("--out", default="gate_out")
    s.add_argument("--name", default="")
    s.add_argument("--subdir", default="", help="scan only this subfolder (for large repos)")
    s.add_argument("--llm", action="store_true", help="enable SkillSpector LLM pass (sends skill text to your configured provider)")
    s.add_argument("--timeout", type=int, default=600)
    s.set_defaults(fn=cmd_scan)
    t = sub.add_parser("triage", help="triage an existing SkillSpector JSON report")
    t.add_argument("report")
    t.add_argument("--out", default="gate_out")
    t.add_argument("--name", default="")
    t.set_defaults(fn=cmd_triage)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
