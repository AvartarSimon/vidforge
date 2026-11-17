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


@unittest.skipUnless(_ff_available(), "ffmpeg not installed")
class BrandSplice(unittest.TestCase):
    """The channel opener / end card spliced onto the segments, then every overlay laid over it."""

    def test_the_end_card_is_matched_and_the_final_pass_finishes(self):
        # full-range yuvj420p on 1/90000 straight from Remotion, stream-copied after yuv420p segments,
        # deadlocked ffmpeg 9 in the final pass once the hook card, badge and progress bar were all on
        import subprocess
        import threading
        td = Path(tempfile.mkdtemp())
        ff = ffmpeg.find_binary("ffmpeg")

        def make(name, colour, seconds, extra):
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=360x640:r=30:d={seconds}",
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds), *extra, "-c:a", "aac",
                            str(td / name)], check=True)
        make("seg.mp4", "gray", 6, ["-c:v", "libx264", "-pix_fmt", "yuv420p"])
        make("card.mp4", "black", 3, ["-c:v", "libx264", "-pix_fmt", "yuvj420p", "-color_range", "pc", "-video_track_timescale", "90000"])
        p = proj.Project(title="t", segments=[], root=td, width=360, height=640, quality="draft", encoder="libx264",
                         theme={"palette": "mint", "badge": "S01"}, progress_bar=True, hook=proj.HookCard("开场大字", 2))
        card = render.match_clip(td / "card.mp4", td / "seg.mp4", p, "libx264", td / "card_m.mp4")

        def probe(f, what):
            return subprocess.run([ffmpeg.find_binary("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   f"stream={what}", "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(probe(card, "pix_fmt"), "yuv420p")
        self.assertEqual(probe(card, "time_base"), probe(td / "seg.mp4", "time_base"))
        render.concat([td / "seg.mp4", card], td / "merged.mp4")
        done = []
        t = threading.Thread(target=lambda: done.append(render.finalize(p, td / "merged.mp4", None, 9.0, td / "final.mp4")), daemon=True)
        t.start()
        t.join(60)
        self.assertFalse(t.is_alive(), "the final pass must not hang")
        self.assertAlmostEqual(ffmpeg.duration(td / "final.mp4"), 9.0, delta=0.2)


@unittest.skipUnless(_ff_available(), "ffmpeg not installed")
class ColourRange(unittest.TestCase):
    def test_a_full_range_photo_becomes_a_standard_range_clip(self):
        # JPEGs and Remotion renders are full range; spliced beside video segments they changed the
        # pixel format mid-file and the final pass hung
        import subprocess
        td = Path(tempfile.mkdtemp())
        ff = ffmpeg.find_binary("ffmpeg")
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180,format=yuvj420p",
                        "-frames:v", "1", str(td / "w.jpg")], check=True)
        p = proj.Project(title="t", segments=[], root=td, width=320, height=180, quality="draft", encoder="libx264")
        out = td / "c.mp4"
        render.render_clip(p, render.PlannedClip(Clip(image=td / "w.jpg", motion="none"), 1.0), out, "libx264")
        probe = subprocess.run([ffmpeg.find_binary("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=pix_fmt,color_range", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(probe, "yuv420p,tv")
        y = subprocess.run([ff, "-v", "error", "-i", str(out), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                           capture_output=True).stdout[160 * 90 * 0 + 5]
        self.assertLessEqual(y, 236, "converted to the standard range, not just relabelled")
