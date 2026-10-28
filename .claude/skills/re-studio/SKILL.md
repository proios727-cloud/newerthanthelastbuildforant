---
name: re-studio
description: Study how a feature in an app works and rebuild it as original code, using REA (Reverse Engineer Anything) or Ghidra/jadx/Frida with a spec → build → oracle loop. Use when the user wants to understand an app, binary, APK, Electron app, website, or contract bytecode, write a behavior spec of a feature, or rebuild a feature they saw elsewhere. Starts with a scope check and refuses cracking, DRM or anti-cheat bypass, and unlocking paid features.
---

# RE Studio

Pipeline: **scope → investigate → SPEC.md → build → oracle → retry**.
Reference for tools, install and links: `docs/re-studio.md`.

## 0. Scope gate (always first)

Before touching a target, write `re/<target>/SCOPE.md` with:

- **Target:** the name, version and path of the binary, APK or app.
- **Basis:** one of `own-software`, `open-source`, `ctf`, `malware-sandbox`, `authorized-test` (who authorized it, and in writing?), `interop`, `personal-learning-on-owned-copy`.
- **Goal:** the one feature or question you're answering.
- **Out of scope:** list it explicitly.

Stop and tell the user if the goal is any of these:
- removing licensing, DRM, paywalls or anti-cheat
- using a paid feature without paying
- extracting or redistributing proprietary code, assets, keys or decompiled source
- acting on servers or accounts the user does not own

Offer the lawful version instead: describe the behavior, then build an original implementation.

## 1. Preflight

```bash
node -v                                                  # 22.19+, 24.11+ or 26+ (not 23/25)
npx -y rea-agents@latest doctor --client claude_code --json
```

If REA isn't installed, show the user `npx rea-agents@latest setup`. Don't run it without approval, because it edits the agent config.
Run unknown binaries only in a disposable VM or container, never on the host.

## 2. Investigate (evidence only)

Pick the engine for the target type. The table is in `docs/re-studio.md` under "Engines by target".
Prefer REA's guided workflows: `investigate_feature`, `trace_crash`,
`compare_application_versions`, `prepare_bounded_process_capture`.

Log every claim in `re/<target>/EVIDENCE.md`:

| # | Claim | Evidence (function / file:line / call / capture) | Status |
|---|---|---|---|
| 1 | Export writes `notes.csv` to Downloads | `main.js` handler for `notes:export` | confirmed |

Status is `confirmed`, `inferred`, or `unknown`. Finish with `audit_residual_unknowns`.

## 3. SPEC.md (behavior, not code)

Write `re/<target>/SPEC.md`:
- **Behavior:** inputs, outputs, state, timing, error cases, edge cases.
- **Oracle cases:** concrete input → expected output pairs, observed from the original.
- **No copied code**, no decompiled snippets, no proprietary constants beyond the observable ones.
  Name each `EVIDENCE.md` row the spec relies on.

## 4. Build (clean-room session)

Build in a **separate session or subagent** whose only input is SPEC.md and the oracle cases.
It must not read EVIDENCE.md, the decompiled output or the original binary.
Put the implementation in `re/<target>/build/` (or wherever the user names) and write the oracle cases as tests.

This separation is a practical discipline, not legal advice. For commercial or
contested targets, tell the user that a defensible clean room uses different people
for spec and build, and that they should talk to counsel.

## 5. Oracle loop

- Run the tests. On a mismatch, go back to step 2 for that behavior, update SPEC.md, and rebuild.
- **Test your tests:** add at least one case that must fail, to prove the comparison works.
- Stop when all oracle cases pass and `audit_residual_unknowns` shows nothing that blocks the goal.

## 6. Hand-off

Commit `SCOPE.md`, `EVIDENCE.md`, `SPEC.md`, the tests and the build so a later session can resume.
Never commit decompiled proprietary source, extracted assets or the original binaries.
Keep them in `re/<target>/original/` and `re/<target>/decompiled/`, which `.gitignore` already excludes.
Report: the goal, the oracle pass rate, open unknowns, and what was deliberately left out.
