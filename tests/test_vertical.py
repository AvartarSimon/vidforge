"""Vertical cuts: ranges, re-timed subtitles, reframe filters, source choice."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vidforge.video import VideoToolError
from vidforge.video import vertical as v

TIMELINE = [
    {"id": "__intro__", "label": None, "start": 0.0, "end": 1.2},
    {"id": "seg1", "label": "开场", "start": 1.2, "end": 20.0},
    {"id": "seg2", "label": "数据", "start": 20.0, "end": 41.0},
    {"id": "seg3", "label": "结论", "start": 41.0, "end": 50.0},
]

SRT = """1
00:00:19,000 --> 00:00:21,000
横跨切点的一句

2
00:00:25,500 --> 00:00:27,000
正中间的一句

3
00:00:45,000 --> 00:00:46,000
切点之后，不该出现
"""


class Ranges(unittest.TestCase):
    def test_a_single_segment(self):
        cut = v.range_from_segments(TIMELINE, ["seg2"])
        self.assertEqual((cut.start, cut.end), (20.0, 41.0))
        self.assertAlmostEqual(cut.seconds, 21.0)

    def test_neighbouring_segments_merge_into_one_span(self):
        cut = v.range_from_segments(TIMELINE, ["seg2", "seg3"])
        self.assertEqual((cut.start, cut.end), (20.0, 50.0))

    def test_an_unknown_id_lists_the_real_ones_without_the_brand_clips(self):
        with self.assertRaises(VideoToolError) as cm:
            v.range_from_segments(TIMELINE, ["nope"])
        msg = str(cm.exception)
        self.assertIn("seg1", msg)
        self.assertNotIn("__intro__", msg)

    def test_times_are_accepted_in_the_forms_people_actually_type(self):
        self.assertEqual(v._parse_time(90), 90.0)
        self.assertEqual(v._parse_time("90"), 90.0)
        self.assertEqual(v._parse_time("1:30"), 90.0)
        self.assertEqual(v._parse_time("00:01:30.5"), 90.5)
        with self.assertRaises(VideoToolError):
            v._parse_time("一分半")


class Subtitles(unittest.TestCase):
    def cues(self, cut):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "final.srt"
            f.write_text(SRT, encoding="utf-8")
            return v.subtitles_for(f, cut)

    def test_cues_are_retimed_so_the_clip_starts_at_zero(self):
        cues = self.cues(v.Cut(20.0, 41.0))
        self.assertAlmostEqual(cues[1][0], 5.5)        # 25.5s in the long video
        self.assertEqual(cues[1][2], "正中间的一句")

    def test_a_cue_straddling_the_cut_is_clipped_not_dropped(self):
        cues = self.cues(v.Cut(20.0, 41.0))
        self.assertEqual(cues[0][0], 0.0)              # clamped to the start of the clip
        self.assertEqual(cues[0][2], "横跨切点的一句")

    def test_cues_outside_the_cut_are_left_out(self):
        texts = [c[2] for c in self.cues(v.Cut(20.0, 41.0))]
        self.assertNotIn("切点之后，不该出现", texts)

    def test_no_srt_is_not_an_error(self):
        self.assertEqual(v.subtitles_for(Path("nope.srt"), v.Cut(0, 10)), [])


class Reframe(unittest.TestCase):
    def test_crop_fills_the_frame_and_blur_keeps_the_whole_picture(self):
        crop = v.reframe_filter("crop", 1080, 1920)
        blur = v.reframe_filter("blur", 1080, 1920)
        self.assertIn("force_original_aspect_ratio=increase", crop)
        self.assertIn("boxblur", blur)
        self.assertIn("force_original_aspect_ratio=decrease", blur)   # nothing cropped off

    def test_an_unknown_mode_names_the_real_ones(self):
        with self.assertRaises(VideoToolError) as cm:
            v.reframe_filter("zoom", 1080, 1920)
        self.assertIn("blur", str(cm.exception))

    def test_every_offered_ratio_is_portrait_or_square(self):
        for w, h in v.SIZE.values():
            self.assertLessEqual(w, h)


class SourceChoice(unittest.TestCase):
    def test_a_project_that_burns_subtitles_is_cut_from_the_unburned_copy(self):
        with tempfile.TemporaryDirectory() as td:
            bd = Path(td)
            (bd / "final.mp4").write_bytes(b"x")
            (bd / "merged.mp4").write_bytes(b"x")
            self.assertEqual(v.pick_source(bd, True).name, "merged.mp4")
            self.assertEqual(v.pick_source(bd, False).name, "final.mp4")

    def test_nothing_rendered_yet_says_so(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(VideoToolError):
                v.pick_source(Path(td), False)


class Suggestions(unittest.TestCase):
    def test_brand_clips_are_never_offered_as_a_short(self):
        ids = [i for c in v.suggest(TIMELINE) for i in c["ids"]]
        self.assertNotIn("__intro__", ids)

    def test_nothing_longer_than_the_limit_is_offered(self):
        for c in v.suggest(TIMELINE, seconds=30):
            self.assertLessEqual(c["seconds"], 30)

    def test_pairs_are_offered_when_one_segment_is_short(self):
        labels = [c["ids"] for c in v.suggest(TIMELINE, seconds=60)]
        self.assertIn(["seg2", "seg3"], labels)


if __name__ == "__main__":
    unittest.main()
