"""Picture-in-picture overlays: schema + real ffmpeg composite."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, project as proj, render
from vidforge.project import Clip, Overlay, Segment


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg"); return True
    except ffmpeg.FfmpegError:
        return False


class Schema(unittest.TestCase):
    def test_overlays_and_presenter_parse(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x"); (root / "v.mp4").write_bytes(b"x")
            (root / "project.json").write_text(json.dumps({"title": "t", "presenter": {"provider": "host", "where": "first_last", "size": 0.25},
                "segments": [{"id": "s", "text": "a", "image": "a.jpg", "presenter": False,
                              "overlays": [{"image": "a.jpg", "at": 2, "duration": 5, "position": "top-left", "size": 0.35},
                                           {"video": "v.mp4", "in": 1, "out": 4, "position": "0.1,0.8", "animate": "fade"},
                                           {"avatar": True}]}]}), encoding="utf-8")
            p = proj.load(root)
            s = p.segments[0]
            self.assertEqual(len(s.overlays), 3)
            self.assertEqual((s.overlays[0].at, s.overlays[0].duration, s.overlays[0].position), (2, 5, "top-left"))
            self.assertEqual(s.overlays[1].out, 4)
            self.assertTrue(s.overlays[2].avatar)
            self.assertIs(s.presenter, False)
            self.assertEqual((p.presenter.where, p.presenter.size), ("first_last", 0.25))
            (root / "project.json").write_text(json.dumps({"title": "t", "segments": [{"id": "s", "text": "a", "image": "a.jpg",
                "overlays": [{"image": "a.jpg", "position": "nowhere"}]}]}), encoding="utf-8")
            with self.assertRaises(proj.ProjectError):
                proj.load(root)


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Composite(unittest.TestCase):
    def test_still_and_looping_video_overlays_keep_length(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bg, pip_img, pip_vid, audio, out = root / "bg.png", root / "pip.png", root / "pip.mp4", root / "n.mp3", root / "seg.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=navy:s=640x360", "-frames:v", "1", str(bg)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "color=c=orange:s=320x180", "-frames:v", "1", str(pip_img)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30", "-t", "1.5", "-pix_fmt", "yuv420p", str(pip_vid)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "6", str(audio)])
            p = proj.Project(title="t", segments=[], root=root, width=320, height=180, fps=30, quality="draft")
            seg = Segment(id="o", text="x", pause_after=0, clips=[Clip(image=bg)], overlays=[
                Overlay(image=pip_img, at=1.0, duration=3.0, position="top-left", size=0.3, animate="slide"),
                Overlay(video=pip_vid, at=2.0, in_=0.5, position="bottom-right", size=0.4, animate="fade"),   # 1 s slice, loops to the end
            ])
            dur = render.render_segment(p, seg, audio, out, encoder="libx264")
            self.assertAlmostEqual(ffmpeg.duration(out), dur, delta=0.15)
            self.assertTrue((root / "seg_parts" / "overlaid.mp4").exists())
            # pixel check: at t=2.5 the top-left corner is orange-ish (still overlay), at t=0.5 it is navy
            def px(t):
                frame = root / f"f{t}.png"
                ffmpeg.run(["-y", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-vf", "crop=8:8:40:40", str(frame)])
                from PIL import Image
                return Image.open(frame).convert("RGB").getpixel((4, 4))
            r0, g0, b0 = px(0.5); r1, g1, b1 = px(2.5)
            self.assertGreater(b0, r0, "background navy before the overlay appears")
            self.assertGreater(r1, b1, "orange still visible while the overlay is on")


if __name__ == "__main__":
    unittest.main()
