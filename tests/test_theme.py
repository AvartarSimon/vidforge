"""竖屏主题模板: the layout lands in project.json, the badge lands on the video."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, project as proj, render, theme


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Apply(unittest.TestCase):
    def test_vertical_frame_subtitles_and_presenter_window(self):
        raw = {"title": "t", "segments": [
            {"id": "a", "text": "x", "clips": [], "overlays": [{"video": "assets/takes/a_1.mp4"}, {"image": "assets/pic.jpg"}]}]}
        theme.apply(raw, "mint", badge="RESTART · 001")
        self.assertEqual((raw["width"], raw["height"]), (1080, 1920))
        self.assertEqual(raw["subtitles"]["box_colour"], theme.get("mint").box)
        from vidforge.subtitles import SCRIPT_LINES
        self.assertGreater(raw["subtitles"]["margin_v"] / SCRIPT_LINES, 0.2, "clear of the platform's bottom area")
        self.assertTrue(0.03 <= raw["subtitles"]["font_size"] / SCRIPT_LINES <= 0.04, "a phone-sized line, not a headline")
        take, pic = raw["segments"][0]["overlays"]
        self.assertEqual(take["shape"], "rounded")
        self.assertTrue(0.22 <= take["size"] <= 0.26)
        self.assertAlmostEqual(take["size"] * 1080 / (take["height"] * 1920), 3 / 4, delta=0.01)
        self.assertNotIn("shape", pic, "an ordinary picture overlay is left alone")

    def test_a_subtitle_line_is_a_phone_width_of_chinese_not_half_of_one(self):
        # max_chars is counted in Latin characters and halved for Chinese; the template once set
        # 14 meaning fourteen glyphs and got seven, two or three words per cue
        from vidforge.subtitles import build_cues
        from vidforge.tts import Word
        raw = {"title": "t", "segments": []}
        theme.apply(raw, "mint")
        words = [Word(ch, i * 0.2, 0.2) for i, ch in enumerate("睡眠超过九小时的人白天反而更容易感到疲劳")]
        longest = max(len(c.text) for c in build_cues(words, offset=0, max_chars=raw["subtitles"]["max_chars"]))
        self.assertTrue(9 <= longest <= 12, longest)

    def test_a_project_themed_on_the_first_day_keeps_its_subtitle_size(self):
        # the template stored pixels for one day; read as script units they would fill the screen
        td = Path(tempfile.mkdtemp())
        try:
            (td / "a.jpg").write_bytes(b"x")
            raw = {"title": "t", "width": 1080, "height": 1920, "theme": {"palette": "mint"},
                   "subtitles": {"burn": True, "font_size": 65, "margin_v": 461},
                   "segments": [{"id": "a", "text": "x", "image": "a.jpg"}]}
            import json
            (td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
            sub = proj.load(td / "project.json").subtitles
            fresh = theme.apply({"title": "t", "segments": []}, "mint")["subtitles"]
            self.assertEqual((sub.font_size, sub.margin_v), (fresh["font_size"], fresh["margin_v"]))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_window_sits_upper_left_inside_the_margin(self):
        fx, fy = (float(v) for v in theme.window_position("left").split(","))
        self.assertAlmostEqual((1080 - 1080 * theme.WINDOW_W) * fx, 1080 * theme.MARGIN_X, delta=1)
        self.assertLess(fy, 0.15)

    def test_unknown_palette_falls_back_to_a_bright_one(self):
        self.assertEqual(theme.get("nope").id, theme.PALETTES[0].id)

    def test_every_palette_is_bright(self):
        # the brief: 颜色明亮、鲜一点 — no box darker than mid-grey
        for p in theme.PALETTES:
            h = p.box.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.assertGreater(0.299 * r + 0.587 * g + 0.114 * b, 100, p.id)

    def test_charts_take_the_template_colours_and_stay_readable(self):
        # a chart kept its own near-black backdrop inside a bright video
        from vidforge import pipeline
        from vidforge.project import RemotionSpec
        self.assertIsNone(theme.graphics_theme({}), "no template: the compositions keep their own look")
        for p in theme.PALETTES:
            g = theme.graphics_theme({"palette": p.id})
            self.assertEqual(g["bg"], p.page)
            self.assertGreater(theme._luma(g["bg"]) - theme._luma(g["accent"]), 40, f"{p.id}: accent readable on the page")
        project = proj.Project(title="t", segments=[], root=Path("."), theme={"palette": "mint"})
        self.assertEqual(pipeline._graphics_props(project, RemotionSpec("BigNumber", {"value": "1"}))["theme"]["bg"], theme.get("mint").page)
        own = RemotionSpec("BigNumber", {"value": "1", "theme": {"bg": "#000"}})
        self.assertEqual(pipeline._graphics_props(project, own)["theme"], {"bg": "#000"}, "a segment's own choice wins")

    def test_a_landscape_chart_is_told_where_the_burned_subtitle_line_is(self):
        # readable subtitles sat across the chart's axis; a chart with no subtitles keeps the frame
        from vidforge import pipeline
        from vidforge.project import RemotionSpec, SubtitleStyle
        spec = RemotionSpec("LineChart", {"lines": []})
        wide = proj.Project(title="t", segments=[], root=Path("."), subtitles=SubtitleStyle(burn=True))
        self.assertTrue(0.2 < pipeline._graphics_props(wide, spec)["clearBottom"] < 0.35)
        wide.subtitles.burn = False
        self.assertNotIn("clearBottom", pipeline._graphics_props(wide, spec))
        tall = proj.Project(title="t", segments=[], root=Path("."), width=1080, height=1920, subtitles=SubtitleStyle(burn=True))
        self.assertNotIn("clearBottom", pipeline._graphics_props(tall, spec))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Badge(unittest.TestCase):
    def test_badge_is_drawn_over_the_final_video(self):
        td = Path(tempfile.mkdtemp())
        try:
            merged = td / "merged.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=gray:s=540x960:r=30:d=2", "-f", "lavfi", "-i", "sine=d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(merged)])
            p = proj.Project(title="t", segments=[], root=td, width=540, height=960, quality="draft", encoder="libx264",
                             theme={"palette": "sunny", "badge": "RESTART · 001", "side": "left"})
            out = td / "final.mp4"
            render.finalize(p, merged, None, 2.0, out)
            self.assertAlmostEqual(ffmpeg.duration(out), 2.0, delta=0.15)
            frame = td / "f.png"
            ffmpeg.run(["-y", "-ss", "1", "-i", str(out), "-frames:v", "1", str(frame)])
            from PIL import Image
            im = Image.open(frame).convert("RGB")
            with Image.open(td / "badge.png") as badge:
                bw, bh = badge.size
            x, y = theme.badge_position("left", 540, 960, bw)
            r, g, b = im.getpixel((x + 4, y + bh // 2))
            self.assertGreater(r, 200, "white pill of the sunny badge")
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
