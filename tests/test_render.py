"""Clip planning (pure) and real-ffmpeg segment rendering with slices, loops and stills."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import ffmpeg, project as proj, render
from vidforge.project import Clip, Segment


def _ff_available() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg"); return True
    except ffmpeg.FfmpegError:
        return False


class Planning(unittest.TestCase):
    def test_flexible_images_share_the_remainder(self):
        seg = Segment(id="s", text="", clips=[Clip(video=Path("v"), in_=0, out=4), Clip(image=Path("a")), Clip(image=Path("b"))])
        plan = render.plan_clips(seg, 10)
        self.assertEqual([round(p.seconds, 2) for p in plan], [4, 3, 3])

    def test_too_long_shrinks_images_then_cuts_from_end(self):
        seg = Segment(id="s", text="", clips=[Clip(video=Path("v"), in_=0, out=8), Clip(image=Path("a"), duration=6)])
        plan = render.plan_clips(seg, 9)          # 14 s of clips for 9 s of narration
        self.assertEqual(round(sum(p.seconds for p in plan), 2), 9)
        self.assertEqual(round(plan[1].seconds, 2), 1.5, "fixed image kept at the minimum, video cut")
        seg2 = Segment(id="s", text="", clips=[Clip(video=Path("v"), in_=0, out=8), Clip(video=Path("w"), in_=0, out=8)])
        plan2 = render.plan_clips(seg2, 5)
        self.assertEqual([round(p.seconds, 2) for p in plan2], [5], "second clip dropped entirely")

    def test_too_short_extends_last_clip_and_flags_loop(self):
        with mock.patch("vidforge.ffmpeg.duration", return_value=3.0):
            seg = Segment(id="s", text="", clips=[Clip(image=Path("a"), duration=2), Clip(video=Path("v"))])
            plan = render.plan_clips(seg, 12)
        self.assertEqual([round(p.seconds, 2) for p in plan], [2, 10])
        self.assertTrue(plan[1].loop)
        self.assertFalse(plan[0].loop)

    def test_remotion_clip_gets_flexible_share(self):
        from vidforge.project import RemotionSpec
        seg = Segment(id="s", text="", clips=[Clip(remotion=RemotionSpec("TitleCard")), Clip(image=Path("a"), duration=4)])
        plan = render.plan_clips(seg, 10)
        self.assertEqual([round(p.seconds, 2) for p in plan], [6, 4])


@unittest.skipUnless(_ff_available(), "ffmpeg not installed")
class SegmentRender(unittest.TestCase):
    def test_slice_loop_and_still_join_to_the_narration_length(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, img, audio, out = root / "src.mp4", root / "a.png", root / "n.mp3", root / "seg.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-t", "6", "-pix_fmt", "yuv420p", str(src)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=blue:s=800x450", "-frames:v", "1", str(img)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "9", str(audio)])
            p = proj.Project(title="t", segments=[], root=root, width=320, height=180, fps=30, quality="draft", encoder="libx264")
            seg = Segment(id="v", text="x", pause_after=0.5, clips=[
                Clip(video=src, in_=2, out=4),          # 2 s slice
                Clip(video=src, in_=5),                 # 1 s left in the file -> must loop to fill
                Clip(image=img, motion="pan_right"),    # flexible still takes the rest
            ])
            dur = render.render_segment(p, seg, audio, out, encoder="libx264")
            self.assertAlmostEqual(dur, 9.5, places=2)
            self.assertAlmostEqual(ffmpeg.duration(out), 9.5, delta=0.15)
            parts = sorted((root / "seg_parts").glob("0*.mp4"))
            self.assertEqual(len(parts), 3)
            self.assertAlmostEqual(ffmpeg.duration(parts[0]), 2.0, delta=0.1)

    def test_crossfade_join_keeps_total_length(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img, audio, out = root / "a.png", root / "n.mp3", root / "seg.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=red:s=800x450", "-frames:v", "1", str(img)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "6", str(audio)])
            p = proj.Project(title="t", segments=[], root=root, width=320, height=180, fps=30, quality="draft", transition=0.5)
            seg = Segment(id="x", text="x", pause_after=0, clips=[Clip(image=img), Clip(image=img, motion="zoom_out")])
            dur = render.render_segment(p, seg, audio, out, encoder="libx264")
            self.assertAlmostEqual(ffmpeg.duration(out), dur, delta=0.15)


if __name__ == "__main__":
    unittest.main()
