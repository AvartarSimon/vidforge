"""画面预设与录音棚的保存端点。"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from vidforge import ffmpeg, me, project as proj, ui, videofx


def clip(path: Path, seconds: float = 2.0, *, size: str = "320x180", audio: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=15:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=f=220:d={seconds}"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    ffmpeg.run(args + [str(path)])
    return path


class LookTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_every_look_is_listed(self):
        self.assertEqual({x["id"] for x in videofx.listing()}, {x.id for x in videofx.LOOKS})
        self.assertIn("none", {x.id for x in videofx.LOOKS})

    def test_none_is_empty_and_chains_are_comma_terminated(self):
        self.assertEqual(videofx.chain("none"), "")
        for lk in videofx.LOOKS:
            if lk.chain:
                self.assertTrue(videofx.chain(lk.id).endswith(","), lk.id)

    def test_unknown_look_names_the_options(self):
        with self.assertRaises(KeyError) as cm:
            videofx.get("glam")
        self.assertIn("beauty", str(cm.exception))

    def test_beauty_smooths_with_an_edge_preserving_filter_not_a_blur(self):
        # a plain gblur would take the eyes and hair with it; that is the whole difference
        self.assertIn("bilateral", videofx.get("beauty").chain)
        self.assertNotIn("gblur", videofx.get("beauty").chain)
        self.assertIn("unsharp", videofx.get("beauty").chain, "detail has to come back")

    def test_no_look_resizes_or_retimes(self):
        # a take must stay interchangeable with the one it replaces
        src = clip(self.td / "src.mp4", 2.0)
        want_d, want_s = ffmpeg.duration(src), ffmpeg.video_size(src)
        for lk in videofx.LOOKS:
            out = self.td / f"{lk.id}.mp4"
            args = ["-y", "-i", str(src)]
            if lk.chain:
                args += ["-vf", lk.chain]
            ffmpeg.run(args + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)])
            self.assertAlmostEqual(ffmpeg.duration(out), want_d, delta=0.2, msg=lk.id)
            self.assertEqual(ffmpeg.video_size(out), want_s, lk.id)

    def test_no_look_uses_a_filter_that_changes_length(self):
        for lk in videofx.LOOKS:
            for banned in ("setpts", "fps=", "trim", "tpad", "framerate"):
                self.assertNotIn(banned, lk.chain, f"{lk.id} must not use {banned}")

    def test_chromakey_chain_pulls_the_spill_back_out(self):
        chain = videofx.chromakey_chain("bg.png")
        self.assertIn("chromakey", chain)
        self.assertIn("despill", chain, "green bounces onto hair and shoulders")
        self.assertIn("overlay", chain)


class TakeLookFieldTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi",
                        "-i", "color=c=black:s=64x64", "-frames:v", "1",
                        str(self.td / "assets" / "a.png")], check=True)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def write(self, **extra):
        data = {"title": "T", "voice": "en-US-AndrewNeural",
                "segments": [{"id": "s1", "text": "Hi.", "clips": [{"image": "assets/a.png"}]}]}
        data.update(extra)
        (self.td / "project.json").write_text(json.dumps(data), encoding="utf-8")
        return proj.load(self.td / "project.json")

    def test_default_and_round_trip(self):
        self.assertEqual(self.write().take_look, "clean")
        self.assertEqual(self.write(take_look="beauty").take_look, "beauty")

    def test_a_typo_fails_at_load(self):
        with self.assertRaises(proj.ProjectError) as cm:
            self.write(take_look="pretty")
        self.assertIn("pretty", str(cm.exception))


class RecordSaveApi(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        self.take = clip(self.td / "take.mp4", 2.0)
        (self.td / "project.json").write_text(json.dumps({
            "title": "T", "language": "zh", "voice": "zh-CN-YunxiNeural",
            "segments": [{"id": "s1", "text": "你好，这是第一段。"},
                         {"id": "s2", "text": "第二段。"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.state = ui.State(self.td / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self._lib = me.GLOBAL_DIR
        me.GLOBAL_DIR = self.td / "me-library"

    def tearDown(self):
        me.GLOBAL_DIR = self._lib
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def payload(self, **extra):
        body = {"segment": "s1", "ext": "mp4",
                "data": base64.b64encode(self.take.read_bytes()).decode()}
        body.update(extra)
        return body

    def test_videofx_route_lists_looks_and_the_project_default(self):
        status, j = self.call("/api/videofx")
        self.assertEqual(status, 200)
        self.assertEqual({x["id"] for x in j["looks"]}, {x.id for x in videofx.LOOKS})
        self.assertEqual(j["current"], "clean")

    def test_a_take_becomes_the_segment_narration(self):
        status, j = self.call("/api/record/save", self.payload(as_narration=True))
        self.assertEqual(status, 200)
        self.assertAlmostEqual(j["seconds"], 2.0, delta=0.4)
        on_disk = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["segments"][0]["narration"], j["narration"])
        self.assertTrue((self.td / j["narration"]).is_file())
        self.assertNotIn("narration", on_disk["segments"][1])

    def test_one_take_can_be_narration_and_footage_at_once(self):
        status, j = self.call("/api/record/save",
                              self.payload(as_narration=True, as_footage=True, look="beauty"))
        self.assertEqual(status, 200)
        self.assertTrue(j["narration"])
        self.assertTrue(j["footage"].endswith(".mp4"))
        saved = me.GLOBAL_DIR / j["footage"]
        self.assertTrue(saved.is_file())
        self.assertAlmostEqual(ffmpeg.duration(saved), 2.0, delta=0.4)
        self.assertTrue(any(i["name"] == j["footage"] for i in j["items"]))

    def test_footage_only_leaves_the_script_alone(self):
        status, j = self.call("/api/record/save", self.payload(as_narration=False, as_footage=True))
        self.assertEqual(status, 200)
        self.assertNotIn("narration", j)
        on_disk = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
        self.assertNotIn("narration", on_disk["segments"][0])

    def test_the_chosen_look_is_remembered_for_next_time(self):
        self.call("/api/record/save",
                  self.payload(as_footage=True, look="bright", remember_look=True))
        on_disk = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["take_look"], "bright")
        _, j = self.call("/api/videofx")
        self.assertEqual(j["current"], "bright")

    def test_doing_nothing_with_a_take_is_refused(self):
        status, _ = self.call("/api/record/save",
                              self.payload(as_narration=False, as_footage=False))
        self.assertEqual(status, 400)

    def test_unknown_segment_and_broken_data_are_refused(self):
        self.assertEqual(self.call("/api/record/save", self.payload(segment="nope"))[0], 400)
        self.assertEqual(self.call("/api/record/save",
                                   self.payload(data="!!not base64!!"))[0], 400)
        self.assertEqual(self.call("/api/record/save", self.payload(data=""))[0], 400)

    def test_a_file_that_is_not_media_is_refused_and_not_left_behind(self):
        junk = base64.b64encode(b"this is not a video").decode()
        status, _ = self.call("/api/record/save", self.payload(data=junk))
        self.assertEqual(status, 400)
        folder = self.td / "assets" / "narration"
        self.assertFalse(list(folder.glob("*")) if folder.is_dir() else [],
                         "a broken take must not be left on disk")

    def test_an_unknown_look_is_refused(self):
        status, _ = self.call("/api/record/save", self.payload(as_footage=True, look="glam"))
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
