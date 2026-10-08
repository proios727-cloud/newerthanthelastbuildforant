"""Manual context compaction for plain messages.create loops.

Use compaction_control on tool_runner, or server-side compaction, when either is available.
"""

from __future__ import annotations

from typing import Any

GENERIC_SUMMARY_PROMPT = """You have been working on the task described above but have not yet completed it. Write a continuation summary that lets you resume efficiently in a new context window where this summary replaces the conversation history. Be structured, concise, and actionable:

1. **Task Overview**: the user's core request, success criteria, constraints.
2. **Current State**: what is done, artifacts produced (with paths), the item in progress and its exact step.
3. **Important Discoveries**: constraints found, decisions and rationale, errors and fixes, approaches that failed.
4. **Next Steps**: specific remaining actions in priority order, blockers, open questions.
5. **Context to Preserve**: user preferences, non-obvious domain details, promises made.

Err on the side of including anything that prevents duplicate work or repeated mistakes.
Wrap your summary in <summary></summary> tags."""

QUEUE_SUMMARY_PROMPT = """You are processing items from a queue. Write a focused summary that preserves:

1. **COMPLETED ITEMS**: one line each: ID, name, decisions made (category/priority/route/outcome).
2. **IN PROGRESS**: the current item, steps done, steps remaining.
3. **REUSABLE FACTS**: facts learned from tools that later items will need.
4. **PROGRESS**: completed count and remaining count.
5. **NEXT STEP**: the exact next action.

Wrap your summary in <summary></summary> tags."""


def total_tokens(usage: Any) -> int:
    """Input tokens (including cache reads and writes) plus output tokens for one response."""
    return (
        usage.input_tokens
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        + usage.output_tokens
    )


def _text(content: Any) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text")


class ManualCompactor:
    """Chat loop that replaces its history with a summary once a turn exceeds `threshold` tokens."""

    def __init__(
        self,
        client: Any,
        model: str,
        threshold: int = 50_000,
        summary_prompt: str = GENERIC_SUMMARY_PROMPT,
        summary_model: str | None = None,
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.threshold = threshold
        self.summary_prompt = summary_prompt
        self.summary_model = summary_model or model
        self.max_tokens = max_tokens
        self.system = system
        self.messages: list[dict[str, Any]] = []
        self.compactions = 0
        self.last_tokens = 0

    def _create(self, model: str, messages: list[dict[str, Any]]) -> Any:
        kwargs: dict[str, Any] = {"model": model, "max_tokens": self.max_tokens, "messages": messages}
        if self.system:
            kwargs["system"] = self.system
        return self.client.messages.create(**kwargs)

    def send(self, user_content: Any) -> str:
        self.messages.append({"role": "user", "content": user_content})
        resp = self._create(self.model, self.messages)
        self.messages.append({"role": "assistant", "content": resp.content})
        self.last_tokens = total_tokens(resp.usage)
        if self.last_tokens > self.threshold:
            self.compact()
        return _text(resp.content)

    def compact(self) -> str:
        resp = self._create(
            self.summary_model, self.messages + [{"role": "user", "content": self.summary_prompt}]
        )
        summary = _text(resp.content)
        # The summary is a user turn, so the next send() would put two user turns in a row.
        # Fold it and the next message together by seeding history with a summary plus an ack.
        self.messages = [
            {"role": "user", "content": summary},
            {"role": "assistant", "content": "Understood. Resuming from the summary."},
        ]
        self.compactions += 1
        return summary
