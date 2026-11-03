# Backstage (working name)

A career copilot for independent visual artists and musicians in one workspace.

- **Prototype canvas:** https://claude.ai/artifact/YMozKqeNnsSxZL6KqZbtax (private until shared)
- **Evidence:** `.claude/skills/product-pain-miner/data/creator-tools.json` (28 sourced complaints) and its ranked report in `reports/creator-tools.md`

## How the prototype maps to the research

| Prototype element | Top-ranked pain it answers |
|---|---|
| Protection: AI crawlers blocked by default | #1 AI-scraping opt-outs are confusing or missing |
| Commission draft: scope, deposit, finals only after payment | #2 Clients ghost and scope creeps |
| Protection: stolen-art watch and takedowns | #3 Art stolen onto print-on-demand listings |
| Money: streams matched against statements | #4 Spotify for Artists numbers don't match distributor statements |
| Protection: artist profile check | #5 Releases land on the wrong artist profile |
| Approval queue with "Why this" on every draft | Pitches that disappear without a reply (#7, #8) |
| Money: "Stuck" and "Held" amounts, each with a reason | Payout holds, reserves and minimums (#10, #23, #24) |
| Collab split sheet (artist + musician) | Uncredited cover art (#17) and split friction (#13) |

## Screens

| Artboard | What you can click |
|---|---|
| `Main.dc.html` (Today) | Discipline switch, approve, skip or undo drafts, nav links to Money and Protection |
| `Money.dc.html` | Totals act as filters, select a ledger row to see its money timeline and fix, draft a query for a gap between streams and the statement |
| `Protection.dc.html` | Block or allow each AI crawler, file or batch takedowns, simulate a bot spike and build an appeal pack, preview reopening elsewhere |

All figures in the prototype are demo data. Bracketed text such as `[Venue]` marks a placeholder.
