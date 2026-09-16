"""Browser end-to-end: drive the wizard in headless Edge/Chrome through a whole video.

Skipped unless `playwright` is installed (pip install -e ".[dev]"); uses the browser already on
the machine (channel msedge -> chrome), so no browser download. TTS provider is `silent`
(no network), quality draft, 320x180 — the whole run takes ~30 s.

Path covered: script split -> voice all -> pick segment, upload a picture, add a second
still, set a hold -> render -> final.mp4 exists with the expected length -> publish step lists chapters.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

from vidforge import ffmpeg, ui


def _browser(p):
    for channel in ("msedge", "chrome"):
        try:
            return p.chromium.launch(channel=channel, headless=True)
        except Exception:  # noqa: BLE001
            continue
    return p.chromium.launch(headless=True)      # bundled browser, if the user installed one


@unittest.skipUnless(sync_playwright, "playwright not installed")
class Wizard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg.find_binary("ffmpeg")
        except ffmpeg.FfmpegError:
            raise unittest.SkipTest("ffmpeg not installed")
        cls.td = Path(tempfile.mkdtemp())
        (cls.td / "assets").mkdir()
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=teal:s=640x360", "-frames:v", "1", str(cls.td / "assets" / "seed.png")])
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=orange:s=360x640", "-frames:v", "1", str(cls.td / "upload.png")])
        (cls.td / "project.json").write_text(json.dumps({
            "title": "E2E", "tts": {"provider": "silent"}, "quality": "draft", "width": 320, "height": 180, "fps": 24,
            "encoder": "libx264", "segments": []}), encoding="utf-8")
        cls.state = ui.State(cls.td / "project.json")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(cls.state))
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_full_wizard_run(self):
        with sync_playwright() as p:
            browser = _browser(p)
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.url + "?step=1")

            # 1 script: paste two paragraphs, split
            page.fill("#script", "# Opening\nThe first segment talks about the sea.\n\nThe second segment is about the sky and clouds.")
            page.click("#splitBtn")
            page.wait_for_selector(".seg-row[data-i='1']")
            page.wait_for_function("document.querySelector('#saveState').textContent === '已保存'")
            raw = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
            self.assertEqual([s["id"] for s in raw["segments"]], ["seg1", "seg2"])
            self.assertEqual(raw["segments"][0]["label"], "Opening")

            # 2 voice: synthesize all (silent provider -> instant)
            page.click("#next")
            page.wait_for_selector("#ttsAll")
            page.click("#ttsAll")
            page.wait_for_function("document.querySelectorAll('.voice-row audio').length === 2", timeout=30000)

            # 3 visuals: seg1 <- uploaded picture (portrait -> blur fill) ; seg2 <- upload again + hold 2 s
            page.click("#next")
            page.wait_for_selector(".sb-card[data-id='seg1']")
            page.click(".sb-card[data-id='seg1']")
            page.click("#ptabs button[data-tab='upload']")
            page.set_input_files("#file", str(self.td / "upload.png"))
            page.wait_for_selector(".sb-card[data-id='seg1'] img", timeout=15000)
            page.click(".sb-card[data-id='seg2']")
            page.click("#ptabs button[data-tab='upload']")
            page.set_input_files("#file", str(self.td / "upload.png"))
            page.wait_for_selector(".sb-card[data-id='seg2'] img", timeout=15000)
            page.fill(".clip[data-i='0'] input[data-act='duration']", "2")
            page.dispatch_event(".clip[data-i='0'] input[data-act='duration']", "change")
            page.wait_for_function("document.querySelector('#saveState').textContent === '已保存'")
            raw = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["segments"][1]["clips"][0]["duration"], 2)

            # 4 render
            page.click("#next")
            page.wait_for_selector("#buildBtn")
            page.click("#buildBtn")
            page.wait_for_function("document.querySelector('#buildState').textContent === '完成'", timeout=180000)
            final = self.td / "build" / "final.mp4"
            self.assertTrue(final.exists(), "final.mp4 rendered")
            tl = json.loads((self.td / "build" / "timeline.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(ffmpeg.duration(final), tl[-1]["end"], delta=0.3)
            page.wait_for_selector("#result:not([hidden]) video")

            # 5 publish: chapters preview present, upload button enabled
            page.click("#next")
            page.wait_for_selector("#uploadBtn:not([disabled])")
            self.assertIn("Opening", page.text_content("details pre"))
            self.assertEqual(errors, [], f"JS errors: {errors}")
            browser.close()


if __name__ == "__main__":
    unittest.main()
