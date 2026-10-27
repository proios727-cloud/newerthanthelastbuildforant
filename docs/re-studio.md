# AI Reverse-Engineering Studio: Stack Reference

**Pipeline:** `binary → REA (MCP) → SPEC.md → rebuild → oracle → retry`

## 01 · Analysis core (the agent drives these)
| Tool | Role | Repo |
|---|---|---|
| REA | One MCP server that fronts the other tools | github.com/morluto/rea |
| Ghidra | Free decompiler/disassembler (NSA) | github.com/NationalSecurityAgency/ghidra |
| GhidraMCP | MCP bridge so the agent can drive Ghidra | github.com/LaurieWired/GhidraMCP |
| ida-pro-mcp | MCP bridge for IDA Pro (needs a paid IDA license) | github.com/mrexodia/ida-pro-mcp |

## 02 · Mobile & managed code
| Tool | Role | Repo |
|---|---|---|
| jadx | APK/DEX → Java | github.com/skylot/jadx |
| Apktool | Decode/rebuild APK resources and smali | github.com/iBotPeaches/Apktool |
| Frida | Runtime instrumentation and hooking | github.com/frida/frida |
| ILSpy | .NET decompiler | github.com/icsharpcode/ILSpy |

## 03 · Native / low-level
| Tool | Role | Repo |
|---|---|---|
| radare2 | CLI RE framework | github.com/radareorg/radare2 |
| rizin | radare2 fork, more stable API | github.com/rizinorg/rizin |
| x64dbg | Windows user-mode debugger | github.com/x64dbg/x64dbg |
| ImHex | Hex editor with a pattern language for file formats | github.com/WerWolv/ImHex |
| angr | Symbolic execution and binary analysis (Python) | github.com/angr/angr |

## 04 · Runtime & network
| Tool | Role | Repo |
|---|---|---|
| mitmproxy | HTTPS interception proxy | github.com/mitmproxy/mitmproxy |
| dnSpyEx | .NET debugger/editor (maintained fork) | github.com/dnSpyEx/dnSpy |
| RAD Debugger | Fast Windows debugger (Epic/RAD) | github.com/EpicGamesExt/raddebugger |

## 05 · Indexes & method
- awesome-ai-reverse-engineering: graded list of about 122 repos (github.com/zhuyansen/…)
- awesome-reverse-engineering: maintained by the REA author (github.com/morluto/…)
- REA workflows: investigation prompts that ship with REA
- Clean-room loop: SPEC.md → independent rebuild → oracle diff against the original → iterate

## What's actually new
The tools are 5–20 years old. What's new is the **MCP layer**: an agent can call
decompile/xref/rename/debug as tools, and the **oracle loop** turns "explain this
binary" into a testable target (does the rebuild match the original's I/O?).

## Practical limits
- Packed, obfuscated, or VM-protected binaries (Themida/VMProtect, DexGuard) still stall agents.
- Decompiler output is lossy, so a SPEC is a hypothesis until an oracle confirms it.
- Context cost is high: large binaries need function-level chunking, not whole-program dumps.

## Guardrails (before you point it at an app)
- **OK:** your own software, open source, CTFs, malware samples in a sandbox, authorized
  pentests, and interoperability work where local law allows (e.g. DMCA §1201(f), EU Software Directive Art. 6).
- **Risky:** commercial apps whose EULA bans RE, DRM/anti-cheat bypass, cloning a competitor.
  A real clean room needs **two separate parties**: one writes the spec, the other builds from
  the spec alone. One agent doing both steps is *not* a clean room legally.
- Run untrusted binaries only in a disposable VM/container, never on your host.

---

# REA Field Guide (from the course thread, cleaned up)

> Source: x.com/0xcodila/status/2109623431763292649
> These details come from a social-media course and have not been checked against the REA repo.
> Confirm against github.com/morluto/rea and rea.tools/get-started before relying on them.

## Install (about 5 min)
1. Node **22.19+, 24.11+, or 26+**. Versions 23 and 25 are not supported. `node -v`
2. `npx rea-agents@latest setup` → pick Claude Code → review the plan (it backs up your config) → approve
3. Restart the agent completely (on desktop apps, quit with ⌘Q; closing the window isn't enough)
4. Verify: `npx -y rea-agents@latest doctor --client claude_code --json` (read-only)
5. Optional global CLI: `npm i -g rea-agents` · update with `rea update` · remove with `rea uninstall`

## Engines by target
| Target | Needs | Entry command |
|---|---|---|
| Electron / JS desktop apps | nothing | `rea analyze-javascript-application /abs/path --json` |
| .NET (incl. many Unity games) | nothing | via MCP |
| Native exe / Mac / DOS | Ghidra 12.1.x + JDK 21 (or Hopper / IDA) | `rea function /abs/prog main --provider ghidra --json` |
| Android APK | JDK 17+, jadx-headless-mcp 0.7.1 (`REA_JADX_MCP_JAR`) | `rea inspect-android-package App.apk` |
| Websites / HAR | Chrome-family browser | via MCP |
| EVM bytecode | Linux x64 | `rea inspect-evm-interface ./runtime.hex hex --json` |

Electron bundles live at: Mac `/Applications/<App>.app/Contents/Resources/app.asar` ·
Windows `%LOCALAPPDATA%\Programs\<App>\resources\app.asar` · Linux `/opt/<App>/resources/app.asar`

## Built-in MCP workflows
`investigate_feature` · `compare_application_versions` · `verify_reconstruction` ·
`trace_crash` · `audit_residual_unknowns` · `prepare_bounded_process_capture`

## Prompt pack (duplicates removed)
- **Practice:** Download https://rea.tools/examples/notes-example.zip into a new folder, unpack it, and use REA to find what happens when I click Export notes.
- **Feature → build:** Use REA to investigate how [feature] works in [app]. Write SPEC.md covering behavior, inputs, outputs, and edge cases, with no copied code. Then build from SPEC.md in ./my-version, write tests from the observed behavior, and iterate until they pass.
- **App privacy audit:** Use REA on this APK. List every permission, every analytics/tracking SDK, and every domain it contacts, with the class and method for each.
- **Token check:** Use REA on this contract bytecode. List the state-changing functions and flag mint, blacklist, pause, fee change, and owner-only transfer. Mark each as confirmed or inferred.
- **Update diff:** Run compare_application_versions on [old] vs [new] of [app]. What actually changed, with evidence?
- **Unknowns:** Run audit_residual_unknowns on this investigation. What is still unproven?

## Lessons from the long-run rebuilds (Touhou, DX-Ball)
- Give the agent a clear goal and **acceptance criteria**, i.e. an oracle.
- Keep notes and checks in git so the next session can resume.
- Treat every agent explanation as a hypothesis.
- **Test your tests.** A broken comparison once let a wrong function pass.

## The line
Study → spec → **your own code** = fine. Copying their code, unlocking paid features,
or publishing decompiled source = what gets you sued. ("Free TradingView premium
indicators" is on the wrong side of that line. Building your own charting engine is fine.)

## Links from the article
**Official REA**
- Repo: https://github.com/morluto/rea
- Site: https://rea.tools/
- Get started: https://rea.tools/get-started/
- First investigation: https://rea.tools/first-investigation/
- What you can analyze: https://github.com/morluto/rea#what-you-can-analyze
- Disclaimer: https://github.com/morluto/rea#disclaimer
- Android guide: https://github.com/morluto/rea/blob/main/docs/android-analysis.md
- EVM guide: https://github.com/morluto/rea/blob/main/docs/evm-bytecode.md
- MCP guided prompts: https://github.com/morluto/rea/blob/main/docs/mcp-prompts.md

**Showcases**
- Aegis (133/133 tests): https://rea.tools/showcase/aegis/
- DX-Ball (3,205 x86 tests): https://rea.tools/showcase/dx-ball/
- Notion copy trace: https://rea.tools/showcase/notion/
- Touhou rebuild (696/697 exact): https://rea.tools/blog/touhou-reconstruction/

**Community rebuilds**
- Super Mario Sunshine PC port: https://github.com/chasem-dev/sms-pc-port
- PS1 static recompiler (Tomba!): https://1379.tech/i-built-a-ps1-static-recompiler-with-no-prior-experience-and-claude-code/
- Kotaku on browser ports: https://kotaku.com/we-might-be-cooked-as-these-vibe-coded-web-browser-ports-of-halo-the-simpsons-hit-and-run-and-gta-vice-city-seem-to-work-perfectly-2000743300

**Limits and legal background**
- Why it can't hack your bank: https://rafaelroman.com/articles/ai-reverse-engineering-cant-hack-your-bank/
- Clean-room design: https://en.wikipedia.org/wiki/Clean-room_design
- Sega v. Accolade: https://en.wikipedia.org/wiki/Sega_v._Accolade
- Sony v. geohot settlement: https://www.techspot.com/news/43246-sony-and-geohot-settle-over-ps3-hacking-lawsuit.html

**Agent setup**
- Claude Code: https://code.claude.com/docs/en/setup
