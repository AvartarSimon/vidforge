"""Retention structure templates, the script check, and the /api/structure/* routes."""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from vidforge import structure as st, ui


class TemplateTest(unittest.TestCase):
    def test_every_template_is_listed_with_its_beats(self):
        listed = st.list_templates()
        self.assertEqual({t["id"] for t in listed}, set(st.TEMPLATES))
        for t in listed:
            self.assertTrue(t["name"] and t["about"])
            self.assertTrue(all(b["name"] and b["role"] for b in t["beats"]))

    def test_shares_add_up(self):
        for tid, t in st.TEMPLATES.items():
            self.assertAlmostEqual(sum(b.share for b in t.beats), 1.0, places=2, msg=tid)

    def test_unknown_template_names_the_options(self):
        with self.assertRaises(KeyError) as cm:
            st.get("nope")
        self.assertIn("data_explainer", str(cm.exception))


class OutlineTest(unittest.TestCase):
    def test_runtime_is_spent(self):
        for tid in st.TEMPLATES:
            for minutes in (3, 8, 10, 20):
                total = sum(r["seconds"] for r in st.outline(tid, minutes))
                self.assertAlmostEqual(total, minutes * 60, delta=minutes * 60 * 0.03,
                                       msg=f"{tid} {minutes}min")

    def test_hook_stays_short_however_long_the_video(self):
        for tid in st.TEMPLATES:
            first = st.outline(tid, 30)[0]
            self.assertLessEqual(first["seconds"], st.HOOK_SECONDS, tid)

    def test_a_minute_is_the_floor(self):
        # 30 seconds of runtime would make every beat its own minimum and overshoot wildly
        self.assertAlmostEqual(sum(r["seconds"] for r in st.outline("news_take", 0.2)), 60, delta=4)

    def test_beats_are_split_so_no_segment_outlasts_a_picture_change(self):
        for r in st.outline("data_explainer", 20):
            self.assertLessEqual(r["seconds"] / r["segments"], st.MAX_SEGMENT_SECONDS, r["label"])

    def test_word_targets_follow_the_speaking_rates_the_prompt_uses(self):
        row = st.outline("data_explainer", 10)[3]
        self.assertEqual(row["zh_words"], round(row["seconds"] / 60 * 240))
        self.assertEqual(row["en_words"], round(row["seconds"] / 60 * 150))


class PromptTest(unittest.TestCase):
    def test_chinese_prompt_carries_every_beat_and_the_thresholds(self):
        block = st.prompt_block("data_explainer", 10)
        for beat in st.TEMPLATES["data_explainer"].beats:
            self.assertIn(beat.name, block)
        self.assertIn("15 秒", block)
        self.assertIn("25-35 秒", block)
        self.assertNotIn("Hard requirements", block)

    def test_english_prompt_is_english(self):
        block = st.prompt_block("history_explainer", 8, zh=False)
        self.assertIn("Hard requirements", block)
        self.assertNotIn("硬要求", block)

    def test_prompt_states_the_total_segment_count(self):
        rows = st.outline("news_take", 10)
        self.assertIn(str(sum(r["segments"] for r in rows)), st.prompt_block("news_take", 10))

    def test_prompt_starts_with_blank_lines_so_it_appends_cleanly(self):
        self.assertTrue(st.prompt_block("news_take", 10).startswith("\n\n"))


class SkeletonTest(unittest.TestCase):
    def test_ids_are_unique_and_labels_are_numbered_only_when_split(self):
        segs = st.skeleton_segments("data_explainer", 10)
        self.assertEqual(len(segs), len({s["id"] for s in segs}))
        hook = segs[0]
        self.assertEqual(hook["id"], "hook")
        self.assertEqual(hook["label"], "钩子")
        split = [s for s in segs if s["id"].startswith("data")]
        self.assertGreater(len(split), 1)
        self.assertEqual(split[0]["label"], "数据 1")

    def test_segments_are_empty_but_carry_the_brief(self):
        for s in st.skeleton_segments("history_explainer", 8):
            self.assertEqual(s["text"], "")
            self.assertEqual(s["clips"], [])
            self.assertTrue(s["_brief"])
            self.assertGreater(s["_target_seconds"], 0)

    def test_the_skeleton_passes_its_own_retention_check(self):
        # a template that the check would flag is a template that teaches the wrong shape
        for tid in st.TEMPLATES:
            for minutes in (3, 5, 8, 10, 15, 20):
                segs = st.skeleton_segments(tid, minutes)
                durations = {s["id"]: s["_target_seconds"] for s in segs}
                # the empty-text hook check cannot pass before anything is written
                found = [i.what for i in st.check(segs, durations) if "开场" not in i.what]
                self.assertEqual(found, [], f"{tid} {minutes}min")


class CheckTest(unittest.TestCase):
    def seg(self, sid, text, label=""):
        return {"id": sid, "label": label, "text": text}

    def test_empty_script(self):
        issues = st.check([])
        self.assertEqual(issues[0].level, "problem")

    def test_a_hook_without_a_number_or_a_question_is_a_problem(self):
        issues = st.check([self.seg("s1", "今天我们来聊一聊房地产这个话题，先打个招呼。")])
        self.assertTrue(any("开场" in i.what and i.level == "problem" for i in issues))

    def test_a_number_in_the_hook_clears_it(self):
        issues = st.check([self.seg("s1", "去年有 680 万平方米新房没卖掉。")])
        self.assertFalse(any("开场" in i.what for i in issues))

    def test_a_question_in_the_hook_clears_it(self):
        issues = st.check([self.seg("s1", "为什么降息之后房价反而跌了？")])
        self.assertFalse(any("开场" in i.what for i in issues))

    def test_a_long_first_segment_dilutes_the_hook(self):
        issues = st.check([self.seg("s1", "x"), self.seg("s2", "y")], {"s1": 41.0, "s2": 20.0})
        self.assertTrue(any("钩子被稀释" in i.what for i in issues))

    def test_one_segment_running_from_the_hook_through_the_dropoff(self):
        issues = st.check([self.seg("s1", "x"), self.seg("s2", "y")], {"s1": 41.0, "s2": 30.0})
        bad = [i for i in issues if "没有换气" in i.what]
        self.assertEqual([i.level for i in bad], ["problem"])
        self.assertEqual(bad[0].where, "s1")

    def test_a_fresh_beat_at_fifteen_seconds_is_not_flagged(self):
        issues = st.check([self.seg("s1", "1"), self.seg("s2", "2"), self.seg("s3", "3")],
                          {"s1": 15.0, "s2": 28.0, "s3": 20.0})
        self.assertFalse(any("没有换气" in i.what for i in issues))

    def test_one_segment_before_the_intro_metric(self):
        issues = st.check([self.seg("s1", "1"), self.seg("s2", "2")], {"s1": 40.0, "s2": 40.0})
        self.assertTrue(any("前 30 秒" in i.what for i in issues))

    def test_segments_longer_than_the_limit_are_each_reported(self):
        segs = [self.seg(f"s{i}", "x") for i in range(4)]
        issues = st.check(segs, {"s0": 10.0, "s1": 50.0, "s2": 20.0, "s3": 60.0})
        self.assertEqual({i.where for i in issues if "切换点" in i.what}, {"s1", "s3"})

    def test_a_long_video_without_chapter_names(self):
        segs = [self.seg(f"s{i}", "x") for i in range(20)]
        issues = st.check(segs, {f"s{i}": 30.0 for i in range(20)})
        self.assertTrue(any("章节名" in i.what for i in issues))

    def test_chapter_names_clear_it(self):
        segs = [self.seg(f"s{i}", "x", label=f"第{i}章") for i in range(20)]
        issues = st.check(segs, {f"s{i}": 30.0 for i in range(20)})
        self.assertFalse(any("章节名" in i.what for i in issues))

    def test_the_ending_should_come_back_to_the_opening_number(self):
        segs = [self.seg("s1", "去年有 680 万平方米新房没卖掉。"), self.seg("s2", "就讲到这里，下期再见。")]
        issues = st.check(segs, {"s1": 15.0, "s2": 20.0})
        self.assertTrue(any("回到开场" in i.what for i in issues))

    def test_repeating_the_number_clears_the_callback_check(self):
        segs = [self.seg("s1", "去年有 680 万平方米新房没卖掉。"),
                self.seg("s2", "那 680 万平方米最后会落到谁手上，这才是问题。")]
        issues = st.check(segs, {"s1": 15.0, "s2": 20.0})
        self.assertFalse(any("回到开场" in i.what for i in issues))

    def test_length_is_estimated_from_the_text_when_nothing_is_rendered(self):
        # 240 字/分钟 means roughly four Chinese characters a second
        long_zh = self.seg("s1", "字" * 200)
        issues = st.check([long_zh, self.seg("s2", "字" * 40)])
        self.assertTrue(any("切换点" in i.what and i.where == "s1" for i in issues))

    def test_english_text_is_measured_in_words(self):
        issues = st.check([self.seg("s1", "word " * 150), self.seg("s2", "word " * 20)])
        self.assertTrue(any("切换点" in i.what and i.where == "s1" for i in issues))

    def test_a_short_script_is_not_held_to_the_dropoff_rules(self):
        issues = st.check([self.seg("s1", "为什么？")], {"s1": 20.0})
        self.assertEqual(issues, [])


class StructureApi(unittest.TestCase):
    """Its own project, because /api/structure/apply rewrites the segments."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        root = Path(self.td)
        (root / "assets").mkdir()
        (root / "project.json").write_text(json.dumps({
            "title": "T", "voice": "en-US-AndrewNeural", "target_minutes": 10,
            "segments": [{"id": "s1", "text": "Housing starts fell by 680,000 last year."}],
        }), encoding="utf-8")
        self.state = ui.State(root / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_templates(self):
        status, j = self.call("/api/structure/templates")
        self.assertEqual(status, 200)
        self.assertEqual({t["id"] for t in j["templates"]}, set(st.TEMPLATES))

    def test_outline_returns_rows_and_the_prompt(self):
        status, j = self.call("/api/structure/outline?template=data_explainer&minutes=10")
        self.assertEqual(status, 200)
        self.assertEqual(len(j["rows"]), len(st.TEMPLATES["data_explainer"].beats))
        self.assertIn("钩子", j["prompt"])

    def test_outline_in_english(self):
        _, j = self.call("/api/structure/outline?template=news_take&minutes=8&zh=0")
        self.assertIn("Hard requirements", j["prompt"])

    def test_outline_rejects_an_unknown_template(self):
        status, j = self.call("/api/structure/outline?template=nope")
        self.assertEqual(status, 400)
        self.assertIn("nope", j["error"])

    def test_check_falls_back_to_estimated_durations(self):
        status, j = self.call("/api/structure/check")
        self.assertEqual(status, 200)
        self.assertFalse(j["measured"])
        self.assertTrue(all({"level", "where", "what", "fix"} <= set(i) for i in j["issues"]))

    def test_check_uses_the_rendered_timeline_when_there_is_one(self):
        bd = Path(self.td) / "build"
        bd.mkdir()
        (bd / "timeline.json").write_text(json.dumps(
            [{"id": "s1", "label": "", "start": 0, "end": 55}]), encoding="utf-8")
        _, j = self.call("/api/structure/check")
        self.assertTrue(j["measured"])
        self.assertTrue(any("切换点" in i["what"] for i in j["issues"]))

    def test_apply_refuses_to_clobber_an_existing_script(self):
        status, j = self.call("/api/structure/apply", {"template": "data_explainer", "minutes": 10})
        self.assertEqual(status, 409)
        self.assertTrue(j["has_segments"])
        self.assertEqual(len(json.loads((Path(self.td) / "project.json").read_text())["segments"]), 1)

    def test_apply_with_replace_writes_the_skeleton_without_private_keys(self):
        status, j = self.call("/api/structure/apply",
                              {"template": "data_explainer", "minutes": 10, "replace": True})
        self.assertEqual(status, 200)
        on_disk = json.loads((Path(self.td) / "project.json").read_text(encoding="utf-8"))["segments"]
        self.assertEqual(len(on_disk), len(j["segments"]))
        self.assertTrue(any(k.startswith("_") for k in j["segments"][0]), "UI needs the brief")
        self.assertFalse(any(k.startswith("_") for s in on_disk for k in s), "project.json must stay clean")
        self.assertEqual(on_disk[0]["id"], "hook")

    def test_apply_rejects_an_unknown_template(self):
        status, _ = self.call("/api/structure/apply", {"template": "nope", "replace": True})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
