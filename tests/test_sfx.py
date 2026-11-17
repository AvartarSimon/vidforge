"""转场音效: a synthesized sound at each segment hand-over, under the narration."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, project as proj, render, sfx


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


def _peak(path: Path, start: float, seconds: float) -> float:
    r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-ss", str(start), "-t", str(seconds), "-i", str(path),
                        "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"max_volume: (-?[\d.]+|-inf) dB", r.stderr)
    return float(m.group(1)) if m and m.group(1) != "-inf" else -99.0


class Setting(unittest.TestCase):
    def test_a_typo_fails_at_load_not_at_the_last_step_of_a_render(self):
        td = Path(tempfile.mkdtemp())
        try:
            (td / "a.jpg").write_bytes(b"x")
            raw = {"title": "t", "transition_sfx": "whosh", "segments": [{"id": "a", "text": "x", "image": "a.jpg"}]}
            (td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(proj.ProjectError, "whosh"):
                proj.load(td / "project.json")
            raw["transition_sfx"] = "tick"
            (td / "project.json").write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(proj.load(td / "project.json").transition_sfx, "tick")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_nothing_to_place_is_no_track(self):
        self.assertIsNone(sfx.track("whoosh", [], 5.0, Path("unused.wav")))
        self.assertIsNone(sfx.track("nope", [1.0], 5.0, Path("unused.wav")))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Mixed(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180:r=30:d=4", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.td / "merged.mp4")])

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_the_sound_lands_on_the_cut_and_nowhere_else(self):
        for kind in sfx.KINDS:
            track = sfx.track(kind, [2.0], 4.0, self.td / f"{kind}.wav")
            self.assertAlmostEqual(ffmpeg.duration(track), 4.0, delta=0.05)
            p = proj.Project(title="t", segments=[], root=self.td, width=320, height=180, quality="draft", encoder="libx264")
            out = self.td / f"final_{kind}.mp4"
            render.finalize(p, self.td / "merged.mp4", None, 4.0, out, sfx=track)
            self.assertAlmostEqual(ffmpeg.duration(out), 4.0, delta=0.1)
            self.assertGreater(_peak(out, 1.6, 0.6), -40, f"{kind}: heard at the cut")
            self.assertLess(_peak(out, 0.0, 1.2), -60, f"{kind}: silent away from it")
            self.assertLess(_peak(out, 1.6, 0.6), -15, f"{kind}: under the narration, not over it")


if __name__ == "__main__":
    unittest.main()
