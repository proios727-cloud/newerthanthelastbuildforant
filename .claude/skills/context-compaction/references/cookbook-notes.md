# Source: Anthropic cookbook "Automatic Context Compaction"

Reference run: 5 support tickets × 7 tool calls each (fetch, classify, KB search, priority, route, draft, complete), Sonnet, threshold 5k.

| | Baseline | Compaction |
|---|---|---|
| Turns | 37 | 26 |
| Input tokens | 204,416 | 82,171 |
| Total tokens | 208,838 | 86,446 (−58.6%) |
| Compactions | — | 2 (31→1, 15→1 messages) |

Takeaways
- `compaction_control` keys: `enabled` (required), `context_token_threshold` (default 100k), `model`, `summary_prompt`.
- Detect a compaction by watching for `len(runner._params["messages"])` to drop.
- The summaries kept the in-progress ticket and its step, which avoided duplicate work after a reset.
- Known limitation: server-side sampling loops (web search, server-side thinking) trip it early because cache tokens accumulate.
- For newer models the cookbook recommends server-side compaction instead of SDK compaction.

Fixes relative to the cookbook
- The cookbook's manual loop stores the summary as a single user message. If the next turn also starts with a user message, the history has two user turns in a row. `ManualCompactor` adds an assistant ack after the summary.
- The cookbook's prose says "79,000 tokens", but its own output shows 82,171 input / 86,446 total.
