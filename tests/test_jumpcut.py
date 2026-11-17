"""智能剪口播: gaps out, rhythm kept, picture and sound cut together."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg
from vidforge.video import jumpcut


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


class Ranges(unittest.TestCase):
    def test_keep_is_the_complement_widened_and_merged(self):
        keep = jumpcut.keep_ranges(10.0, [(2.0, 4.0), (4.1, 6.0), (9.5, 10.0)], pad=0.1)
        self.assertEqual(keep, [(0.0, 2.1), (3.9, 4.2), (5.9, 9.6)])

    def test_padding_that_closes_a_gap_merges_it(self):
        self.assertEqual(jumpcut.keep_ranges(5.0, [(2.0, 2.15)], pad=0.1), [(0.0, 5.0)])

    def test_all_quiet_keeps_nothing(self):
        self.assertEqual(jumpcut.keep_ranges(3.0, [(0.0, 3.0)]), [])


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Cut(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        # tone 1 s · silence 1.5 s · tone 1 s · silence 0.2 s · tone 1 s
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=f=440:d=1", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-f", "lavfi", "-i", "testsrc=s=320x240:r=30:d=4.7", "-filter_complex",
                    "[0:a]aresample=44100,asplit=3[t1][t2][t3];[1:a]atrim=0:1.5[s1];[1:a]atrim=0:0.2[s2];"
                    "[t1][s1][t2][s2][t3]concat=n=5:v=0:a=1[a]",
                    "-map", "2:v", "-map", "[a]", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(self.td / "take.mp4")])

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_long_gap_goes_short_gap_stays(self):
        p = jumpcut.plan(self.td / "take.mp4")
        self.assertEqual(len(p["keep"]), 2, "only the 1.5 s gap is cut; 0.2 s is speech rhythm")
        self.assertAlmostEqual(p["removed"], 1.5 - 2 * jumpcut.PAD, delta=0.08)

    def test_cut_file_has_the_planned_length_with_picture(self):
        r = jumpcut.cut(self.td / "take.mp4", self.td / "cut.mp4", log=lambda *_: None)
        out = self.td / "cut.mp4"
        self.assertAlmostEqual(ffmpeg.duration(out), r["kept"], delta=0.1)
        self.assertEqual(ffmpeg.video_size(out), (320, 240))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Fillers(unittest.TestCase):
    """嗯/呃: Whisper names them, the level meter places the cut."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        # speech 1 s · pause 0.3 · "嗯" 0.3 s · pause 0.3 · speech 1 s
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=f=440:d=1", "-f", "lavfi", "-i", "sine=f=220:d=0.3",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-filter_complex",
                    "[0:a]aresample=44100,asplit=2[t1][t2];[1:a]aresample=44100[f];"
                    "[2:a]atrim=0:0.3,asplit=2[s1][s2];[t1][s1][f][s2][t2]concat=n=5:v=0:a=1[a]",
                    "-map", "[a]", "-c:a", "aac", str(self.td / "take.m4a")])
        self.words = [("今天", 0.1, 0.9), ("嗯，", 1.2, 1.7), ("人口", 2.0, 2.8)]

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_only_pure_hesitations_count(self):
        for yes in ("嗯", "嗯，", "呃", "Um,", "uh", "hmm"):
            self.assertTrue(jumpcut.is_filler(yes), yes)
        for no in ("那个", "就是", "啊", "人口", "umbrella"):
            self.assertFalse(jumpcut.is_filler(no), no)

    def test_the_cut_follows_the_sound_not_whispers_loose_times(self):
        cuts, unsure = jumpcut.find_fillers(self.td / "take.m4a", words=self.words)
        self.assertEqual(unsure, 0)
        (a, b, w), = cuts
        self.assertEqual(w, "嗯")
        self.assertAlmostEqual(a, 1.3, delta=0.06)
        self.assertAlmostEqual(b, 1.6, delta=0.06)

    def test_a_filler_run_into_a_word_is_left_in(self):
        words = [("今天", 0.1, 0.5), ("嗯", 0.6, 0.9), ("人口", 2.0, 2.8)]
        cuts, unsure = jumpcut.find_fillers(self.td / "take.m4a", words=words)
        self.assertEqual((cuts, unsure), ([], 1), "same stretch of sound as 今天: cutting it would clip the word")

    def test_plan_removes_the_filler_and_keeps_both_sentences(self):
        from unittest import mock
        from vidforge import align
        with mock.patch.object(align, "available", return_value=True), \
                mock.patch.object(align, "transcribe", return_value=self.words) as heard:
            p = jumpcut.plan(self.td / "take.m4a", fillers=True, lang="zh-CN")
            jumpcut.plan(self.td / "take.m4a", fillers=True, lang="zh-CN", min_gap=0.2)
        self.assertEqual(heard.call_count, 1, "the sliders re-plan; Whisper listens once")
        self.assertEqual(heard.call_args.args[1], "zh")
        self.assertEqual(len(p["fillers"]), 1)
        self.assertEqual(len(p["keep"]), 2)
        self.assertLess(p["keep"][0][1], 1.35)
        self.assertGreater(p["keep"][1][0], 1.55)

    def test_without_whisper_it_says_what_to_install(self):
        from unittest import mock
        from vidforge import align
        from vidforge.video import VideoToolError
        with mock.patch.object(align, "available", return_value=False):
            with self.assertRaisesRegex(VideoToolError, "faster-whisper"):
                jumpcut.find_fillers(self.td / "take.m4a")


if __name__ == "__main__":
    unittest.main()
