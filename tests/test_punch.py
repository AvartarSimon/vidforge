"""口播推近: a talking-head take alternates wide and tight shots at sentence breaks."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, render
from vidforge.project import Clip, Project, Segment
from vidforge.tts import Word


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Windows(unittest.TestCase):
    def test_every_other_sentence_is_tight(self):
        self.assertEqual(render.punch_windows([3.0, 6.0, 9.0], 12.0), [(3.0, 6.0), (9.0, 12.0)])

    def test_breaks_too_close_together_or_to_the_end_are_skipped(self):
        self.assertEqual(render.punch_windows([0.5, 3.0, 3.8, 11.5], 12.0), [(3.0, 12.0)])

    def test_a_long_take_without_breaks_still_changes_shot(self):
        self.assertEqual(render.punch_windows([], 13.0), [(4.0, 8.0)], "a cut 1 s before the end is no shot")
        self.assertEqual(render.punch_windows([], 5.0), [], "a short take stays one shot")

    def test_only_takes_of_the_presenter_count(self):
        self.assertTrue(render.is_talking_head(Clip(video=Path("/p/assets/takes/a_1.mp4"))))
        self.assertTrue(render.is_talking_head(Clip(video=Path("/u/.vidforge/me/intro.mp4"))))
        self.assertTrue(render.is_talking_head(Clip(video=Path("/p/x.mp4"), me={"tags": ["intro"]})))
        self.assertFalse(render.is_talking_head(Clip(video=Path("/p/assets/pexels_123.mp4"))))
        self.assertFalse(render.is_talking_head(Clip(image=Path("/p/assets/takes/still.jpg"))))

    def test_sentence_breaks_fall_in_the_pause(self):
        from vidforge import pipeline
        ws = [Word("一", 0.0, 0.5), Word("二", 0.5, 0.5, break_after=True), Word("三", 1.4, 0.5)]
        self.assertEqual(pipeline._sentence_breaks(ws), [1.2])


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Rendered(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "takes").mkdir()
        # a red band down the left edge: the tight shot crops it out of the frame
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=6", "-vf",
                    "drawbox=x=0:y=0:w=12:h=180:color=red:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(self.td / "takes" / "a_1.mp4")])

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def edge(self, video: Path, t: float):
        from PIL import Image
        f = self.td / f"f{t}.png"
        ffmpeg.run(["-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(f)])
        with Image.open(f) as im:
            return im.convert("RGB").getpixel((3, 90))

    def test_the_tight_shot_shows_only_inside_its_window(self):
        p = Project(title="t", segments=[], root=self.td, width=320, height=180, quality="draft",
                    encoder="libx264", punch_in=True)
        pc = render.PlannedClip(Clip(video=self.td / "takes" / "a_1.mp4"), 6.0, punch=[(2.0, 4.0)])
        out = self.td / "out.mp4"
        render.render_clip(p, pc, out, "libx264")
        self.assertAlmostEqual(ffmpeg.duration(out), 6.0, delta=0.1)
        wide, tight, back = self.edge(out, 1.0), self.edge(out, 3.0), self.edge(out, 5.0)
        self.assertGreater(wide[0], 150, "wide: the red edge is in frame")
        self.assertLess(tight[0], 100, "tight: cropped out")
        self.assertGreater(back[0], 150)

    def test_the_segment_hands_its_breaks_to_takes_only_when_asked(self):
        seg = Segment(id="s", text="x", clips=[Clip(video=self.td / "takes" / "a_1.mp4")])
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=d=6", str(self.td / "n.m4a")])
        for on in (True, False):
            p = Project(title="t", segments=[seg], root=self.td, width=320, height=180, quality="draft",
                        encoder="libx264", punch_in=on, normalize_audio=False)
            out = self.td / f"seg{on}.mp4"
            render.render_segment(p, seg, self.td / "n.m4a", out, encoder="libx264", beats=[2.0, 4.0])
            self.assertEqual(self.edge(out, 3.0)[0] < 100, on)


if __name__ == "__main__":
    unittest.main()
