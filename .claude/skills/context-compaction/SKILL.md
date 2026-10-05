---
name: context-compaction
description: Keep long-running Claude agents (ticket queues, desk seats, shadow runners, multi-hour chat loops) under the context limit by summarizing history and resuming from the summary. Use when an agent loop processes many items in sequence, when cumulative input tokens grow linearly per turn, when a run hits or nears the 200k window, or when someone asks about compaction, compaction_control, context rot, or "summarize and continue".
---

# Context Compaction

When a loop sends the whole history every turn, input tokens grow with each turn and the total cost grows with the square of the turn count. Compaction replaces the history with a structured summary when a threshold is crossed. In the reference run (5 tickets, 7 tool calls each), total tokens fell from 208.8k to 86.4k (−58.6%) and the work came out the same.

## Pick the mechanism

| Situation | Use |
|---|---|
| Model supports server-side compaction (current Claude 4.6+ / 5 family) | **Server-side compaction**. The API manages it with no SDK code. Check `claude-api` skill for the param. |
| `client.beta.messages.tool_runner` with client-side tools | **`compaction_control`** (SDK ≥ 0.74.1) |
| Plain `messages.create` loop, no tool runner | **Manual**: `scripts/compaction.py` → `ManualCompactor` |
| Server-side tools (web search) or server-side extended thinking | **Avoid SDK compaction.** Cached tokens accumulate and trigger it early. |

## Tool runner (automatic)

```python
runner = client.beta.messages.tool_runner(
    model=MODEL, max_tokens=4096, tools=tools, messages=messages,
    compaction_control={
        "enabled": True,
        "context_token_threshold": 20_000,   # default 100_000
        "model": "claude-haiku-4-5",          # optional, a cheaper summarizer
        "summary_prompt": QUEUE_SUMMARY_PROMPT,  # optional, from scripts/compaction.py
    },
)
for msg in runner:
    ...  # compaction happened when len(runner._params["messages"]) drops
```

## Manual loop

```python
from compaction import ManualCompactor
c = ManualCompactor(client, model=MODEL, threshold=50_000)
reply = c.send("next user message")   # compacts automatically after the turn
c.compactions, c.messages             # stats and current history
```

## Threshold guide

- **5k–20k**: independent items in sequence (tickets, markets, symbols). Compact often.
- **50k–100k**: multi-phase workflows with a few natural checkpoints.
- **100k–150k**: work that needs a lot of raw history. Compactions are rare and each call costs more.
- Set the threshold to at least 3× the expected summary size, or the summary itself will trigger another compaction.

## Summary prompt rules

Use `GENERIC_SUMMARY_PROMPT` (task, state, discoveries, next steps, context to preserve) or `QUEUE_SUMMARY_PROMPT` (one line per completed item plus progress). Tailor it so the summary keeps:
- IDs and the decisions made for each completed item (category, priority, routing, P&L)
- the item **in progress** and the step it is on, so the agent does not redo or skip work
- facts learned from tools that later items will reuse (KB facts, fee schedules, team names)
- promises made to the user and any hard limits (risk caps, approval words)

Always wrap the summary in `<summary></summary>`.

## When NOT to compact

- The task finishes in under ~50k tokens.
- You need a full audit trail. Write it to disk or a DB first, then compact (for example the desk's `shadow.jsonl`).
- Each step depends on exact raw detail from every earlier step.

## Verify

- Log per-turn input tokens. After each compaction they should fall back near the base prompt size.
- Diff the final per-item outcomes against a no-compaction baseline on a small queue.
- Run `python -m pytest tests/test_compaction_skill.py` (offline, mocked client).
