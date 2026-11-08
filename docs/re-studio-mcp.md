# RE Studio: MCP Wiring

How to give an agent tool-level access to the decompilers/debuggers, scoped to **your own
software**. All of this is local — the agent calls `decompile / xref / rename / debug` as
tools instead of you copy-pasting dumps.

## What connects over MCP

| Server | Repo | Backs | License | Needs |
|---|---|---|---|---|
| GhidraMCP | LaurieWired/GhidraMCP | Ghidra | Apache-2.0 | Ghidra + JDK 21 |
| ida-pro-mcp | mrexodia/ida-pro-mcp | IDA Pro | MIT | a paid IDA license |
| REA (MCP) | morluto/rea | fronts several of the above | MIT | ⚠️ see caution below |

Frida, radare2, jadx, Apktool, mitmproxy, angr, x64dbg, dnSpyEx, ImHex run as **CLIs/GUIs**,
not MCP — the agent drives them with the Bash tool. Only the three above need wiring.

## Claude Code (project-scoped)

Put an `.mcp.json` at the repo root (project scope keeps it out of your global config):

```jsonc
{
  "mcpServers": {
    "ghidra": {
      "command": "python",
      "args": ["-m", "ghidra_mcp"],   // per GhidraMCP README; some builds ship a bridge script
      "env": { "GHIDRA_INSTALL_DIR": "/abs/path/to/ghidra_12.1.x" }
    }
  }
}
```

Then: `claude mcp list` to confirm it loaded, and in-session check the `mcp__ghidra__*` tools
appear. Follow the server's own README for the exact command/transport — pin it to the
verified repo, not a blog snippet. Keep servers **project-scoped** so RE tooling isn't live
in every session.

## REA (optional, gated)

REA installs via `npx rea-agents@latest setup`, which **rewrites your agent config**. Given
the metric/pitch red flags in `re-studio-repos.md`, treat it as untrusted:

1. Read morluto/rea and its issues yourself first.
2. Install and run it in a disposable VM/container, not your host.
3. The `re-studio` skill requires your approval before REA setup — don't bypass that.
4. `npx -y rea-agents@latest doctor --client claude_code --json` is read-only; use it to
   inspect without committing to setup.

You don't need REA to run this pipeline — GhidraMCP + the trusted-core CLIs cover it.

## Trust & scope

- MCP servers here run **locally** against files you own; nothing phones a vendor for the
  analysis itself.
- Point them only at targets whose basis in `SCOPE.md` is `own-software` (or another lawful
  basis). The scope gate in the skill still applies when tools are MCP-driven.
- Don't commit `.mcp.json` env paths that leak machine specifics if you'd rather keep them
  local — `.mcp.json.example` + gitignore is fine.
