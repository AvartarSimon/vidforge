"""开场大字: the hook card is on screen for its seconds, over the picture, and then gone."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, hook, project as proj, render


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Card(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_a_long_hook_shrinks_rather_than_running_to_a_fourth_line(self):
        from PIL import Image
        short = hook.card_png("人口第一次减少", self.td / "a.png", width=1080, height=1920)
        long = hook.card_png("为什么每天睡九个小时还是这么累而且越睡越困到底是哪里出了问题呢我们来看看为什么", self.td / "b.png",
                             width=1080, height=1920)
        with Image.open(short) as a, Image.open(long) as b:
            self.assertLess(a.height, b.height)
            self.assertLess(b.height, 1920 * 0.25, "three lines at most")
            self.assertLessEqual(b.width, 1080 * 0.9)

    def test_it_sits_between_the_presenter_window_and_the_subtitles(self):
        from vidforge import theme
        from vidforge.subtitles import SCRIPT_LINES
        x, y = hook.position(1080, 1920, 700, 250)
        self.assertEqual(x, 190)
        self.assertGreater(y / 1920, theme.MARGIN_TOP + theme.WINDOW_H)
        self.assertLess((y + 250) / 1920, 1 - theme.SUB_LIFT - 12 / SCRIPT_LINES)

    def test_over_a_full_screen_face_it_goes_up_out_of_the_way(self):
        # in the middle of the frame it sat on the presenter's eyes and nose
        x, y = hook.position(1080, 1920, 700, 250, over_face=True)
        self.assertLess((y + 250) / 1920, 0.30)
        self.assertGreater(y / 1920, 0.10, "below the series badge")

    def test_the_project_reads_it_and_keeps_seconds_sensible(self):
        raw = {"title": "t", "hook": {"text": "  人口第一次减少 ", "seconds": 30},
               "segments": [{"id": "a", "text": "x", "image": "a.jpg"}]}
        (self.td / "a.jpg").write_bytes(b"x")
        (self.td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
        p = proj.load(self.td / "project.json")
        self.assertEqual((p.hook.text, p.hook.seconds), ("人口第一次减少", 6.0))
        raw.pop("hook")
        (self.td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
        self.assertEqual(proj.load(self.td / "project.json").hook.text, "", "off unless written")


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Burned(unittest.TestCase):
    def test_the_card_shows_from_the_narration_start_for_its_seconds(self):
        td = Path(tempfile.mkdtemp())
        try:
            merged = td / "merged.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=0x6080a0:s=640x360:r=30:d=5", "-f", "lavfi", "-i", "sine=d=5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(merged)])
            p = proj.Project(title="t", segments=[], root=td, width=640, height=360, quality="draft", encoder="libx264",
                             hook=proj.HookCard("人口第一次减少", 2.0))
            out = td / "final.mp4"
            render.finalize(p, merged, None, 5.0, out, hook_at=1.0)
            self.assertAlmostEqual(ffmpeg.duration(out), 5.0, delta=0.15)
            from PIL import Image
            with Image.open(td / "hook.png") as card:
                cw, ch = card.size
            x, y = hook.position(640, 360, cw, ch)

            def pixel(t: float):
                f = td / f"f{t}.png"
                ffmpeg.run(["-y", "-ss", str(t), "-i", str(out), "-frames:v", "1", str(f)])
                with Image.open(f) as im:
                    return im.convert("RGB").getpixel((x + 6, y + ch // 2))

            before, during, after = pixel(0.5), pixel(2.0), pixel(4.0)
            self.assertGreater(sum(before), 300, "the opener is left alone")
            self.assertLess(sum(during), 200, "the dark card is over the picture")
            self.assertGreater(sum(after), 300, "and gone after its seconds")
        finally:
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
