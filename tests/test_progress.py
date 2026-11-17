"""进度条: a thin bar filling across the video — along the bottom when wide, the top when upright."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, project as proj, render


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg")
        return True
    except ffmpeg.FfmpegError:
        return False


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Bar(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def render(self, w: int, h: int, **kw) -> Path:
        merged = self.td / f"m{w}x{h}.mp4"
        ffmpeg.run(["-y", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}:r=30:d=4", "-f", "lavfi", "-i", "sine=d=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(merged)])
        p = proj.Project(title="t", segments=[], root=self.td, width=w, height=h, quality="draft", encoder="libx264",
                         progress_bar=True, **kw)
        out = self.td / f"f{w}x{h}.mp4"
        render.finalize(p, merged, None, 4.0, out)
        self.assertAlmostEqual(ffmpeg.duration(out), 4.0, delta=0.1)
        return out

    def pixel(self, video: Path, t: float, x: int, y: int):
        from PIL import Image
        f = self.td / "px.png"
        ffmpeg.run(["-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(f)])
        with Image.open(f) as im:
            return im.convert("RGB").getpixel((x, y))

    def is_bar(self, rgb) -> bool:
        r, g, b = rgb
        return abs(r - g) > 40 or abs(g - b) > 40          # coloured, where the frame is grey

    def test_it_fills_in_step_with_the_clock_along_the_bottom_of_a_wide_video(self):
        out = self.render(320, 180)
        self.assertTrue(self.is_bar(self.pixel(out, 2.0, 60, 178)), "a quarter in: reached")
        self.assertFalse(self.is_bar(self.pixel(out, 2.0, 260, 178)), "three quarters: not yet")
        self.assertFalse(self.is_bar(self.pixel(out, 2.0, 60, 90)), "only a thin strip")

    def test_an_upright_video_carries_it_at_the_top(self):
        out = self.render(180, 320, theme={"palette": "mint"})
        self.assertTrue(self.is_bar(self.pixel(out, 3.0, 30, 2)))
        self.assertFalse(self.is_bar(self.pixel(out, 3.0, 30, 318)))


if __name__ == "__main__":
    unittest.main()
