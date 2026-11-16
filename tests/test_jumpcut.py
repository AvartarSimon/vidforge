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


if __name__ == "__main__":
    unittest.main()
