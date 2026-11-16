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


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Export(unittest.TestCase):
    def test_landscape_final_becomes_each_shape(self):
        td = Path(tempfile.mkdtemp())
        try:
            src = td / "final.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "testsrc=s=640x360:r=30:d=2", "-f", "lavfi", "-i", "sine=d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)])
            p = proj.Project(title="t", segments=[], root=td)
            for pid, size in (("douyin", (1080, 1920)), ("youtube", (1920, 1080))):
                r = platforms.export(p, src, td / "out", pid, log=lambda *_: None)
                self.assertEqual(ffmpeg.video_size(r["path"]), size, pid)
                self.assertAlmostEqual(r["seconds"], 2.0, delta=0.15)
                self.assertTrue(Path(r["text"]).is_file())
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
