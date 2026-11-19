"""多平台导出: shape per platform, length warnings that never block, the upload text."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, platforms, project as proj


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Rules(unittest.TestCase):
    def test_upright_platforms_are_upright(self):
        for pid in ("douyin", "kuaishou", "tiktok", "shorts", "shipinhao"):
            p = platforms.get(pid)
            self.assertLess(p.width, p.height, pid)
        for pid in ("toutiao", "youtube"):
            p = platforms.get(pid)
            self.assertGreater(p.width, p.height, pid)

    def test_too_long_is_a_warning_not_an_error(self):
        w = platforms.check(platforms.get("shorts"), 400)
        self.assertTrue(any("最长" in x for x in w))

    def test_toutiao_wants_a_minute(self):
        self.assertTrue(any("1 分钟" in x for x in platforms.check(platforms.get("toutiao"), 40)))

    def test_unknown_platform_names_the_options(self):
        with self.assertRaises(platforms.PlatformError) as cm:
            platforms.get("myspace")
        self.assertIn("douyin", str(cm.exception))

    def test_post_text_carries_title_tags_and_ai_line(self):
        p = proj.Project(title="一个很长的标题" * 10, segments=[], root=Path("."), language="zh")
        p.youtube.tags = ["历史", "美国 独立战争"]
        t = platforms.post_text(p, platforms.get("shipinhao"))
        self.assertIn("#历史 #美国独立战争", t)
        self.assertIn("截断", t)
        self.assertIn("人工智能生成内容", t)

    def test_post_text_carries_the_credits_the_licences_ask_for(self):
        p = proj.Project(title="t", segments=[], root=Path("."), language="zh")
        credits = "Media credits\nWikimedia Commons:\n  Jane Doe — CC BY-SA 4.0 — https://commons.wikimedia.org/x"
        self.assertIn("Jane Doe — CC BY-SA 4.0", platforms.post_text(p, platforms.get("douyin"), credits))
        self.assertNotIn("署名", platforms.post_text(p, platforms.get("douyin")))

    def test_an_upright_master_on_a_landscape_platform_is_flagged(self):
        yt, dy = platforms.get("youtube"), platforms.get("douyin")
        self.assertTrue(any("竖屏" in w for w in platforms.check(yt, 120, (1080, 1920))))
        self.assertFalse(any("竖屏" in w for w in platforms.check(dy, 120, (1080, 1920))))
        self.assertFalse(any("竖屏" in w for w in platforms.check(yt, 120, (1920, 1080))))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Export(unittest.TestCase):
    def test_landscape_final_becomes_each_shape(self):
        td = Path(tempfile.mkdtemp())
        try:
            src = td / "final.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "sine=d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)])
            (td / "credits.txt").write_text("Media credits\n  Jane Doe — CC BY 4.0 — http://x", encoding="utf-8")
            p = proj.Project(title="t", segments=[], root=td)
            for pid, size in (("douyin", (1080, 1920)), ("youtube", (1920, 1080)), ("xiaohongshu", (1080, 1440)),
                              ("bilibili", (1920, 1080))):
                r = platforms.export(p, src, td / "out", pid, log=lambda *_: None)
                self.assertEqual(ffmpeg.video_size(r["path"]), size, pid)
                self.assertAlmostEqual(r["seconds"], 2.0, delta=0.15)
                self.assertTrue(Path(r["text"]).is_file())
                self.assertIn("Jane Doe", Path(r["text"]).read_text(encoding="utf-8"))
            from PIL import Image

            def size(c):
                with Image.open(c) as im:
                    return im.size
            shapes = {pid: [size(c) for c in platforms.export(p, src, td / "out", pid, log=lambda *_: None)["covers"]]
                      for pid in ("douyin", "tiktok", "youtube", "xiaohongshu")}
            self.assertEqual(shapes, {"douyin": [(1080, 1920), (1080, 1440)], "tiktok": [(1080, 1920)],
                                      "youtube": [(1280, 720)], "xiaohongshu": [(1080, 1440)]},
                             "each app's own cover shapes, the 3:4 grid tile where it has one")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_a_title_on_an_upright_cover_is_broken_into_lines(self):
        from vidforge import thumbnail
        self.assertEqual(thumbnail.wrap_for("中国人口六十一年来第一次减少", (1080, 1920)), "中国人口六十一\n年来第一次减少")
        self.assertEqual(thumbnail.wrap_for("中国人口六十一年来第一次减少", (1280, 720)), "中国人口六十一年来第一次减少")
        self.assertEqual(thumbnail.wrap_for("自己\n分的行", (1080, 1920)), "自己\n分的行")
        self.assertEqual(thumbnail.wrap_for("Why did 1816 have no summer at all", (1080, 1920)),
                         "Why did 1816\nhave no summer\nat all")


class SuggestText(unittest.TestCase):
    """标题 / 简介 / 话题 by the local model: the model is mocked, the rules are not."""

    SCRIPT = "2022年，中国人口六十一年来第一次减少了85万人。"

    def project(self, text: str = SCRIPT, language: str = "zh"):
        seg = proj.Segment(id="a", text=text, clips=[])
        return proj.Project(title="t", segments=[seg], root=Path("."), language=language)

    def answer(self, data: dict, project=None):
        import json
        from unittest import mock
        from vidforge import llm
        with mock.patch.object(llm, "chat", return_value=json.dumps(data, ensure_ascii=False)) as chat:
            out = platforms.suggest_text(project or self.project())
        return out, chat

    def test_chinese_numerals_in_the_script_are_numbers_a_title_may_use(self):
        self.assertEqual(platforms.cn_number("六十一"), 61)
        self.assertEqual(platforms.cn_number("一九九零"), 1990)
        self.assertEqual(platforms.cn_number("八十五万"), 850000)
        self.assertIsNone(platforms.cn_number("百分之五"))
        self.assertTrue({"2022", "61", "85"} <= platforms.script_numbers(self.SCRIPT))
        # a unit standing alone is no number: "85 万" used to bring a 0 with it and look invented
        self.assertEqual(platforms.script_numbers("少了 85 万人"), {"85"})
        self.assertEqual(platforms.script_numbers("零下五度"), {"0", "5"})

    def test_a_title_with_a_number_the_script_never_said_is_dropped(self):
        out, _ = self.answer({"titles": ["中国人口61年来首次减少", "人口减少了100万？", "2022年发生了什么", "人口少了三千万"],
                              "description": "d", "tags": ["人口"]})
        self.assertEqual(out["titles"], ["中国人口61年来首次减少", "2022年发生了什么"])
        self.assertEqual(out["dropped"], ["人口减少了100万？", "人口少了三千万"])

    def test_decoration_is_stripped_and_long_tags_are_left_out_not_cut(self):
        out, _ = self.answer({"titles": ["《人口》🔥 减少了"], "description": "d",
                              "tags": ["#人口", "人口 变化", "中国人口六十一年来第一次减少", "人口"]})
        self.assertEqual(out["titles"], ["人口 减少了"])
        self.assertEqual(out["tags"], ["人口", "人口变化"])

    def test_the_prompt_is_in_the_projects_language(self):
        _, chat = self.answer({"titles": [], "description": "", "tags": []})
        self.assertIn("只能用稿子里出现过的数字", chat.call_args.args[0])
        _, chat = self.answer({"titles": [], "description": "", "tags": []},
                              self.project("In 1815 a volcano erupted.", "en"))
        self.assertIn("never invent", chat.call_args.args[0])

    def test_without_a_script_there_is_nothing_to_title(self):
        with self.assertRaisesRegex(platforms.PlatformError, "脚本"):
            platforms.suggest_text(self.project(""))


if __name__ == "__main__":
    unittest.main()
