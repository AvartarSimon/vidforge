from __future__ import annotations

import unittest

from vidforge.research import analyze, youtube as yt


class Parsing(unittest.TestCase):
    def test_views_age_duration(self):
        self.assertEqual(yt.parse_views("1.2M views"), 1_200_000)
        self.assertEqual(yt.parse_views("438,824 views"), 438_824)
        self.assertEqual(yt.parse_views("3.5万次观看"), 35_000)
        self.assertEqual(yt.parse_age_days("2 years ago"), 730)
        self.assertEqual(yt.parse_age_days("3 weeks ago"), 21)
        self.assertIsNone(yt.parse_age_days(""))
        self.assertEqual(yt.parse_duration("1:02:05"), 3725)
        self.assertEqual(yt.parse_duration("11:34"), 694)
        self.assertEqual(yt.iso8601_duration("PT1H2M5S"), 3725)

    def test_summary_and_prompt(self):
        vids = [yt.Video("a", "The Year Without a Summer", "OER", 4_000_000, "", 120, 400),
                yt.Video("b", "Tambora explained", "Geo", 1_000_000, "", 1800, 1400),
                yt.Video("c", "Short one", "X", 50_000, "", 30, 200)]
        s = yt.summarize(vids)
        self.assertEqual((s["count"], s["median_views"], s["recent_12m"]), (3, 1_000_000, 2))
        self.assertAlmostEqual(s["long_form_share"], 0.33, places=2)
        p = analyze.build_prompt("year without a summer", vids, "英文历史解说", lang="zh")
        self.assertIn("4,000,000 views", p)
        self.assertIn('"verdict"', p)
        self.assertIn("英文历史解说", p)
        self.assertTrue(analyze.build_prompt("x", vids, lang="en").startswith("I run an explainer"))

    def test_parse_answer_extracts_json_or_falls_back(self):
        r = analyze.parse_answer('Sure! ```json\n{"verdict": "do_with_angle", "angles": [{"title": "A", "why": "B"}]}\n```')
        self.assertEqual(r["verdict"], "do_with_angle")
        self.assertEqual(r["angles"][0]["title"], "A")
        r2 = analyze.parse_answer("not json at all")
        self.assertTrue(r2["raw"])


if __name__ == "__main__":
    unittest.main()
