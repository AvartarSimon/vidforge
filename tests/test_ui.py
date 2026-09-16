"""Web UI API against a real ThreadingHTTPServer on a temp copy of a tiny project.
TTS is stubbed (no network); the build endpoint is exercised with a patched pipeline.build."""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import pipeline, ui
from vidforge.tts import Word


class UiApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp()
        root = Path(cls.td)
        (root / "assets").mkdir()
        (root / "assets" / "a.jpg").write_bytes(b"\xff\xd8\xff")
        (root / "project.json").write_text(json.dumps({
            "title": "T", "voice": "en-US-AndrewNeural",
            "variants": {"zh": {"voice": "zh-CN-YunxiNeural"}},
            "segments": [
                {"id": "s1", "text": "Hello.", "text_zh": "你好。", "image": "assets/a.jpg"},
                {"id": "s2", "text": "Card.", "remotion": {"composition": "TitleCard", "props": {"title": "X"}}},
            ]}, ensure_ascii=False), encoding="utf-8")
        cls.state = ui.State(root / "project.json")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(cls.state))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.td, ignore_errors=True)

    def call(self, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_index_and_static(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            self.assertIn(b"vidforge", r.read())

    def test_project_view_base_and_variant(self):
        st, j = self.call("/api/project")
        self.assertEqual(st, 200)
        self.assertEqual(j["langs"], ["en", "zh"])
        self.assertEqual(j["resolved"]["s1"]["image"], "assets/a.jpg")
        self.assertEqual(j["resolved"]["s2"]["remotion"], "TitleCard")
        self.assertIsNone(j["resolved"]["s1"]["audio"])
        st, j = self.call("/api/project?lang=zh")
        self.assertIn("s2", j["issues"], "s2 has no text_zh -> reported, but the view still works")
        self.assertEqual(j["resolved"]["s1"]["image"], "assets/a.jpg", "visuals resolved via base language")
        self.assertEqual(j["build_dir"], "build_zh")

    def test_save_rejects_invalid_and_keeps_file(self):
        before = self.state.project_path.read_text(encoding="utf-8")
        st, j = self.call("/api/project", {"raw": {"title": "T", "segments": [{"id": "x", "text": "a", "image": "missing.jpg"}]}})
        self.assertEqual(st, 400)
        self.assertIn("missing.jpg", j["error"])
        self.assertEqual(self.state.project_path.read_text(encoding="utf-8"), before)
        raw = json.loads(before)
        raw["segments"][0]["label"] = "Intro"
        st, j = self.call("/api/project", {"raw": raw})
        self.assertEqual(st, 200)
        self.assertEqual(self.state.read_raw()["segments"][0]["label"], "Intro")

    def test_tts_endpoint_writes_audio_and_view_marks_fresh(self):
        def fake_synth(self_, text, voice, out_path):
            Path(out_path).write_bytes(b"ID3fake")
            return [Word("Hello.", 0, 0.5)]
        with mock.patch("vidforge.tts.edge.EdgeProvider.synthesize", fake_synth), \
                mock.patch("vidforge.ffmpeg.duration", return_value=0.5):
            st, j = self.call("/api/tts?lang=en", {"id": "s1"})
            self.assertEqual(st, 200)
            self.assertEqual(j["audio"], "build/audio/s1.mp3")
            st, view = self.call("/api/project")
            self.assertTrue(view["resolved"]["s1"]["audio_fresh"])
            # edit the text -> cache key changes -> stale
            raw = self.state.read_raw(); raw["segments"][0]["text"] = "Changed."
            self.call("/api/project", {"raw": raw})
            st, view = self.call("/api/project")
            self.assertFalse(view["resolved"]["s1"]["audio_fresh"])
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/files/build/audio/s1.mp3") as r:
            self.assertEqual(r.read(), b"ID3fake")

    def test_files_blocks_traversal(self):
        st, _ = self.call("/files/../project.json")
        self.assertIn(st, (403, 404))

    def test_upload_asset(self):
        st, j = self.call("/api/assets/upload", {"name": "my pic.png", "data_b64": base64.b64encode(b"png").decode()})
        self.assertEqual(st, 200)
        self.assertEqual(j["path"], "assets/my_pic.png")
        self.assertEqual((Path(self.td) / "assets" / "my_pic.png").read_bytes(), b"png")

    def test_build_runs_in_background_and_streams_log(self):
        def fake_build(project, **kw):
            pipeline._log("hello from build")
            time.sleep(0.3)
            pipeline._log("done")
        with mock.patch.object(pipeline, "build", fake_build):
            st, j = self.call("/api/build?lang=en&burn=0", {})
            self.assertEqual(st, 200)
            st, j2 = self.call("/api/build?lang=en", {})
            self.assertEqual(st, 409, "second build while running is refused")
            deadline = time.time() + 5
            while time.time() < deadline:
                st, s = self.call("/api/build/status")
                if s["state"] != "running":
                    break
                time.sleep(0.05)
            self.assertEqual(s["state"], "done")
            self.assertIn("[vidforge] hello from build", s["lines"])


if __name__ == "__main__":
    unittest.main()
