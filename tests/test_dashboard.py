import sys
import unittest

sys.path.insert(0, "scripts")
import build_dashboard  # noqa: E402


class DashboardTests(unittest.TestCase):
    def test_renders_all_four_desks(self):
        page = build_dashboard.render()
        self.assertTrue(page.startswith("<title>Desk Control Room</title>"))
        for heading in ("Fund · equities", "Options · SPY", "Kalshi · 15-min", "Sportsbook · line"):
            self.assertIn(heading, page)
        self.assertIn("<svg", page)
        self.assertNotIn("None", page)


if __name__ == "__main__":
    unittest.main()
