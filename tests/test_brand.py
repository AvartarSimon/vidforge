"""Brand kit: config layering, the SVG marks, contrast, and where the clips go in the timeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import brand


def _ff() -> bool:
    from vidforge import ffmpeg
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


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
        project = mock.Mock(raw=raw, width=1920, height=1080, fps=30, theme={})
        return mock.Mock(project=project)

    def setUp(self):
        # matching the cards to the segments' stream format is an encode; these tests are about order
        from vidforge import render
        patcher = mock.patch.object(render, "match_clip", side_effect=lambda clip, like, p, enc, out: clip)
        patcher.start()
        self.addCleanup(patcher.stop)

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


class ProjectPalette(unittest.TestCase):
    def test_the_opener_takes_the_videos_palette_when_it_has_one(self):
        from vidforge import theme
        kit = brand.Brand(name="刻度")
        self.assertEqual(brand.for_project(kit, None).bg, kit.bg, "no palette: the channel's own colours")
        mint = brand.for_project(kit, {"palette": "mint"})
        self.assertEqual(mint.bg, theme.get("mint").page)
        self.assertEqual(mint.name, "刻度")


class Api(unittest.TestCase):
    """片头片尾与音乐 from the UI. The kit file is redirected: a test must not rewrite the user's."""

    def setUp(self):
        import json
        import shutil
        import tempfile
        import threading
        from http.server import ThreadingHTTPServer
        from pathlib import Path
        from vidforge import ui
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        for target, attr, value in ((brand, "BRAND_DIR", self.td / "brand"), (brand, "BRAND_FILE", self.td / "brand" / "brand.json"),
                                    (ui, "RECENT", self.td / "recent.json")):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.td / "p").mkdir()
        (self.td / "p" / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.state = ui.State(self.td / "p" / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def call(self, path, body=None):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def raw(self):
        import json
        return json.loads(self.state.project_path.read_text(encoding="utf-8"))

    def test_the_kit_is_saved_once_for_every_video(self):
        code, j = self.call("/api/brand", {"kit": {"name": "刻度", "slogan": "把热点放进时间里", "outro_seconds": "7", "intro": False, "evil": 1}})
        self.assertEqual(code, 200, j)
        self.assertEqual((j["kit"]["name"], j["kit"]["outro_seconds"], j["kit"]["intro"]), ("刻度", 7.0, False))
        self.assertNotIn("evil", j["kit"])
        self.assertTrue((self.td / "brand" / "brand.json").is_file())
        self.assertEqual(self.call("/api/brand")[1]["kit"]["slogan"], "把热点放进时间里")

    def test_a_video_can_leave_out_the_opener_and_go_back(self):
        self.call("/api/brand/project", {"intro": False, "outro": False})
        self.assertEqual(self.raw()["brand"], {"intro": False, "outro": False})
        self.call("/api/brand/project", {"outro": False})
        self.assertEqual(self.raw()["brand"], {"outro": False}, "the opener is back to the channel's own")
        self.call("/api/brand/project", {})
        self.assertNotIn("brand", self.raw())

    @unittest.skipUnless(_ff(), "ffmpeg not installed")
    def test_sounds_are_made_or_uploaded_and_bad_ones_refused(self):
        import base64
        import subprocess
        from vidforge import ffmpeg
        j = self.call("/api/brand/sting", {"style": "two"})[1]
        self.assertTrue(j["has"]["sting"])
        self.assertEqual(self.call("/api/brand/sting", {"style": "nope"})[0], 400)
        self.assertFalse(self.call("/api/brand/sting", {"style": "none"})[1]["has"]["sting"])
        song = self.td / "song.m4a"
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=2", str(song)], check=True)
        b64 = base64.b64encode(song.read_bytes()).decode()
        code, j = self.call("/api/audio/upload", {"kind": "bgm", "name": "我的 歌.m4a", "data_b64": b64})
        self.assertEqual(code, 200, j)
        self.assertEqual(self.raw()["bgm"]["file"], "assets/music/我的_歌.m4a")
        self.assertEqual(self.raw()["bgm"]["volume_db"], -18)
        j = self.call("/api/audio/upload", {"kind": "outro_music", "name": "end.m4a", "data_b64": b64})[1]
        self.assertTrue(j["has"]["outro_music"])
        self.assertEqual(self.call("/api/audio/upload", {"kind": "bgm", "name": "x.mp3", "data_b64": base64.b64encode(b"not audio").decode()})[0], 400)
        self.assertFalse((self.state.root / "assets" / "music" / "x.mp3").exists(), "a refused file is not kept")
        self.assertEqual(self.call("/api/audio/upload", {"kind": "logo", "name": "x.png", "data_b64": b64})[0], 400)

    def test_a_preview_needs_a_name_first(self):
        code, j = self.call("/api/brand/preview", {})
        self.assertEqual(code, 400)
        self.assertIn("频道名", j["error"])


if __name__ == "__main__":
    unittest.main()
