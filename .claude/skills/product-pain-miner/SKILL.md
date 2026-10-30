---
name: product-pain-miner
description: Mine public complaints about an everyday product category (kitchen, bathroom, cleaning, laundry, bedroom, packaging, etc.), classify each complaint by root design failure, score it, and turn the top pains into redesign concepts. Maintains one JSON dataset per category and regenerates a ranked report from it. Use when the user asks to redesign household or everyday items, find what people hate about a product, run a "pain → redesign" pass, or refresh an existing category.
---

# Product Pain Miner

Turn negative public opinion about everyday items into ranked, defensible redesign concepts.
The JSON dataset in `data/<category>.json` is the source of truth. The report in `reports/<category>.md`
is always generated from it and never edited by hand.

## Files

| Path | Purpose |
|---|---|
| `references/failure-modes.md` | The 7 root design failures used for classification, with check questions |
| `data/<category>.json` | One dataset per category (schema below) |
| `reports/<category>.md` | Generated ranked report |
| `scripts/pain_index.py` | Validates a dataset, scores it, renders the report. Stdlib only |

## Workflow

1. **Scope.** Confirm the category and, optionally, the items to cover. If `data/<category>.json` exists,
   this is a *refresh*: load it, keep existing entries, and add or update them.
2. **Gather complaints.** Prefer sources where people complain unprompted:
   - Retailer 1–3★ reviews (Amazon, Target, Home Depot, Best Buy)
   - Reddit: r/mildlyinfuriating, r/assholedesign, r/BuyItForLife (the inverse: what lasts), category subs
   - CPSC recalls / SaferProducts.gov for safety failures
   - "Hack" videos and articles: every workaround points to a design gap
   Use whatever search tools are available (WebSearch, Exa, Nimble, Bright Data, Tavily). Spawn one
   research agent per sub-area when the category is large (e.g. appliances / cookware / storage / packaging).
   Record at least one source URL per entry. Never invent sources.
3. **Classify.** Read `references/failure-modes.md` and assign exactly one primary `failure_mode`.
4. **Score** each entry 1–5 on:
   - `frequency`: how often the complaint appears across sources (5 = in nearly every thread/review set)
   - `severity`: cost to the user (1 = mild annoyance, 3 = wasted money/time, 5 = injury or health risk)
   - `workaround`: how hard it is to avoid (1 = easy fix exists, 5 = no workaround)
   - `feasibility`: how buildable the redesign is (1 = new tech needed, 5 = cheap change to existing product)
5. **Redesign.** Write one concrete `redesign` per entry: what changes physically or behaviorally, not a slogan.
   Optional `prior_art` names an existing product that already solves it (good signal the fix is feasible).
6. **Validate and render:**
   ```bash
   python3 .claude/skills/product-pain-miner/scripts/pain_index.py .claude/skills/product-pain-miner/data/<category>.json \
     --out .claude/skills/product-pain-miner/reports/<category>.md
   ```
   Fix every problem it reports. It refuses to render an invalid dataset.
7. **Report back** to the user: top 5 by opportunity, which failure modes dominate, and any entries
   with weak evidence (one source only).

## Scoring (computed by the script, do not hand-edit)

- `pain = frequency × severity × workaround` normalized to 0–100
- `opportunity = pain × feasibility / 5`; this is the ranking key: high pain that is cheap to fix ranks first

## Dataset schema

```json
{
  "category": "kitchen",
  "updated": "YYYY-MM-DD",
  "entries": [
    {
      "id": "nonstick-coating-peels",
      "item": "Nonstick pans & air-fryer baskets",
      "complaint": "Coating flakes within months; users worry about eating it",
      "failure_mode": "wears-out-early",
      "frequency": 5, "severity": 4, "workaround": 3, "feasibility": 3,
      "redesign": "…",
      "prior_art": "optional",
      "sources": ["https://…"]
    }
  ]
}
```

`id` is kebab-case and unique. `sources` must be http(s) URLs.

## Rules

- Evidence before ideas: an entry without a real source URL is invalid.
- One complaint per entry. Split compound complaints.
- Keep redesigns ethical and safe; do not propose removing safety features (e.g. child-resistant caps) without an equivalent.
- On a refresh, update `updated`, adjust scores when new evidence changes them, and never delete entries silently;
  mention removals to the user.
