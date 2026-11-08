# RE Studio: Agent Workflow (clean-room)

A multi-agent version of the `re-studio` pipeline for **your own software**. The point of
the split is the clean room: the agent that *writes code* never sees the original's
internals — only a behavior spec and input→output oracle cases. One agent doing both steps
is not a clean room.

```
scope ─▶ investigate ─▶ SPEC.md ─▶ │ wall │ ─▶ build ─▶ oracle ─▶ retry
        (evidence agent)           │      │    (build agent, spec-only)
```

## Roles

| Agent | Reads | Writes | Must NOT read |
|---|---|---|---|
| **Scope** (you + Claude) | the request | `re/<target>/SCOPE.md` | — |
| **Evidence** | original binary, decompiler/MCP output | `EVIDENCE.md`, `SPEC.md` | — |
| **Build** (separate session/subagent) | `SPEC.md` + oracle cases **only** | `build/`, tests | `EVIDENCE.md`, decompiled source, the original binary |
| **Oracle** | `build/`, oracle cases | pass/fail report | — |

## Run it

1. **Scope gate** (always first). Write `re/<target>/SCOPE.md`; basis = `own-software`.
   The skill refuses DRM/paywall/anti-cheat goals — leave that gate on.
2. **Evidence agent** — investigate with the trusted-core tools (see `re-studio-repos.md`).
   Log every claim in `EVIDENCE.md` as `confirmed | inferred | unknown`. Distil to `SPEC.md`:
   behavior + concrete input→output oracle cases, **no copied code**.
3. **Build agent** — launch a *fresh* subagent whose entire brief is `SPEC.md` + oracle
   cases. It writes `build/` and turns each oracle case into a test. Enforce the wall: do
   not paste evidence or decompiled snippets into its prompt.
4. **Oracle loop** — run the tests. On a mismatch, send it back to the evidence agent for
   that one behavior, update `SPEC.md`, rebuild. Add one case that *must* fail, to prove the
   comparison works.
5. **Stop** when all oracle cases pass and residual unknowns don't block the goal.

## Dispatching the build agent

- **Claude Code / this repo:** use the `Agent` tool (or `superpowers:subagent-driven-development`)
  with a prompt that contains only `SPEC.md` + oracle cases. Do not attach the original.
- **Cowork:** run Evidence and Build as separate sessions so context can't leak across the wall.
- Either way, keep `SCOPE.md`, `EVIDENCE.md`, `SPEC.md`, tests and `build/` in git so a later
  session resumes. `re/*/original/` and `re/*/decompiled/` are git-ignored — never commit the
  binary or decompiled proprietary source.

## Guardrails that stay on

- Basis stays `own-software` (or another lawful basis in `SCOPE.md`); if the goal drifts to
  unlocking paid features or redistributing code, stop.
- Run unknown binaries only in a disposable VM/container.
- A defensible clean room for commercial/contested targets uses **different people** for spec
  and build. The agent split is good discipline, not legal advice — for those cases, counsel.
