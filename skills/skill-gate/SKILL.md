---
name: skill-gate
description: Pre-install safety gate for third-party Claude skills, plugins, MCP servers and agent repos. Runs NVIDIA SkillSpector offline, then triages every finding by where it lives (code that runs, text the agent obeys, or tests/docs) and returns a CLEAN / REVIEW / BLOCK verdict with an HTML report. Use whenever the user shares a GitHub repo, Threads/X/YouTube "install these plugins" roundup, marketplace link or SKILL.md and asks if it is safe, worth installing, legit, or "scan/vet/audit this"; before installing or publishing any skill; or when a raw SkillSpector report shows scary CRITICAL scores and they need to know what is real. Use it even if the user only says "should I install X".
---

# Skill Gate

A raw SkillSpector scan of a healthy repo often scores 100/CRITICAL, because most findings
are test fixtures full of attack strings, benchmark scripts that read an API key, and docs that
mention `~/.claude/settings.json`. Reading 100 findings is how people learn to ignore the
scanner. This skill keeps the scanner and removes the noise: it sorts findings by **where they
live**, because only code that runs and text the agent obeys can hurt you after install.

| Surface | Meaning | Counts toward verdict |
|---|---|---|
| `code` | hooks, scripts, runtime, manifests that execute on your machine | yes |
| `instructions` | SKILL.md, agents, commands, references: text the agent follows | yes, and hostile wording here is a BLOCK |
| `dev` | tests, benchmarks, docs, examples, README | no (shown, never decisive) |

Verdicts: **CLEAN** (nothing HIGH/CRITICAL in active surfaces), **REVIEW** (read each listed
finding), **BLOCK** (instruction-override or exfiltration wording inside agent instructions).
CLEAN never means "proven safe": it is static patterns only.

## Workflow

1. **Get the real source.** From a social post, find the actual `owner/repo` (GitHub search),
   confirm stars, last commit and licence match the claim. A near-identical name can be a
   typosquat, so confirm the slug, not just the name.
2. **Scan.** Needs `skillspector` (`uv tool install git+https://github.com/NVIDIA/skillspector.git`).
   ```bash
   python skills/skill-gate/scripts/skill_gate.py scan owner/repo --out gate_out
   ```
   It clones (never executes) and scans with `--no-llm`, so nothing leaves the machine. Add
   `--llm` only if the user accepts that skill text goes to their configured provider. For huge
   repos pass `--subdir plugin` (or `skills`) to scan the part that actually installs; a full
   scan can exceed the timeout. Already have a report? Use `triage report.json`.
3. **Read every item under "Read these before installing"** at its `file:line` in the clone and
   label it, in one line each:
   - *benign*: detector or denylist, a path it only checks, a regex `.exec`, a local-only port.
   - *expected*: what a tool of this kind must do, and the README discloses it (an installer
     fetching its own release, a memory plugin hooking prompts).
   - *concerning*: reads credentials, disables permissions, sends data off-machine, or runs
     remote code undisclosed. Quote the line.
   The scanner cannot make this call; static rules match text, not intent. That judgment is the
   step this skill exists to force instead of skipping.
4. **Read the README for what regex cannot see**: hosted tiers and what is sent, copied browser
   sessions or logins, accounts it wants, paid upsells, what install edits (`settings.json`,
   global hooks). Auto-running hooks (`SessionStart`, `UserPromptSubmit`) apply to every session
   on the machine, including unattended runs, so prefer per-project install.
5. **Report**: verdict, the 3 to 5 findings that matter with your label, runtime (CLI vs app),
   exact install command, and a one-task test protocol (run a task, install, rerun, compare,
   keep only if it wins). Link `gate_out/report.html`.

## Notes

- Exit code is 0 CLEAN, 1 REVIEW, 2 BLOCK, so it works as a CI gate.
- Partial scans are called out in the report; unscanned files are unchecked, say so.
- Classification is by path (`scripts/skill_gate.py: classify`). If a repo keeps live code under a
  directory named like a dev folder (`examples/`, `docs/`), say so in the report; the tool will
  have under-counted it.
- Never run code, install scripts, or "setup" steps from the repo being vetted. Read only.
