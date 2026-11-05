import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/context-compaction/scripts"))
from compaction import ManualCompactor, total_tokens  # noqa: E402


class FakeClient:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        text = "<summary>S</summary>" if kw["messages"][-1]["content"].startswith("You have") else "ok"
        usage = NS(input_tokens=self.tokens.pop(0), output_tokens=10,
                   cache_creation_input_tokens=None, cache_read_input_tokens=None)
        return NS(content=[NS(type="text", text=text)], usage=usage)


def test_total_tokens_counts_cache():
    u = NS(input_tokens=100, output_tokens=5, cache_creation_input_tokens=20, cache_read_input_tokens=30)
    assert total_tokens(u) == 155


def test_no_compaction_under_threshold():
    c = ManualCompactor(FakeClient([100, 200]), model="m", threshold=1000)
    c.send("a"); c.send("b")
    assert c.compactions == 0 and len(c.messages) == 4


def test_compacts_and_keeps_alternation():
    client = FakeClient([100, 2000, 50, 120])
    c = ManualCompactor(client, model="m", threshold=1000, summary_model="cheap")
    c.send("a"); c.send("b")
    assert c.compactions == 1
    assert client.calls[-1]["model"] == "cheap"
    assert [m["role"] for m in c.messages] == ["user", "assistant"]
    assert "<summary>" in c.messages[0]["content"]
    c.send("c")
    roles = [m["role"] for m in c.messages]
    assert all(a != b for a, b in zip(roles, roles[1:]))
