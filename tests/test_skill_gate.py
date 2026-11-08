import importlib.util
import json
import os
import tempfile
import unittest

_PATH = os.path.join(os.path.dirname(__file__), "..", "skills", "skill-gate", "scripts", "skill_gate.py")
_spec = importlib.util.spec_from_file_location("skill_gate", _PATH)
sg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sg)


def issue(rid, severity, file, line=1, surface="code", finding="x"):
    return {"id": rid, "pattern": "p", "severity": severity, "confidence": 0.9,
            "location": {"file": file, "start_line": line}, "surface": surface,
            "finding": finding, "code_snippet": "snip", "remediation": "fix"}


def report(*issues, complete=True):
    return {"issues": list(issues), "execution_successful": True,
            "risk_assessment": {"score": 100, "severity": "CRITICAL", "recommendation": "DO_NOT_INSTALL"},
            "analysis_completeness": {"is_complete": complete, "coverage_percent": 100 if complete else 80}}


class Classify(unittest.TestCase):
    def test_tests_benchmarks_docs_are_dev(self):
        for p in ["tests/hooks.test.js", "benchmarks/judge.py", "docs/cursor-hooks.md",
                  "README.md", "examples/demo/run.sh", "pkg/test_thing.py", ".github/workflows/ci.yml"]:
            self.assertEqual(sg.classify(p), sg.DEV, p)

    def test_hooks_and_runtime_are_code(self):
        for p in ["hooks/ponytail-activate.js", "agent_reach/runtime/browser.py",
                  ".claude-plugin/plugin.json", "scripts/setup.sh"]:
            self.assertEqual(sg.classify(p), sg.CODE, p)

    def test_agent_instruction_files(self):
        for p in ["SKILL.md", "skills/foo/SKILL.md", "agents/reviewer.md",
                  "skills/foo/references/guide.md", "CLAUDE.md"]:
            self.assertEqual(sg.classify(p), sg.INSTR, p)

    def test_skill_md_inside_docs_is_an_example(self):
        self.assertEqual(sg.classify("docs/examples/SKILL.md"), sg.DEV)

    def test_scanner_tests_surface_wins(self):
        self.assertEqual(sg.classify("lib/check.js", "tests"), sg.DEV)


class Verdicts(unittest.TestCase):
    def test_noise_only_is_clean(self):
        t = sg.triage(report(issue("TT3", "CRITICAL", "benchmarks/judge.py"),
                             issue("P1", "HIGH", "tests/hooks.test.js", surface="tests")), "n")
        self.assertEqual(t["verdict"], "CLEAN")
        self.assertEqual(t["dev_only_serious"], 2)
        self.assertEqual(t["to_review"], [])

    def test_high_in_runtime_code_is_review(self):
        t = sg.triage(report(issue("PE3", "HIGH", "hooks/a.js")), "n")
        self.assertEqual(t["verdict"], "REVIEW")
        self.assertEqual(len(t["to_review"]), 1)

    def test_medium_in_code_does_not_trigger_review(self):
        self.assertEqual(sg.triage(report(issue("E1", "MEDIUM", "hooks/a.js")))["verdict"], "CLEAN")

    def test_override_wording_in_skill_md_blocks(self):
        t = sg.triage(report(issue("P1", "HIGH", "SKILL.md", surface="docs")), "n")
        self.assertEqual(t["verdict"], "BLOCK")
        self.assertEqual(len(t["hard_signals"]), 1)

    def test_same_wording_in_tests_does_not_block(self):
        self.assertEqual(sg.triage(report(issue("P1", "HIGH", "tests/x.js", surface="tests")))["verdict"], "CLEAN")

    def test_partial_scan_is_noted(self):
        t = sg.triage(report(complete=False), "n")
        self.assertTrue(any("partial" in n.lower() for n in t["notes"]))

    def test_empty_report(self):
        self.assertEqual(sg.triage({}, "n")["verdict"], "CLEAN")


class Output(unittest.TestCase):
    def test_group_collapses_repeats(self):
        rows = sg.triage(report(*[issue("PE3", "HIGH", "hooks/a.js", i) for i in range(1, 21)]))["to_review"]
        g = sg.group(rows)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["count"], 20)

    def test_html_escapes_hostile_text(self):
        evil = '<script>alert(1)</script>'
        t = sg.triage(report(issue("PE3", "HIGH", "hooks/a.js", finding=evil)), "<b>n</b>")
        page = sg.to_html(t)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("<b>n</b>", page)

    def test_write_outputs_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            rp = os.path.join(d, "r.json")
            with open(rp, "w") as f:
                json.dump(report(issue("PE3", "HIGH", "hooks/a.js")), f)
            self.assertEqual(sg.main(["triage", rp, "--out", os.path.join(d, "o")]), 1)
            for fn in ("verdict.json", "report.md", "report.html"):
                self.assertTrue(os.path.exists(os.path.join(d, "o", fn)))
            with open(rp, "w") as f:
                json.dump(report(), f)
            self.assertEqual(sg.main(["triage", rp, "--out", os.path.join(d, "o2")]), 0)


if __name__ == "__main__":
    unittest.main()
