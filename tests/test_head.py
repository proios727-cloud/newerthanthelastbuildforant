import json
import re
import unittest

from scripts import build_head


class HeadPageTests(unittest.TestCase):
    def test_snapshot_covers_every_book_and_embeds(self):
        s = build_head.snapshot()
        for key in ("real", "shadow", "putbook", "spreadbook", "jevcheck", "activity", "rules"):
            self.assertIn(key, s)
        self.assertTrue(all(isinstance(v["open"], int) for v in s["shadow"].values()))

    def test_page_has_no_placeholders_and_guard_rules(self):
        html = (build_head.ROOT / "assets" / "head-template.html").read_text(encoding="utf-8")
        html = html.replace("/*SNAPSHOT*/null", json.dumps({"x": "</script>"}).replace("</", "<\\/"))
        self.assertNotIn("</script>\"", html)
        self.assertTrue(any("place" in g and "exercise" in g for g in build_head.CONFIG["guard"]))
        self.assertTrue(any("EXECUTE" in g for g in build_head.CONFIG["guard"]))
        self.assertRegex(html, re.escape('"create_session"'))


if __name__ == "__main__":
    unittest.main()
