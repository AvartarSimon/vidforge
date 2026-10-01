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

    def test_silent_narration_does_not_break_loudnorm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            img, audio, out = root / "a.png", root / "n.mp3", root / "seg.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=red:s=800x450", "-frames:v", "1", str(img)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", "-c:a", "libmp3lame", str(audio)])
            self.assertTrue(render.audio_is_silent(audio))
            p = proj.Project(title="t", segments=[], root=root, width=320, height=180, fps=30, quality="draft")
            dur = render.render_segment(p, Segment(id="q", text="x", pause_after=0, clips=[Clip(image=img)]), audio, out, encoder="libx264")
            self.assertAlmostEqual(ffmpeg.duration(out), dur, delta=0.15)

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


class EditingLook(unittest.TestCase):
    """The grade and the transitions: strings only — rendering them is the e2e test's job."""

    def proj(self, **kw):
        from vidforge.project import Project
        return Project(root=Path("."), title="t", segments=[], **kw)

    def test_look_is_off_by_default(self):
        from vidforge.render import look_filter
        self.assertEqual(look_filter(self.proj()), "")
        self.assertEqual(look_filter(self.proj(look="none")), "")

    def test_each_look_produces_a_filter(self):
        from vidforge.render import LOOKS, look_filter
        for name in LOOKS:
            self.assertTrue(look_filter(self.proj(look=name)), name)

    def test_strength_scales_the_grade(self):
        from vidforge.render import look_filter
        weak = look_filter(self.proj(look="warm", look_strength=0.2))
        strong = look_filter(self.proj(look="warm", look_strength=2.0))
        self.assertNotEqual(weak, strong)
        self.assertIn("temperature=6", weak)        # barely moved off 6500K
        self.assertIn("temperature=4", strong)      # clearly warm

    def test_strength_is_clamped_so_a_typo_cannot_wreck_the_picture(self):
        from vidforge.render import look_filter
        self.assertEqual(look_filter(self.proj(look="warm", look_strength=99)),
                         look_filter(self.proj(look="warm", look_strength=2.0)))

    def test_an_unknown_look_names_the_real_ones(self):
        from vidforge.render import look_filter
        with self.assertRaises(ValueError) as cm:
            look_filter(self.proj(look="sparkle"))
        self.assertIn("warm", str(cm.exception))

    def test_only_transitions_that_suit_an_explainer_are_offered(self):
        from vidforge.render import TRANSITIONS
        self.assertIn("fade", TRANSITIONS)
        self.assertIn("fadeblack", TRANSITIONS)
        for silly in ("pixelize", "squeezeh", "hlslice"):
            self.assertNotIn(silly, TRANSITIONS)

    def test_boundary_fade_never_changes_a_segment_length(self):
        """The whole reason it is a fade and not a crossfade: timings must stay exact."""
        from unittest import mock
        from vidforge import render
        calls = []
        with mock.patch.object(render.ffmpeg, "run", side_effect=lambda a: calls.append(a)):
            render._boundary_fade(self.proj(segment_fade=0.5), Path("in.mp4"), 10.0,
                                  Path("out.mp4"), "libx264")
        args = calls[0]
        self.assertIn("-t", args)
        self.assertEqual(args[args.index("-t") + 1], "10.000")
        chain = args[args.index("-filter_complex") + 1]
        self.assertIn("fade=t=in:st=0:d=0.500", chain)
        self.assertIn("fade=t=out:st=9.500:d=0.500", chain)

    def test_boundary_fade_is_capped_on_a_very_short_segment(self):
        from unittest import mock
        from vidforge import render
        calls = []
        with mock.patch.object(render.ffmpeg, "run", side_effect=lambda a: calls.append(a)):
            render._boundary_fade(self.proj(segment_fade=5.0), Path("in.mp4"), 1.0,
                                  Path("out.mp4"), "libx264")
        chain = calls[0][calls[0].index("-filter_complex") + 1]
        self.assertIn("d=0.250", chain)        # a quarter of the segment, not all of it
