"""Web UI API against a real ThreadingHTTPServer on a temp project. TTS and asset providers stubbed."""

from __future__ import annotations

import base64
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import pipeline, ui
from vidforge.assets import Candidate
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
                {"id": "s1", "text": "Mount Tambora erupted in 1815.", "text_zh": "你好。", "clips": [{"image": "assets/a.jpg"}]},
                {"id": "s2", "text": "Card.", "remotion": {"composition": "TitleCard", "props": {"title": "X"}}},
            ]}, ensure_ascii=False), encoding="utf-8")
        cls.state = ui.State(root / "project.json")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(cls.state))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
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

    def test_static_files(self):
        for path in ("/", "/static/app.js", "/static/style.css"):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
                self.assertEqual(r.status, 200, path)

    def test_project_view_has_clips_need_and_keywords(self):
        st, j = self.call("/api/project")
        self.assertEqual(st, 200)
        s1 = j["resolved"]["s1"]
        self.assertEqual(s1["clips"][0]["kind"], "image")
        self.assertEqual(s1["clips"][0]["path"], "assets/a.jpg")
        self.assertGreater(s1["need"], 1.0)
        self.assertIn("Mount Tambora", s1["keywords"])
        self.assertEqual(j["resolved"]["s2"]["clips"][0]["remotion"], "TitleCard")
        st, j = self.call("/api/project?lang=zh")
        self.assertIn("s2", j["issues"])
        self.assertEqual(j["build_dir"], "build_zh")

    def test_save_rejects_invalid_and_keeps_file(self):
        before = self.state.project_path.read_text(encoding="utf-8")
        st, j = self.call("/api/project", {"raw": {"title": "T", "segments": [{"id": "x", "text": "a", "clips": [{"image": "missing.jpg"}]}]}})
        self.assertEqual(st, 400)
        self.assertEqual(self.state.project_path.read_text(encoding="utf-8"), before)

    def test_tts_and_freshness(self):
        def fake_synth(self_, text, voice, out_path):
            Path(out_path).write_bytes(b"ID3fake"); return [Word("Hello.", 0, 0.5)]
        with mock.patch("vidforge.tts.edge.EdgeProvider.synthesize", fake_synth), mock.patch("vidforge.ffmpeg.duration", return_value=0.5):
            st, j = self.call("/api/tts?lang=en", {"id": "s1"})
            self.assertEqual(st, 200)
            st, view = self.call("/api/project")
            self.assertTrue(view["resolved"]["s1"]["audio_fresh"])

    def test_search_reports_missing_key_and_fetch_downloads(self):
        with mock.patch.dict("os.environ", {"PEXELS_API_KEY": ""}):
            st, j = self.call("/api/search?source=pexels&kind=image&q=volcano")
        self.assertEqual(st, 400)
        self.assertEqual(j.get("needs_key"), "PEXELS_API_KEY")
        cand = Candidate(provider="pexels", id="77", kind="image", thumb_url="t", preview_url="p", download_url="http://x/y.jpg",
                         width=4000, height=2000, duration=None, author="A", license="Pexels License", page_url="pg", title="volcano")
        with mock.patch("vidforge.assets.search", return_value=[cand]):
            st, j = self.call("/api/search?source=pexels&kind=image&q=volcano")
        self.assertEqual(st, 200); self.assertEqual(j["candidates"][0]["id"], "77")
        with mock.patch("vidforge.assets.pexels.download", side_effect=lambda url, dest: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(b"jpg"), dest)[2]), \
                mock.patch("vidforge.llm.vision_model", return_value=None):      # keep the suite offline
            st, j = self.call("/api/assets/fetch", {"candidate": cand.__dict__})
        self.assertEqual(st, 200)
        self.assertEqual(j["path"], "assets/pexels/volcano-77.jpg")
        self.assertIn("Pexels License", j["credit"])
        self.assertTrue((Path(self.td) / "assets" / "index.json").exists())

    def test_autofill_picks_a_picture_right_away(self):
        """One click gives every clip-less segment a downloaded image (spec kept for re-pick),
        remotion/existing segments untouched, and a segment nothing is found for is reported."""
        raw = self.state.read_raw()
        raw["segments"].append({"id": "s3", "text": "The Battle of Lexington began the war."})
        raw["segments"].append({"id": "s4", "text": "Nothing matches this."})
        self.state.write_raw(raw)
        try:
            cand = Candidate(provider="commons", id="9", kind="image", thumb_url="t", preview_url="p", download_url="http://x/lex.jpg",
                             width=3000, height=2000, duration=None, author="A", license="Public domain", page_url="pg", title="Battle of Lexington.jpg")

            def fake_search(root, provider, query, kind, page=1, relax=True):
                return [cand] if "Lexington" in query else []
            fake_dl = lambda url, dest, referer=None, retries=3: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(b"jpg"), dest)[2]
            with mock.patch("vidforge.assets.search", fake_search), mock.patch("vidforge.assets.wikimedia.download", fake_dl), \
                    mock.patch("vidforge.llm.available", return_value=None), mock.patch.dict("os.environ", {"PEXELS_API_KEY": "", "PIXABAY_API_KEY": ""}):
                st, j = self.call("/api/autofill", {"source": "commons", "sync": True})
            self.assertEqual(st, 200)
            self.assertEqual((j["filled"], j["resolved"]), (2, 1))
            self.assertEqual([f["id"] for f in j["failed"]], ["s4"])
            raw = self.state.read_raw()
            segs = {s["id"]: s for s in raw["segments"]}
            self.assertEqual(segs["s3"]["clips"], [{"image": "commons:Battle Lexington", "motion": "zoom_in"}])
            self.assertEqual(segs["s1"]["clips"], [{"image": "assets/a.jpg"}])      # untouched
            self.assertNotIn("clips", segs["s2"])                                   # remotion segment untouched
            st, j = self.call("/api/project")
            self.assertEqual(j["resolved"]["s3"]["clips"][0]["path"], "assets/commons/battle-of-lexington-9.jpg")
            self.assertEqual(j["resolved"]["s4"]["clips"], [])                     # nothing accurate: left empty, no spec
            st, j = self.call("/api/autofill")
            self.assertEqual(j["state"], "done")
        finally:
            raw = self.state.read_raw()
            raw["segments"] = [s for s in raw["segments"] if s["id"] not in ("s3", "s4")]
            self.state.write_raw(raw)

    def test_upload_asset(self):
        import io
        from PIL import Image
        buf = io.BytesIO(); Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
        st, j = self.call("/api/assets/upload", {"name": "my pic.png", "data_b64": base64.b64encode(buf.getvalue()).decode()})
        self.assertEqual(st, 200); self.assertEqual(j["path"], "assets/local/my_pic.png"); self.assertEqual(j["kind"], "image")

    def test_upload_rejects_unreadable_image(self):
        st, j = self.call("/api/assets/upload", {"name": "bad.jpg", "data_b64": base64.b64encode(b"not an image").decode()})
        self.assertEqual(st, 400)
        self.assertIn("HEIC", j["error"])
        self.assertFalse((Path(self.td) / "assets" / "local" / "bad.jpg").exists())

    def test_health(self):
        st, j = self.call("/api/health")
        self.assertEqual(st, 200); self.assertIn("ffmpeg", j); self.assertIn("keys", j)

    def test_build_background_and_cancel(self):
        def fake_build(project, **kw):
            pipeline._log("hello from build")
            for _ in range(20):
                pipeline._check_cancel(); time.sleep(0.05)
            pipeline._log("done")
        with mock.patch.object(pipeline, "build", fake_build):
            st, j = self.call("/api/build?lang=en&burn=0", {})
            self.assertEqual(st, 200)
            st, _ = self.call("/api/build?lang=en", {})
            self.assertEqual(st, 409)
            time.sleep(0.2)
            self.call("/api/build/cancel", {})
            for _ in range(60):
                st, s = self.call("/api/build/status")
                if s["state"] != "running":
                    break
                time.sleep(0.05)
            self.assertEqual(s["state"], "cancelled")
            self.assertIn("[vidforge] hello from build", s["lines"])


if __name__ == "__main__":
    unittest.main()
