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
        theme.apply(raw, "mint", badge="RESTART · 001", frame="9:16")
        self.assertEqual((raw["width"], raw["height"]), (1080, 1920))
        self.assertEqual(raw["subtitles"]["box_colour"], theme.get("mint").box)
        self.assertEqual(raw["subtitles"]["highlight"], "word")
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
        theme.apply(raw, "mint", frame="9:16")
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
            fresh = theme.apply({"title": "t", "segments": []}, "mint", frame="9:16")["subtitles"]
            self.assertEqual((sub.font_size, sub.margin_v), (fresh["font_size"], fresh["margin_v"]))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_a_wide_project_keeps_its_frame_and_takes_the_colours(self):
        raw = {"title": "t", "segments": []}
        theme.apply(raw, "sky")
        self.assertNotIn("width", raw, "no frame asked for: the project's own (1920x1080) stays")
        sub = raw["subtitles"]
        self.assertEqual((sub["box_colour"], sub["font_size"], sub["margin_v"]), (theme.get("sky").box, 22, 48))
        theme.apply(raw, "sky", frame="3:4")
        self.assertEqual((raw["width"], raw["height"]), (1080, 1440))
        self.assertGreater(raw["subtitles"]["margin_v"], 48, "upright: lifted over the caption area")
        with self.assertRaises(KeyError):
            theme.apply(raw, "sky", frame="21:9")

    def test_the_window_keeps_its_shape_in_every_frame(self):
        # a 3:4 box sized for 9:16 came out as a 461x194 strip in a 1920x1080 project
        for (w, h) in theme.FRAMES.values():
            for shape, want in (("circle", 1.0), ("rounded", 4 / 3 if h > w else 3 / 4)):
                size, box_h = theme.window_box(w, h, shape)
                self.assertAlmostEqual(box_h * h / (size * w), want, delta=0.01, msg=f"{w}x{h} {shape}")

    def test_every_corner_is_inside_the_frame_and_clear_of_the_subtitles(self):
        for (w, h) in theme.FRAMES.values():
            raw = {"width": w, "height": h, "subtitles": {"burn": True, "font_size": 22, "margin_v": 48}}
            for corner in theme.CORNERS:
                o = theme.presenter_overlay("assets/takes/a.mp4", raw, corner=corner)
                fx, fy = (float(v) for v in o["position"].split(","))
                self.assertTrue(0 <= fx <= 1 and 0 <= fy <= 1, (w, h, corner))
                top = fy * (h - o["height"] * h)
                bottom = top + o["height"] * h
                if corner.startswith("bottom"):
                    from vidforge.subtitles import band
                    self.assertLess(bottom, h * (1 - band(22, 48)), (w, h, corner))
                self.assertEqual(o["corner"], corner)

    def test_a_window_put_in_the_badges_corner_starts_under_it(self):
        raw = {"width": 1920, "height": 1080, "theme": {"palette": "mint", "badge": "S01", "side": "left"}}
        mine = theme.presenter_overlay("v.mp4", raw, corner="top-right")
        free = theme.presenter_overlay("v.mp4", raw, corner="top-left")
        top = lambda o: float(o["position"].split(",")[1]) * (1080 - o["height"] * 1080)   # noqa: E731
        x, y = theme.badge_position("left", 1920, 1080, 200)
        from PIL import Image
        with Image.open(theme.badge_png("S01", "mint", Path(tempfile.mkdtemp()) / "b.png", height=1080)) as im:
            bh = im.height
        self.assertGreater(top(mine), y + bh, "under the badge, not on it")
        self.assertLess(top(free), top(mine))

    def test_a_wide_circle_does_not_eat_half_the_height(self):
        size, h = theme.window_box(1920, 1080, "circle")
        self.assertLess(h, 0.3)

    def test_the_window_goes_opposite_the_badge(self):
        raw = {"width": 1920, "height": 1080, "theme": {"palette": "mint", "badge": "S01", "side": "left"}}
        self.assertEqual(theme.presenter_overlay("v.mp4", raw)["corner"], "top-left")
        raw["theme"]["side"] = "right"
        self.assertEqual(theme.presenter_overlay("v.mp4", raw)["corner"], "top-right")
        self.assertEqual(theme.presenter_overlay("v.mp4", {"width": 1920, "height": 1080})["corner"], "top-right")

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

    def test_a_window_in_a_bottom_corner_sends_the_source_caption_to_the_other_side(self):
        # a round window sat right on 「数据来源：世界银行」, which must stay on screen
        from vidforge import pipeline
        from vidforge.project import Overlay, RemotionSpec, Segment
        spec = RemotionSpec("BigNumber", {"value": "1"})
        p = proj.Project(title="t", segments=[], root=Path("."), width=1080, height=1920)
        seg = Segment(id="s", text="x", overlays=[Overlay(video=Path("t.mp4"), size=0.24, position="0.94,0.62")])
        self.assertEqual(pipeline._graphics_props(p, spec, seg)["captionSide"], "left")
        seg.overlays[0].position = "0.06,0.62"
        self.assertEqual(pipeline._graphics_props(p, spec, seg)["captionSide"], "right")
        seg.overlays[0].position = "0.06,0.05"
        self.assertNotIn("captionSide", pipeline._graphics_props(p, spec, seg), "a top window is out of the caption's way")
        seg.overlays = [Overlay(video=Path("t.mp4"), size=1, height=0.5, position="0,1")]
        self.assertNotIn("captionSide", pipeline._graphics_props(p, spec, seg), "a split screen is not a corner window")

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


class Api(unittest.TestCase):
    """画幅与风格 from the UI: the frame, the palette, and a new project made in a given frame."""

    def setUp(self):
        import json
        import threading
        from http.server import ThreadingHTTPServer
        from unittest import mock
        from vidforge import ui
        self.td = Path(tempfile.mkdtemp())
        # opening a project adds it to the recent list in ~/.vidforge: the test's own, not the user's
        self.recent = mock.patch.object(ui, "RECENT", self.td / "recent.json")
        self.recent.start()
        self.addCleanup(self.recent.stop)
        (self.td / "p").mkdir()
        (self.td / "p" / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.state = ui.State(self.td / "p" / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path, body=None):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def raw(self):
        import json
        return json.loads(self.state.project_path.read_text(encoding="utf-8"))

    def test_frame_and_palette_together_or_the_frame_alone(self):
        self.assertEqual(self.call("/api/theme")[1]["frame"], "16:9")
        self.assertEqual(self.call("/api/theme/apply", {"frame": "9:16", "palette": "mint"})[0], 200)
        self.assertEqual((self.raw()["width"], self.raw()["height"]), (1080, 1920))
        self.assertEqual(self.call("/api/theme")[1]["frame"], "9:16")
        self.assertEqual(self.call("/api/theme/apply", {"off": True, "frame": "1:1"})[0], 200)
        raw = self.raw()
        self.assertNotIn("theme", raw)
        self.assertEqual((raw["width"], raw["height"]), (1080, 1080))
        code, j = self.call("/api/theme/apply", {"frame": "21:9", "palette": "mint"})
        self.assertEqual(code, 400)
        self.assertIn("21:9", j["error"])

    def test_the_next_episode_keeps_the_look_and_counts_the_badge_on(self):
        import json
        (self.td / "p" / "assets" / "music").mkdir(parents=True)
        (self.td / "p" / "assets" / "music" / "pad.m4a").write_bytes(b"x")
        raw = {"title": "第一期", "language": "zh", "voice": "zh-CN-YunxiNeural", "width": 1080, "height": 1920,
               "theme": {"palette": "mint", "badge": "人口 · 009", "side": "left"}, "transition_sfx": "whoosh",
               "bgm": {"file": "assets/music/pad.m4a", "volume_db": -20}, "hook": {"text": "旧的钩子"},
               "youtube": {"title": "旧标题"}, "segments": [{"id": "a", "text": "旧脚本", "image": "x.jpg"}]}
        self.state.project_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        code, j = self.call("/api/new", {"name": "ep10", "title": "第十期", "next_episode": True, "dir": str(self.td)})
        self.assertEqual(code, 200, j)
        made = json.loads((self.td / "ep10" / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(made["theme"]["badge"], "人口 · 010")
        self.assertEqual((made["title"], made["segments"]), ("第十期", []))
        self.assertEqual((made["width"], made["height"], made["transition_sfx"], made["voice"]), (1080, 1920, "whoosh", "zh-CN-YunxiNeural"))
        self.assertNotIn("hook", made)
        self.assertNotIn("youtube", made)
        self.assertTrue((self.td / "ep10" / "assets" / "music" / "pad.m4a").is_file(), "the music came along")

    def test_a_project_in_the_temp_folder_stays_off_the_recent_list(self):
        from vidforge import ui
        ui.remember_project(self.td / "p")
        self.assertFalse((self.td / "recent.json").exists())

    def test_a_new_project_starts_in_the_frame_it_was_made_for(self):
        code, j = self.call("/api/new", {"name": "xhs", "title": "t", "language": "zh", "frame": "3:4", "dir": str(self.td)})
        self.assertEqual(code, 200, j)
        import json
        made = json.loads((self.td / "xhs" / "project.json").read_text(encoding="utf-8"))
        self.assertEqual((made["width"], made["height"]), (1080, 1440))
        code, _ = self.call("/api/new", {"name": "bad", "frame": "5:4", "dir": str(self.td)})
        self.assertEqual(code, 400)
        self.assertFalse((self.td / "bad").exists(), "nothing left behind for a refused frame")


class BadgeSpan(unittest.TestCase):
    def test_the_badge_stays_off_the_opener_and_the_end_card(self):
        from unittest import mock
        calls = []
        td = Path(tempfile.mkdtemp())
        try:
            p = proj.Project(title="t", segments=[], root=td, width=540, height=960, quality="draft", encoder="libx264",
                             theme={"palette": "mint", "badge": "S01"})
            with mock.patch.object(render.ffmpeg, "run", side_effect=calls.append), mock.patch.object(render, "replace_with_retry"):
                render.finalize(p, td / "merged.mp4", None, 20.0, td / "final.mp4", hook_at=1.2, content_end=14.0)
                render.finalize(p, td / "merged.mp4", None, 20.0, td / "final.mp4")
        finally:
            shutil.rmtree(td, ignore_errors=True)
        graph = lambda a: a[a.index("-filter_complex") + 1]   # noqa: E731
        self.assertIn("enable='between(t,1.200,14.000)'", graph(calls[0]))
        self.assertNotIn("enable=", graph(calls[1]), "no brand clips: the badge runs the whole video")


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
