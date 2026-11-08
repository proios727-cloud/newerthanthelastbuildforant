# RE Studio: Verified Repo Reference

Scope: tools for studying and rebuilding **software you own** (interop, lost-source
recovery, debugging your own binaries). Pairs with the `re-studio` skill and
`docs/re-studio.md`.

**Verified 2026-11-08** via the GitHub API (stars/license/last-push) and `git ls-remote`
(reachability). Star counts are a freshness signal, not an endorsement. `NOASSERTION`
means GitHub could not map the license to an SPDX id, not that the project is unlicensed —
the real license is noted in the row.

## Trusted core — use these first

| Tool | Repo | Stars | License | Last push | Role |
|---|---|--:|---|---|---|
| Ghidra | NationalSecurityAgency/ghidra | 98,691 | Apache-2.0 | 2026-11-06 | Free decompiler/disassembler (NSA) |
| GhidraMCP | LaurieWired/GhidraMCP | 11,840 | Apache-2.0 | 2026-10-10 | MCP bridge to drive Ghidra from an agent |
| ida-pro-mcp | mrexodia/ida-pro-mcp | 13,412 | MIT | 2026-09-26 | MCP bridge for IDA Pro (needs paid IDA) |
| jadx | skylot/jadx | 51,690 | Apache-2.0 | 2026-11-07 | APK/DEX → Java |
| Apktool | iBotPeaches/Apktool | 27,087 | Apache-2.0 | 2026-11-02 | Decode/rebuild APK resources & smali |
| Frida | frida/frida | 22,708 | wxWindows (BSD-like) | 2026-11-07 | Runtime instrumentation / hooking |
| ILSpy | icsharpcode/ILSpy | 27,012 | MIT | 2026-11-08 | .NET decompiler |
| dnSpyEx | dnSpyEx/dnSpy | reachable¹ | GPL-3.0 | active | Maintained dnSpy fork: .NET debug/edit |
| radare2 | radareorg/radare2 | 25,358 | LGPL-3.0 | 2026-11-08 | CLI RE framework |
| rizin | rizinorg/rizin | 4,154 | LGPL-3.0 | 2026-11-08 | radare2 fork, cleaner API |
| x64dbg | x64dbg/x64dbg | 50,243 | GPL-3.0 | 2026-11-08 | Windows user-mode debugger |
| ImHex | WerWolv/ImHex | 55,788 | GPL-2.0 | 2026-10-09 | Hex editor + file-format pattern language |
| angr | angr/angr | 9,347 | BSD-2-Clause | 2026-11-08 | Symbolic execution / binary analysis |
| mitmproxy | mitmproxy/mitmproxy | 46,729 | MIT | 2026-11-04 | HTTPS interception proxy |
| raddebugger | EpicGames/raddebugger | 8,795 | MIT | 2026-11-06 | Fast Windows debugger (RAD/Epic) |

¹ dnSpyEx/dnSpy is reachable and maintained; the search index returned no metadata at
verification time. License/role are from the repo itself.

## Index lists (method & discovery)

| List | Repo | Stars | Note |
|---|---|--:|---|
| awesome-reverse-engineering | alphaSeclab/awesome-reverse-engineering | 5,198 | Large established index |
| reverse-engineering | wtsxDev/reverse-engineering | 10,770 | Large established index |
| awesome-reverse-engineering | morluto/awesome-reverse-engineering | 1,953 | Newer; same owner as REA — see caution |
| awesome-ai-reverse-engineering | zhuyansen/awesome-ai-reverse-engineering | 91 | Small AI-RE index |

## ⚠️ Caution — verify before you install

| Tool | Repo | Reported | Why flagged |
|---|---|---|---|
| REA | morluto/rea | 442,949★ / 109,476 forks, created 2026-04-14, MIT | A 7-month-old niche RE tool showing near-top-of-GitHub metrics is not organically plausible, and its promotion ("make any app free by the afternoon") is a piracy frame. The repo is reachable, but treat the numbers and the pitch as unverified. |

REA's installer (`npx rea-agents@latest setup`) **edits your agent config**. Before running it:
read the repo and its issues yourself, run it in a disposable VM/container, and prefer the
trusted-core tools above, which do the same decompile/trace/debug work with no config rewrite.
The `re-studio` skill already requires your approval before any REA setup — keep it that way.

## License note for rebuilds

GPL/LGPL tools (radare2, rizin, x64dbg, ImHex, dnSpyEx) are fine to **use** as analysis
tools. That does not put their license on code you write. Your rebuild's license is your
choice — just don't paste their source, or decompiled proprietary source, into it.
