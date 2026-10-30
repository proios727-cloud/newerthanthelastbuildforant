import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest

SKILL = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/product-pain-miner"
_spec = importlib.util.spec_from_file_location("pain_index", SKILL / "scripts/pain_index.py")
pain_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pain_index)

ENTRY = {
    "id": "a-thing", "item": "Thing", "complaint": "Breaks", "failure_mode": "wears-out-early",
    "frequency": 5, "severity": 5, "workaround": 5, "feasibility": 5,
    "redesign": "Make it not break", "sources": ["https://example.com/a"],
}


def dataset(*entries):
    return {"category": "test", "updated": "2026-10-30", "entries": list(entries) or [dict(ENTRY)]}


class PainIndexTests(unittest.TestCase):
    def test_valid_dataset_has_no_problems(self):
        self.assertEqual(pain_index.validate(dataset()), [])

    def test_scores_bounds(self):
        self.assertEqual(pain_index.score(ENTRY), (100, 100))
        low = dict(ENTRY, frequency=1, severity=1, workaround=1, feasibility=1)
        self.assertEqual(pain_index.score(low), (1, 0))

    def test_rejects_bad_fields(self):
        bad = dict(ENTRY, id="Bad Id", failure_mode="nope", frequency=6, severity=True, sources=["ftp://x"])
        problems = " ".join(pain_index.validate(dataset(bad)))
        for needle in ("kebab-case", "failure_mode", "'frequency'", "'severity'", "http(s)"):
            self.assertIn(needle, problems)

    def test_requires_sources_and_unique_ids(self):
        no_src = dict(ENTRY, sources=[])
        problems = pain_index.validate(dataset(dict(ENTRY), dict(ENTRY), no_src))
        self.assertTrue(any("duplicate id" in p for p in problems))
        self.assertTrue(any("source URL" in p for p in problems))

    def test_ranks_by_opportunity_then_pain(self):
        cheap = dict(ENTRY, id="cheap", severity=3)                 # pain 60, opp 60
        hard = dict(ENTRY, id="hard", feasibility=2)                # pain 100, opp 40
        tie = dict(ENTRY, id="tie", severity=3, workaround=5)       # same as cheap
        ids = [e["id"] for e, _, _ in pain_index.ranked(dataset(hard, tie, cheap))]
        self.assertEqual(ids, ["cheap", "tie", "hard"])

    def test_render_escapes_pipes_and_flags_single_source(self):
        e = dict(ENTRY, complaint="a | b")
        md = pain_index.render(dataset(e))
        self.assertIn("a \\| b", md)
        self.assertIn("Single-source entries", md)

    def test_cli_refuses_invalid_and_writes_valid(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = pathlib.Path(d, "x.json"), pathlib.Path(d, "x.md")
            bad = copy.deepcopy(dataset())
            bad["entries"][0]["sources"] = []
            src.write_text(json.dumps(bad))
            self.assertEqual(pain_index.main([str(src), "--out", str(out)]), 1)
            self.assertFalse(out.exists())
            src.write_text(json.dumps(dataset()))
            self.assertEqual(pain_index.main([str(src), "--out", str(out)]), 0)
            self.assertIn("Ranked opportunities", out.read_text())

    def test_shipped_datasets_are_valid_and_reports_current(self):
        for data_file in sorted((SKILL / "data").glob("*.json")):
            data = json.loads(data_file.read_text())
            self.assertEqual(pain_index.validate(data), [], data_file.name)
            report = SKILL / "reports" / f"{data_file.stem}.md"
            self.assertEqual(report.read_text(), pain_index.render(data), f"regenerate {report.name}")


if __name__ == "__main__":
    unittest.main()
