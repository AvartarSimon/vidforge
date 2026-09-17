"""Footage library (me.py) + lip-sync stub (lipsync.py) + project/pipeline wiring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vidforge import ffmpeg, me as me_mod, pipeline, project as proj
from vidforge.project import Clip, Overlay


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg"); return True
    except ffmpeg.FfmpegError:
        return False


def _make_clip(path: Path, colour: str, seconds: float = 3.0, size: str = "320x180") -> None:
    ffmpeg.run(["-y", "-f", "lavfi", "-i", f"color=c={colour}:s={size}:d={seconds}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])


class Tags(unittest.TestCase):
    def test_tags_from_name(self):
        self.assertEqual(me_mod.tags_from_name("backyard_glasses_talking_01.mp4"), (["backyard", "glasses"], True))
        self.assertEqual(me_mod.tags_from_name("study-bluejacket-02.mov"), (["study", "bluejacket"], False))
        self.assertEqual(me_mod.tags_from_name("beach walk wide.mp4"), (["beach", "walk", "wide"], False))
        self.assertEqual(me_mod.tags_from_name("说话_书房.mp4"), (["书房"], True))


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Library(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        for name, colour in [("backyard_talking_01.mp4", "teal"), ("backyard_talking_02.mp4", "blue"),
                              ("study_silent.mp4", "green")]:
            _make_clip(self.td / name, colour)

    def test_scan_indexes_tags_and_duration(self):
        lib = me_mod.MeLibrary(self.td)
        items = {i["name"]: i for i in lib.scan()}
        self.assertEqual(set(items), {"backyard_talking_01.mp4", "backyard_talking_02.mp4", "study_silent.mp4"})
        self.assertEqual(items["backyard_talking_01.mp4"]["tags"], ["backyard"])
        self.assertTrue(items["backyard_talking_01.mp4"]["talking"])
        self.assertFalse(items["study_silent.mp4"]["talking"])
        self.assertAlmostEqual(items["study_silent.mp4"]["duration"], 3.0, delta=0.2)

    def test_pick_prefers_least_used_matching_tag(self):
        lib = me_mod.MeLibrary(self.td)
        lib.scan()
        lib.record_use(self.td / "backyard_talking_01.mp4")
        # both backyard takes match; 02 has fewer uses -> picked
        pick = lib.pick(["backyard"], talking=True)
        self.assertEqual(pick.name, "backyard_talking_02.mp4")
        # avoid set excludes it too -> falls back to the other one
        pick2 = lib.pick(["backyard"], talking=True, avoid={"backyard_talking_02.mp4"})
        self.assertEqual(pick2.name, "backyard_talking_01.mp4")
        # no talking clip tagged "study" with talking=False silent exists -> exact match
        self.assertEqual(lib.pick(["study"], talking=False).name, "study_silent.mp4")
        # tag nobody has -> falls back to "any" within the talking bucket
        self.assertIsNotNone(lib.pick(["nonexistent"], talking=True))
        # wrong talking bucket entirely -> falls back to any clip in that bucket, not cross-bucket
        self.assertIsNone(lib.pick(["nonexistent"], talking=True, avoid={"backyard_talking_01.mp4", "backyard_talking_02.mp4"}))

    def test_set_tags_persists_and_scan_keeps_manual_edits(self):
        lib = me_mod.MeLibrary(self.td)
        lib.scan()
        lib.set_tags("study_silent.mp4", ["office", "reading"], talking=False)
        lib2 = me_mod.MeLibrary(self.td)   # fresh instance reloads index.json from disk
        lib2.scan()
        item = next(i for i in lib2.items() if i["name"] == "study_silent.mp4")
        self.assertEqual(item["tags"], ["office", "reading"])


class Schema(unittest.TestCase):
    def test_clip_and_overlay_me_spec_parse(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.json").write_text(json.dumps({
                "title": "t", "lipsync": "musetalk",
                "segments": [{"id": "s", "text": "a",
                              "clips": [{"me": {"tags": ["backyard", "glasses"], "talking": True}}],
                              "overlays": [{"me": {"talking": False}, "position": "bottom-right"}]}],
            }), encoding="utf-8")
            p = proj.load(root)
            self.assertEqual(p.lipsync, "musetalk")
            clip = p.segments[0].clips[0]
            self.assertEqual(clip.me, {"tags": ["backyard", "glasses"], "talking": True})
            self.assertFalse(clip.needs_asset)      # a `me` clip is not an unresolved asset
            ov = p.segments[0].overlays[0]
            self.assertEqual(ov.me, {"tags": [], "talking": False})

    def test_clip_needs_exactly_one_visual_kind(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / "project.json").write_text(json.dumps({"title": "t", "segments": [
                {"id": "s", "text": "a", "clips": [{"image": "a.jpg", "me": {"talking": False}}]}]}), encoding="utf-8")
            with self.assertRaises(proj.ProjectError):
                proj.load(root)


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class EndToEnd(unittest.TestCase):
    def test_silent_take_builds_without_lipsync(self):
        """A `me` clip with talking=False needs no lipsync provider: the take is used muted,
        narration is dubbed over it just like any other video clip."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib_dir = root / "assets" / "me"
            lib_dir.mkdir(parents=True)
            _make_clip(lib_dir / "backyard_silent.mp4", "purple", seconds=5.0)
            (root / "project.json").write_text(json.dumps({
                "title": "t", "tts": {"provider": "silent"}, "quality": "draft",
                "width": 320, "height": 180, "fps": 24, "encoder": "libx264",
                "segments": [{"id": "s1", "text": "Hello from my backyard.",
                              "clips": [{"me": {"tags": ["backyard"], "talking": False}}]}],
            }), encoding="utf-8")
            p = proj.load(root)
            final = pipeline.build(p)
            self.assertTrue(final.exists())
            self.assertGreater(ffmpeg.duration(final), 0)
            # the library recorded the use
            lib = me_mod.MeLibrary(lib_dir)
            self.assertEqual(lib.items()[0]["uses"], 1)

    def test_talking_take_without_lipsync_provider_warns_but_still_builds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lib_dir = root / "assets" / "me"
            lib_dir.mkdir(parents=True)
            _make_clip(lib_dir / "study_talking.mp4", "orange", seconds=5.0)
            (root / "project.json").write_text(json.dumps({
                "title": "t", "tts": {"provider": "silent"}, "quality": "draft",
                "width": 320, "height": 180, "fps": 24, "encoder": "libx264", "lipsync": "none",
                "segments": [{"id": "s1", "text": "A quick word from my study.",
                              "clips": [{"me": {"tags": ["study"], "talking": True}}]}],
            }), encoding="utf-8")
            p = proj.load(root)
            logs: list[str] = []
            pipeline.set_log(logs.append)
            try:
                final = pipeline.build(p)
            finally:
                pipeline.set_log(None)
            self.assertTrue(final.exists())
            self.assertTrue(any("口型不会对上" in l for l in logs))
            self.assertFalse(p.youtube.disclosure.realistic_presenter)   # no lip-sync actually applied

    def test_empty_library_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "assets" / "me").mkdir(parents=True)
            (root / "project.json").write_text(json.dumps({
                "title": "t", "tts": {"provider": "silent"}, "quality": "draft",
                "segments": [{"id": "s1", "text": "x", "clips": [{"me": {"talking": False}}]}],
            }), encoding="utf-8")
            p = proj.load(root)
            with self.assertRaisesRegex(RuntimeError, "素材库为空"):
                pipeline.build(p)


if __name__ == "__main__":
    unittest.main()
