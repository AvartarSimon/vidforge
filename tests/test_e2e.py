"""Browser end-to-end: drive the UI in headless Edge/Chrome through a whole video.

Skipped unless `playwright` is installed (pip install -e ".[dev]") and the React UI is built; uses
the browser already on the machine (channel msedge -> chrome), so no browser download. TTS
provider is `silent` (no network), quality draft, 320x180 — the whole run takes ~40 s.

Path covered: paste a script, split it -> voice all -> pick a segment, upload a picture, upload
another and set its hold -> render -> final.mp4 has the timeline's length -> publish lists the
chapters. Then the language switcher: a variant's text is edited in its own field and the
original's text is left alone.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
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
@unittest.skipUnless(ui.react_ready(), "React UI not built (npm run build in vidforge/ui/react)")
class Wizard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg.find_binary("ffmpeg")
        except ffmpeg.FfmpegError:
            raise unittest.SkipTest("ffmpeg not installed")
        cls.td = Path(tempfile.mkdtemp())
        (cls.td / "assets").mkdir()
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=orange:s=360x640", "-frames:v", "1", str(cls.td / "upload.png")])
        (cls.td / "project.json").write_text(json.dumps({
            "title": "E2E", "language": "en", "tts": {"provider": "silent"}, "quality": "draft",
            "width": 320, "height": 180, "fps": 24, "encoder": "libx264", "segments": []}), encoding="utf-8")
        cls.state = ui.State(cls.td / "project.json")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(cls.state))
        cls.url = f"http://127.0.0.1:{cls.httpd.server_address[1]}/"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        shutil.rmtree(cls.td, ignore_errors=True)

    def raw(self) -> dict:
        return json.loads((self.td / "project.json").read_text(encoding="utf-8"))

    def saved(self, page):
        page.get_by_text("已保存", exact=False).first.wait_for(timeout=10000)

    def test_full_run_then_a_language_variant(self):
        with sync_playwright() as p:
            browser = _browser(p)
            page = browser.new_page(viewport={"width": 1400, "height": 950})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.url)
            step = lambda name: page.get_by_role("banner").get_by_text(name, exact=True).click()   # noqa: E731

            # 1 script: paste two paragraphs, split, accept the preview
            step("脚本")
            page.get_by_label("脚本", exact=True).fill(
                "# Opening\nThe first segment talks about the sea.\n\nThe second segment is about the sky and clouds.")
            page.get_by_role("button", name="拆成段落").click()
            page.get_by_role("button", name="采用这").click()
            page.wait_for_function("document.body.innerText.includes('段落（2）')")
            self.saved(page)
            page.wait_for_timeout(900)
            raw = self.raw()
            self.assertEqual([s["id"] for s in raw["segments"]], ["seg1", "seg2"])
            self.assertEqual(raw["segments"][0].get("label"), "Opening")

            # 2 voice: synthesize all (silent provider -> instant)
            step("配音")
            page.get_by_role("button", name="全部配音").click()
            page.wait_for_function("document.querySelectorAll('audio').length >= 2", timeout=30000)

            # 3 visuals: a picture for each segment; the second held for 2 s
            step("画面")
            for seg in ("seg1", "seg2"):
                page.locator(f"[data-seg='{seg}']").click()
                page.get_by_role("tab", name="本地文件").click()
                page.locator("input[type=file][accept='image/*,video/*'][multiple]").set_input_files(str(self.td / "upload.png"))
                page.locator(f"[data-seg='{seg}']").get_by_text("1 个片段").wait_for(timeout=15000)
            page.get_by_label("停留秒数").first.fill("2")
            self.saved(page)
            page.wait_for_timeout(900)
            self.assertEqual(self.raw()["segments"][1]["clips"][0].get("duration"), 2)

            # 4 render
            step("渲染")
            page.get_by_role("button", name="▶ 渲染").click()
            page.get_by_text("完成", exact=True).first.wait_for(timeout=180000)
            final = self.td / "build" / "final.mp4"
            self.assertTrue(final.exists(), "final.mp4 rendered")
            tl = json.loads((self.td / "build" / "timeline.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(ffmpeg.duration(final), tl[-1]["end"], delta=0.3)

            # 5 publish: the chapters are listed
            step("发布")
            page.wait_for_function("document.body.innerText.includes('Opening')")

            # a language variant: the top bar switches the script to text_zh, the original stays
            raw = self.raw()
            raw["variants"] = {"zh": {"voice": "zh-CN-YunxiNeural"}}
            (self.td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
            page.goto(self.url)
            step("脚本")
            page.get_by_role("banner").get_by_role("combobox").click()
            page.get_by_role("option", name="zh").click()
            page.wait_for_function("location.search.includes('lang=zh')")
            page.get_by_label("旁白（zh）").first.fill("第一段讲大海。")
            self.saved(page)
            page.wait_for_timeout(900)
            seg1 = self.raw()["segments"][0]
            self.assertEqual(seg1.get("text_zh"), "第一段讲大海。")
            self.assertEqual(seg1["text"], "The first segment talks about the sea.")
            self.assertEqual(errors, [], f"JS errors: {errors}")
            browser.close()


if __name__ == "__main__":
    unittest.main()
