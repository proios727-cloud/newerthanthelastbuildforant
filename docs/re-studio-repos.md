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

## Clean-room rebuild engines — real, but unvetted (promising tier)

These are *real* open-source tools whose purpose (study an original, rebuild it clean-room)
matches this skill exactly. They are **not** in trusted-core because their metrics are not
organically plausible and they are very new — treat them as "evaluate in a sandbox," not
"depend on."

| Tool | Repo | Reported | Reality |
|---|---|---|---|
| Craft Anything | storytold/craft-anything | 22,227★ / 4,383 forks, Apache-2.0 + MIT, created 2026-10-31 | Real, pure-Rust clean-room engine, very active (349+ commits), README says **early alpha**. But 22k stars in ~8 days is not organic. |
| REA | morluto/rea | 442,949★ / 109,476 forks, MIT, created 2026-04-14 | Reachable MCP RE tool. Metrics are near-top-of-GitHub for a 7-month niche tool — implausible. Promoted with a "make any app free" piracy frame. REA's own README warns copycat repos exist, so if you do try it, confirm the source (morluto/rea, rea.tools, `rea-agents` npm). |

**Shared signal:** craft-anything, REA, and the rest of the `storytold` family
(`photocraft` 77,909★, `pdfcraft` 20,010★, `filmcraft`, `wordcraft` — all created in the last
few weeks) show the same 10k–80k-stars-in-weeks growth. That pattern is a coordinated-hype /
trending-campaign signature, not adoption. It doesn't make the code bad — it makes the
*social proof* worthless. Judge these on the code, in a VM, yourself.

Both ship installers that **edit your agent config** (`npx rea-agents@latest setup`;
craft-anything registers agents too). Read the repo and issues first, run in a disposable
VM/container, and prefer the trusted-core tools — they do the same decompile/trace/debug work
with no config rewrite. The `re-studio` skill requires your approval before any such setup;
keep it that way.

## ❌ Did not clear verification

| Tool | Repo | Why not |
|---|---|---|
| Seep Reverse Lab | angusdevgo/Seep-Reverse-Lab | 2,098★ / 791 forks, GPL-3.0, created 2026-09-23. Small, unknown author; high fork-to-star ratio; framed as an "autonomous authorization-audit / apk-reverse workbench" (CWE-602) whose attribution chain (`Open-tqtylab`, `newliver666/apk-reverse`) is small unknown repos. Authorization-bypass tooling against APKs is exactly where the own-software scope gate matters most. Not vetted; not recommended. |

## License note for rebuilds

GPL/LGPL tools (radare2, rizin, x64dbg, ImHex, dnSpyEx) are fine to **use** as analysis
tools. That does not put their license on code you write. Your rebuild's license is your
choice — just don't paste their source, or decompiled proprietary source, into it.
