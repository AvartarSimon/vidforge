"""Brand kit: config layering, the SVG marks, contrast, and where the clips go in the timeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import brand


class Config(unittest.TestCase):
    def test_a_project_overrides_the_global_kit_field_by_field(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "brand.json"
            f.write_text(json.dumps({"name": "刻度", "accent": "#d4793a", "slogan": "把热点放进时间里"}),
                         encoding="utf-8")
            with mock.patch.object(brand, "BRAND_FILE", f):
                kit = brand.load({"brand": {"accent": "#2a9d8f"}})
        self.assertEqual(kit.name, "刻度")              # kept from the global kit
        self.assertEqual(kit.accent, "#2a9d8f")         # overridden by the project
        self.assertEqual(kit.slogan, "把热点放进时间里")

    def test_unknown_keys_in_the_file_do_not_crash_the_load(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "brand.json"
            f.write_text(json.dumps({"name": "x", "from_an_older_version": 1}), encoding="utf-8")
            with mock.patch.object(brand, "BRAND_FILE", f):
                self.assertEqual(brand.load().name, "x")

    def test_a_corrupt_file_falls_back_to_defaults_rather_than_failing(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "brand.json"
            f.write_text("{not json", encoding="utf-8")
            with mock.patch.object(brand, "BRAND_FILE", f):
                self.assertEqual(brand.load().name, "")

    def test_the_theme_is_what_the_charts_receive(self):
        kit = brand.Brand(bg="#000000", accent="#ff0000")
        self.assertEqual(kit.theme()["bg"], "#000000")
        self.assertEqual(kit.theme()["accent"], "#ff0000")


class Marks(unittest.TestCase):
    def test_each_mark_is_valid_standalone_svg_in_the_brand_colours(self):
        kit = brand.Brand(name="刻度", accent="#d4793a")
        for mark in ("ticks", "line", "axis"):
            svg = brand.logo_svg(kit, mark)
            self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"), mark)
            self.assertIn("#d4793a", svg, mark)
            self.assertIn('viewBox="0 0 512 512"', svg, mark)

    def test_an_unknown_mark_says_which_ones_exist(self):
        with self.assertRaises(brand.BrandError) as cm:
            brand.logo_svg(brand.Brand(), "spiral")
        self.assertIn("ticks", str(cm.exception))

    def test_write_logos_produces_all_three_for_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            files = brand.write_logos(brand.Brand(name="刻度"), Path(td))
        self.assertEqual([f.stem for f in files], ["logo-ticks", "logo-line", "logo-axis"])


class Contrast(unittest.TestCase):
    def test_dark_card_with_light_text_passes(self):
        self.assertTrue(brand.contrast_ok("#0d1117", "#f3f4f6"))

    def test_grey_on_grey_is_rejected(self):
        self.assertFalse(brand.contrast_ok("#808080", "#8b949e"))

    def test_three_digit_hex_is_understood(self):
        self.assertTrue(brand.contrast_ok("#000", "#fff"))


class Timeline(unittest.TestCase):
    """Where the brand clips land, without rendering anything."""

    def _ctx(self, raw):
        project = mock.Mock(raw=raw, width=1920, height=1080, fps=30)
        return mock.Mock(project=project)

    def test_opener_goes_first_and_the_end_card_last(self):
        from vidforge import pipeline
        with tempfile.TemporaryDirectory() as td:
            bd = Path(td)
            kit = brand.Brand(name="刻度", intro=True, outro=True)
            with mock.patch.object(brand, "load", return_value=kit), \
                    mock.patch.object(brand, "render_opener", return_value=bd / "i.mp4"), \
                    mock.patch.object(brand, "render_endcard", return_value=bd / "o.mp4"), \
                    mock.patch.object(brand, "with_audio", side_effect=lambda c, a, o, s: o):
                with mock.patch("vidforge.ffmpeg.duration", return_value=1.2):
                    out, lead, trail = pipeline._with_brand(self._ctx({}), bd, [Path("a.mp4"), Path("b.mp4")])
        self.assertEqual([p.name for p in out], ["intro.mp4", "a.mp4", "b.mp4", "outro.mp4"])
        self.assertEqual((lead, trail), (1.2, 1.2))

    def test_a_kit_without_a_name_leaves_the_timeline_alone(self):
        from vidforge import pipeline
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(brand, "load", return_value=brand.Brand(name="")):
                out, lead, trail = pipeline._with_brand(self._ctx({}), Path(td), [Path("a.mp4")])
        self.assertEqual((out, lead, trail), ([Path("a.mp4")], 0.0, 0.0))

    def test_a_render_failure_never_sinks_the_build(self):
        from vidforge import pipeline
        with tempfile.TemporaryDirectory() as td:
            kit = brand.Brand(name="刻度")
            with mock.patch.object(brand, "load", return_value=kit), \
                    mock.patch.object(brand, "render_opener", side_effect=RuntimeError("no node")):
                out, lead, trail = pipeline._with_brand(self._ctx({}), Path(td), [Path("a.mp4")])
        self.assertEqual((out, lead, trail), ([Path("a.mp4")], 0.0, 0.0))

    def test_intro_can_be_turned_off_for_a_cold_open(self):
        from vidforge import pipeline
        with tempfile.TemporaryDirectory() as td:
            bd = Path(td)
            kit = brand.Brand(name="刻度", intro=False, outro=True)
            with mock.patch.object(brand, "load", return_value=kit), \
                    mock.patch.object(brand, "render_endcard", return_value=bd / "o.mp4"), \
                    mock.patch.object(brand, "with_audio", side_effect=lambda c, a, o, s: o):
                with mock.patch("vidforge.ffmpeg.duration", return_value=6.0):
                    out, lead, trail = pipeline._with_brand(self._ctx({}), bd, [Path("a.mp4")])
        self.assertEqual([p.name for p in out], ["a.mp4", "outro.mp4"])
        self.assertEqual((lead, trail), (0.0, 6.0))


class Sting(unittest.TestCase):
    def test_an_unknown_style_lists_the_real_ones(self):
        with self.assertRaises(brand.BrandError) as cm:
            brand.sting(Path("x.m4a"), style="fanfare")
        self.assertIn("rise", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
