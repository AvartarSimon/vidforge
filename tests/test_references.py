"""参考视频 and 框架: the library, and a framework read from one video into a structure template.
Network, Whisper and the local model are stand-ins; the folders are temporary."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import ffmpeg, frameworks, references, structure


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Isolated(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        for target, attr, value in ((references, "REF_DIR", self.td / "refs"), (structure, "USER_DIR", self.td / "structures")):
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def clip(self, seconds: float = 30.0) -> bytes:
        f = self.td / "clip.mp4"
        ffmpeg.run(["-y", "-f", "lavfi", "-i", f"testsrc=s=320x240:r=24:d={seconds}", "-f", "lavfi", "-i", f"sine=d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(f)])
        return f.read_bytes()


class Library(Isolated):
    def test_links_are_told_apart_by_platform(self):
        for url, want in (("https://www.bilibili.com/video/BV1KD4y1c7xX", "bilibili"), ("https://b23.tv/abc", "bilibili"),
                          ("https://youtu.be/x", "youtube"), ("https://v.douyin.com/abc/", "douyin"),
                          ("https://www.xiaohongshu.com/explore/1", "xiaohongshu"), ("https://www.kuaishou.com/short-video/1", "kuaishou"),
                          ("https://example.com/v.mp4", "web")):
            self.assertEqual(references.platform_of(url), want, url)

    def test_apps_without_search_say_what_to_do_instead(self):
        with self.assertRaisesRegex(references.RefError, "粘贴链接"):
            references.search("douyin", "人口")

    def test_bilibili_results_come_back_most_played_first_without_markup(self):
        rows = {"result": [{"bvid": "BV1aaaaaaaaa", "title": '<em class="keyword">人口</em>少', "author": "a", "play": 10, "duration": "1:05", "pic": "//i0.hdslb.com/x.jpg"},
                           {"bvid": "BV1bbbbbbbbb", "title": "人口多", "author": "b", "play": 999, "duration": "12:00", "pic": ""}]}
        with mock.patch.object(references, "_bili_session", return_value=(None, {})), \
                mock.patch.object(references, "_bili_json", return_value=rows):
            out = references.search("bilibili", "人口")
        self.assertEqual([c["title"] for c in out], ["人口多", "人口少"])
        self.assertEqual((out[1]["seconds"], out[1]["thumb"]), (65, "https://i0.hdslb.com/x.jpg"))

    @unittest.skipUnless(_ff(), "ffmpeg not installed")
    def test_an_imported_file_joins_the_library_and_leaves_cleanly(self):
        info = references.import_file("我存的.mp4", self.clip(4), "存下来的")
        self.assertEqual((info["platform"], info["title"]), ("local", "存下来的"))
        self.assertAlmostEqual(info["seconds"], 4.0, delta=0.2)
        self.assertTrue((references.REF_DIR / info["id"] / "thumb.jpg").is_file())
        self.assertEqual([i["id"] for i in references.listing()], [info["id"]])
        with self.assertRaises(references.RefError):
            references.folder_of("../refs")
        references.remove(info["id"])
        self.assertEqual(references.listing(), [])
        with self.assertRaises(references.RefError):
            references.import_file("x.mp4", b"")


class Framework(Isolated):
    WORDS = [("2022年", 0.0, 0.8), ("中国人口", 0.8, 1.6), ("第一次减少了。", 1.6, 3.0), ("为什么", 3.4, 4.0), ("会这样？", 4.0, 5.0),
             ("先看", 6.0, 6.5), ("出生率", 6.5, 7.5), ("一直在降。", 7.5, 9.0)] + \
            [(f"第{i}句话讲数据。", 10.0 + i * 4, 13.0 + i * 4) for i in range(12)]

    def test_words_become_sentences_and_sentences_chunks(self):
        sents = frameworks.sentences(self.WORDS)
        self.assertEqual(sents[0]["text"], "2022年中国人口第一次减少了。")
        self.assertEqual(sents[1]["text"], "为什么会这样？")
        parts = frameworks.chunks(sents, seconds=10)
        self.assertLess(len(parts), len(sents))
        self.assertEqual(parts[0]["start"], 0.0)
        self.assertEqual(parts[-1]["end"], sents[-1]["end"])

    def test_the_pace_numbers(self):
        sents = frameworks.sentences(self.WORDS)
        m = frameworks.metrics(sents, cuts=[5.0, 12.0, 30.0], total=60.0)
        self.assertEqual((m["shots"], m["shot_seconds"], m["cuts_first_15s"], m["language"]), (4, 15.0, 2, "zh"))
        self.assertTrue(m["question_up_front"] and m["number_up_front"])

    def test_a_long_first_block_is_cut_at_the_hook_limit(self):
        parts = [{"start": i * 10.0, "end": i * 10.0 + 10, "text": f"t{i}"} for i in range(8)]
        blocks = frameworks.split_hook([{"name": "钩子", "from": 0, "to": 4, "role": "r", "technique": ""},
                                        {"name": "数据", "from": 5, "to": 7, "role": "r", "technique": ""}], parts, True)
        self.assertEqual([(b["name"], b["from"], b["to"]) for b in blocks], [("钩子", 0, 0), ("铺垫", 1, 4), ("数据", 5, 7)])

    def extract(self, llm_answer: dict | None):
        info = references.import_file("ref.mp4", self.clip(60), "参考")
        from vidforge import align, llm
        with mock.patch.object(align, "available", return_value=True), \
                mock.patch.object(align, "transcribe", return_value=self.WORDS), \
                mock.patch.object(llm, "available", return_value={"model": "x"} if llm_answer else None), \
                mock.patch.object(llm, "chat", return_value=json.dumps(llm_answer or {}, ensure_ascii=False)):
            return info, frameworks.extract(info["id"], log=lambda *_: None)

    @unittest.skipUnless(_ff(), "ffmpeg not installed")
    def test_without_a_model_the_video_is_cut_by_time_and_says_so(self):
        info, fw = self.extract(None)
        self.assertEqual(fw["made_by"], "time")
        self.assertEqual(fw["beats"][0]["name"], "钩子")
        self.assertEqual(fw["beats"][-1]["name"], "结尾")
        self.assertEqual(frameworks.load(info["id"])["template"], f"ref-{info['id']}")

    @unittest.skipUnless(_ff(), "ffmpeg not installed")
    def test_the_framework_becomes_a_template_the_script_step_can_use(self):
        answer = {"name": "数据反差", "about": "适合数据题材", "blocks": [
            {"name": "钩子", "from": 0, "to": 0, "role": "用一个反常的数字开场", "technique": "反差"},
            {"name": "数据", "from": 1, "to": 3, "role": "一次只摆一个指标", "technique": "对比"},
            {"name": "回扣", "from": 4, "to": 99, "role": "回到开场的数字", "technique": "首尾呼应"}]}
        info, fw = self.extract(answer)
        self.assertEqual((fw["made_by"], fw["name"]), ("llm", "数据反差"))
        ids = [t["id"] for t in structure.list_templates()]
        self.assertIn(fw["template"], ids)
        t = structure.get(fw["template"])
        self.assertAlmostEqual(sum(b.share for b in t.beats), 1.0, delta=0.06)
        self.assertLessEqual(t.beats[0].max_seconds, structure.HOOK_SECONDS)
        self.assertIn("手法：反差", t.beats[0].role)
        self.assertIn("用一个反常的数字开场", structure.prompt_block(fw["template"], 3))
        rows = structure.outline(fw["template"], 3)
        self.assertEqual([r["label"] for r in rows], ["钩子", "数据", "回扣"])


class Api(Isolated):
    def setUp(self):
        super().setUp()
        import threading
        from http.server import ThreadingHTTPServer
        from vidforge import ui
        patcher = mock.patch.object(ui, "RECENT", self.td / "recent.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.td / "p").mkdir()
        (self.td / "p" / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.State(self.td / "p" / "project.json")))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def call(self, path, body=None):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    @unittest.skipUnless(_ff(), "ffmpeg not installed")
    def test_import_watch_and_delete(self):
        import base64
        code, b = self.call("/api/refs/import", {"name": "a.mp4", "data_b64": base64.b64encode(self.clip(3)).decode(), "title": "存的"})
        self.assertEqual(code, 200, b)
        rid = json.loads(b)["item"]["id"]
        self.assertEqual(json.loads(self.call("/api/refs")[1])["items"][0]["id"], rid)
        code, video = self.call(f"/api/refs/file/{rid}/video.mp4")
        self.assertEqual(code, 200)
        self.assertGreater(len(video), 1000)
        self.assertEqual(self.call(f"/api/refs/file/{rid}/info.json")[0], 403, "only the video and the thumbnail are served")
        self.assertEqual(self.call("/api/refs/file/..%2F..%2Fetc/video.mp4")[0], 404)
        self.assertEqual(json.loads(self.call("/api/refs/delete", {"id": rid})[1])["items"], [])

    def test_covers_are_fetched_only_from_the_two_image_hosts(self):
        import urllib.parse
        for u in ("https://evil.example/x.jpg", "http://i0.hdslb.com/x.jpg", "file:///etc/passwd"):
            self.assertEqual(self.call("/api/refs/thumb?u=" + urllib.parse.quote(u))[0], 403, u)

    def test_only_your_own_frameworks_can_be_deleted(self):
        code, b = self.call("/api/structure/templates/delete", {"id": "data_explainer"})
        self.assertEqual(code, 400)
        structure.save_user_template(structure.Template(id="ref-x", name="x", about="", beats=[structure.Beat("b1", "钩子", "r", 1.0)]))
        code, b = self.call("/api/structure/templates/delete", {"id": "ref-x"})
        self.assertEqual(code, 200)
        self.assertNotIn("ref-x", [t["id"] for t in json.loads(b)["templates"]])


if __name__ == "__main__":
    unittest.main()
