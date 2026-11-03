# GAPS: where Backstage can beat Mogul

**Mogul's position (E1–E16):** royalty recovery for musicians. It finds missing registrations, fixes them, monitors the catalog, values it, and offers distribution plus a human Concierge tier.

**Backstage's position:** the whole career, for visual artists *and* musicians. Royalty recovery is matched, then extended.

"Gap" means the feature does not appear in Mogul's public material (see SCOPE). The rank comes from the opportunity score in `.claude/skills/product-pain-miner/reports/creator-tools.md`.

## 1. Match first (the parity core, see SPEC.md)
Gap finder, one-click registrations (PRO, MLC, SoundExchange), always-on monitoring, catalog valuation, an AI-assistant/MCP connection. **These are table stakes. Without them Backstage loses a musician who compares the two.**

## 2. Revisions Mogul hasn't shown publicly, ranked

| # | Feature | Why it matters (pain rank: score) | Mogul evidence | In prototype? |
|---|---|---|---|---|
| 1 | **Visual-artist workspace.** Commissions, prints, licensing and grants sit beside music in one place. | Mogul's audience is musicians only (E2, E17). This opens the whole visual-artist market. | E2, E17 | Yes: Artist / Musician / Both switch |
| 2 | **AI-training protection.** Crawlers blocked by default, and licences exclude AI training. | #1: 51, the top-ranked pain | Mogul is waiting on the AI rules (E16) | Yes: Protection screen |
| 3 | **Commission scope plus deposit flow.** Finals are released only after payment, and extra changes are priced up front. | #2: 48 | Not in scope (E17) | Yes: Today queue and Money |
| 4 | **Stolen-art watch with batch takedowns** | #3: 38 | Not in scope (E17) | Yes: Protection |
| 5 | **Streams vs. statements reconciliation**, month by month, with expected and unexpected gaps labelled and a one-click query | #4: 38 | Unknown (E20) | Yes: Money |
| 6 | **Release-day profile and art checks.** Artist IDs, cover-art rules and the pitch window are checked before delivery. | #5: 38 and #15: 29 | Unknown (E21) | Yes: Protection |
| 7 | **Every income stream in one ledger**: gigs, merch, memberships, commissions and licences, each with a "why it's stuck" timeline | #10, #23, #24: payout holds and minimums | Royalties only (E17) | Yes: Money |
| 8 | **Tax as you go.** Quarterly set-aside, plus flags for duplicate 1099-K and 1099-MISC forms. | #11: 30 and #21: 23 | Not stated | Yes: Money |
| 9 | **Split sheets signed in the session.** One record feeds the distributor split, PRO, MLC and payouts, and collaborators need no subscription. | #13: 30 | Registrations, yes. Session split capture is not stated. | Partly: collab card |
| 10 | **1,000-stream threshold tracker** that flags tracks close to the line and suggests where to focus | #12: 30 | Not stated | No, next |
| 11 | **Stream-spike monitor and appeal pack**, ready before a distributor takedown | #16: 26 | Unknown (E21) | Yes: Protection |
| 12 | **Cross-discipline collab.** Cover and Canvas art credit, usage terms and the merch split are built in. | #17: 23 | Not in scope | Yes: collab card |
| 13 | **Agent approval queue.** Agents draft every pitch, invoice and registration, you approve each one, and each shows "why this". | Mogul's investor named ease of use as the challenge (E15). Concierge is a $75–125/mo human service (E8). | E8, E15, E18 | Yes: Today |
| 14 | **Live setlist reporting to the PRO**, triggered by each confirmed gig | #27: 14 | Not stated | Partly: Money (live row) |
| 15 | **Opportunities pipeline** for gigs, sync, playlists, open calls and grants, with fees spent compared against wins | #7: 32 and #8: 31 | Not stated | Yes: Today |
| 16 | **Owned fan list and platform-shutdown backup** | #14: 29 and #22: 21 | Not stated | Partly: Protection (shop backup) |

## 3. Pricing and trust levers
- **One public price list.** Mogul's own pricing page and help center disagree on what Concierge costs (E8). Backstage should publish one list and keep it consistent.
- **No cut of recovered royalties.** Mogul has tested taking a percentage of what it recovers (E13). Charge a flat fee and say so plainly.
- **A real free entry point.** Mogul removed its free tier (E12). Offer a free gap check and a free ledger, and charge for automation.

## 4. Recommended next builds
1. **Royalty Audit screen** to cover the parity core: a gap list per song (PRO, MLC, SoundExchange) with an amount at stake and "register" actions. This is needed to compete with Mogul head on.
2. **1,000-stream threshold tracker** (gap #10), the one top-15 gap not yet prototyped.
3. Once `usemogul.com` is allowed in the network settings, re-run with REA website analysis to close E19–E21 and confirm or remove each "not stated" row above.
