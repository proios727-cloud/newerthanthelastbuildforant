# SPEC: royalty core (behaviour to match, written from public observation)

This describes **what a user can expect**, not how Mogul builds it. It contains no copied copy, code or assets. Each item names the EVIDENCE rows it relies on.

## Parity core (Backstage must do these to be "similar enough")

1. **Connect income sources.** A user links accounts from distributors, publishers, PROs, the MLC, SoundExchange, labels and international societies, and sees every source in one place. (E3, E11)
2. **Royalty check without an account.** A user enters an artist name and gets a short list of likely registration gaps before signing up. (E5)
3. **Find gaps.** For each song and recording the system flags missing or mismatched registrations (PRO work, MLC mechanicals, SoundExchange neighbouring rights) and shows an estimated amount at stake. (E1, E4)
4. **Fix gaps.** For each flag the user gets a registration ready to file, with the identifiers linked (ISRC, ISWC, IPI). (E1, E4)
5. **Monitor.** New releases are picked up and registered without being asked, and earnings are watched over time. (E4)
6. **Valuation.** An estimated catalog value for recordings and publishing, with an optional route to advance providers. (E6, E7)
7. **Assistant access.** The user's royalty data can be reached from an AI assistant through MCP. (E10)

## Oracle cases (input → expected observable output)

| Case | Input | Expected |
|---|---|---|
| O1 | A released song with a co-writer split and no PRO registration | A "performance royalties at risk" flag with the song and the split, and a "register" action |
| O2 | A recording with an ISRC but no ISWC link at the MLC | An "unmatched mechanicals" flag and a "register with the MLC" action |
| O3 | A new release appears in the distributor feed | It is added to the catalog and its registrations are queued within 1 sync |
| O4 | Royalty check for an artist with every registration complete | "No gaps found", with no false flags |
| O5 (must fail) | A flag shown with no source evidence attached | Rejected by the tests: every flag must cite its source row |

## Unknowns that block exact parity
E19–E21. Society coverage, matching logic and anomaly detection can only be specified at the level of behaviour. Backstage implements its own independent methods.
