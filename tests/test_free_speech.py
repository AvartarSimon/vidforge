"""按要点说: the script is the plan, the take says it in other words, the subtitles say what was said.
Whisper and the local model are stand-ins; ffmpeg is real."""
from __future__ import annotations

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

from vidforge import align as aligner, ffmpeg, narration, pipeline, points, project as proj, ui

PLAN = "去年全国有六百八十万平方米的新房没有卖掉。这个数字背后是三个故事。"
SAID = "去年啊，全国差不多有六百八十万平方米新房没卖出去。"


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


def heard_of(text: str, sure: float = 0.9):
    return [(c, i * 0.12, i * 0.12 + 0.12, 0.3 if c == "卖" else sure) for i, c in enumerate(aligner.tokenize(text))]


class Model(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        (self.td / "a.mp3").write_bytes(b"x")
        (self.td / "b.mp3").write_bytes(b"y")

    def load(self, **seg):
        raw = {"title": "t", "narration_mode": "free",
               "segments": [{"id": "s", "text": PLAN, "narration": "a.mp3", **seg}]}
        (self.td / "project.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return proj.load(self.td / "project.json")

    def test_the_subtitles_say_what_this_take_said_and_not_a_replaced_one(self):
        p = self.load(spoken={"text": SAID, "take": "a.mp3", "checked": True})
        self.assertEqual(p.narration_mode, "free")
        self.assertEqual(p.segments[0].said, SAID)
        self.assertEqual(p.segments[0].text, PLAN, "the plan is kept")
        stale = self.load(spoken={"text": SAID, "take": "b.mp3"})
        self.assertEqual(stale.segments[0].said, PLAN, "heard from another take: not these words")

    def test_points_and_the_mode_round_trip_and_go_to_the_next_episode(self):
        p = self.load(points=["六百八十万", " "])
        self.assertEqual(p.segments[0].points, ["六百八十万"])
        self.assertIn("narration_mode", proj.SERIES_KEYS)


class Points(unittest.TestCase):
    def test_the_local_model_condenses_but_may_not_invent_a_figure(self):
        from vidforge import llm
        answer = json.dumps({"points": ["新房 680 万平方米没卖", "三个故事", "降价 30%"]}, ensure_ascii=False)
        with mock.patch.object(llm, "available", return_value={"model": "x"}), mock.patch.object(llm, "chat", return_value=answer):
            got, how = points.condense(PLAN)
        self.assertEqual(how, "llm")
        self.assertEqual(got, ["新房 680 万平方米没卖", "三个故事"], "30% is not in the script")

    def test_a_figure_the_model_dropped_comes_back_with_its_sentence(self):
        from vidforge import llm
        script = "第一步从睡眠开始。每天晚上十点半放下手机。接下来二十一天，我会每天记录。"
        answer = json.dumps({"points": ["从睡眠开始", "放下手机"]}, ensure_ascii=False)
        with mock.patch.object(llm, "available", return_value={"model": "x"}), mock.patch.object(llm, "chat", return_value=answer):
            got, _ = points.condense(script)
        self.assertEqual(got[:2], ["从睡眠开始", "放下手机"])
        self.assertTrue(any("十点半" in g for g in got) and any("二十一天" in g for g in got), got)

    def test_without_a_model_the_sentences_are_the_points(self):
        from vidforge import llm
        with mock.patch.object(llm, "available", return_value=None):
            got, how = points.condense(PLAN)
        self.assertEqual((how, got), ("sentences", ["去年全国有六百八十万平方米的新房没有卖掉。", "这个数字背后是三个故事。"]))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Build(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=f=220:d=4", str(self.td / "take.m4a")])

    def build(self, **seg):
        raw = {"title": "t", "language": "zh", "narration_mode": "free", "width": 320, "height": 180, "quality": "draft",
               "encoder": "libx264", "tts": {"provider": "silent"},
               "segments": [{"id": "s", "text": PLAN, "narration": "take.m4a", **seg}]}
        (self.td / "project.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(aligner, "available", return_value=True), \
             mock.patch.object(aligner, "transcribe", return_value=heard_of(SAID)) as tr:
            pipeline.set_log(lambda *_: None)
            try:
                pipeline.build(proj.load(self.td / "project.json"))
            finally:
                pipeline.set_log(None)
        return (self.td / "build" / "final.srt").read_text(encoding="utf-8"), tr.call_count

    def test_a_take_nobody_has_checked_still_gets_its_own_words_as_subtitles(self):
        srt, calls = self.build()
        self.assertIn("差不多", srt)
        self.assertNotIn("三个故事", srt, "the plan's sentence was never said")
        self.assertEqual(calls, 1, "heard once, for the words and their times")

    def test_checked_subtitles_are_used_as_written(self):
        srt, _ = self.build(spoken={"text": "去年全国有六百八十万平方米新房没卖出去。", "take": "take.m4a", "checked": True})
        self.assertIn("六百八十万", srt)
        self.assertNotIn("差不多", srt)

    def test_fixing_a_subtitle_does_not_draw_the_picture_again(self):
        self.build(spoken={"text": SAID, "take": "take.m4a", "checked": True})
        clips = self.td / "build" / "clips"
        base = {f.name for f in clips.glob("*.mp4") if f.stem.count(".") == 1}
        self.build(spoken={"text": SAID.replace("差不多", "大约"), "take": "take.m4a", "checked": True})
        self.assertEqual({f.name for f in clips.glob("*.mp4") if f.stem.count(".") == 1}, base, "same base clip")


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Api(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.td, True)
        patcher = mock.patch.object(ui, "RECENT", self.td / "recent.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.td / "assets").mkdir()
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=f=220:d=3", str(self.td / "assets" / "take.mp3")])
        (self.td / "project.json").write_text(json.dumps({
            "title": "t", "language": "zh", "narration_mode": "free",
            "segments": [{"id": "s", "text": PLAN, "clips": []}]}, ensure_ascii=False), encoding="utf-8")
        self.state = ui.State(self.td / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def call(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def raw(self):
        return json.loads((self.td / "project.json").read_text(encoding="utf-8"))

    def test_a_take_lands_with_its_words_unchecked_and_checking_keeps_the_plan(self):
        import base64
        data = base64.b64encode((self.td / "assets" / "take.mp3").read_bytes()).decode()
        with mock.patch.object(self.state, "WARM", True), mock.patch.object(aligner, "available", return_value=True), \
             mock.patch.object(aligner, "transcribe", return_value=heard_of(SAID)):
            self.call("/api/narration/upload", {"segment": "s", "data": data, "ext": "mp3"})
            for _ in range(100):                     # written in the background, while the next take is recorded
                if (self.raw()["segments"][0].get("spoken") or {}).get("text"):
                    break
                time.sleep(0.1)
            sp = self.raw()["segments"][0]["spoken"]
            self.assertEqual((sp["text"], sp["checked"]), ("去年啊全国差不多有六百八十万平方米新房没卖出去。", False))
            self.assertEqual(sp["take"], self.raw()["segments"][0]["narration"])
            self.assertEqual([d[0] for d in sp["doubt"]], ["卖"], "the word Whisper was unsure of, to look at")
            status, j = self.call("/api/narration/recognize", {"segment": "s"})
            self.assertEqual((status, j["mode"], j["checked"]), (200, "free", False))
            status, j = self.call("/api/narration/recognize", {"segment": "s", "apply": "去年全国差不多有六百八十万平方米新房没卖出去。"})
            self.assertEqual((status, j["to"]), (200, "spoken"))
        seg = self.raw()["segments"][0]
        self.assertEqual(seg["text"], PLAN, "checking the subtitles never rewrites the plan")
        self.assertEqual((seg["spoken"]["text"], seg["spoken"]["checked"]), ("去年全国差不多有六百八十万平方米新房没卖出去。", True))

    def test_points_come_back_for_the_teleprompter(self):
        from vidforge import llm
        with mock.patch.object(llm, "available", return_value=None):
            status, j = self.call("/api/narration/points", {"segment": "s"})
        self.assertEqual((status, j["by"], len(j["points"])), (200, "sentences", 2))


if __name__ == "__main__":
    unittest.main()
