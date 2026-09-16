"""Run: python -m unittest discover -s tests -v

No network, no API keys: ElevenLabs and Pexels HTTP calls are stubbed; ffmpeg is real.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import project as proj, subtitles
from vidforge.assets.pexels import Pexels
from vidforge.tts import Word, synthesize_cached
from vidforge.tts.elevenlabs import ElevenLabsProvider, alignment_to_words, rate_to_speed


def _alignment(text: str, step: float = 0.1) -> dict:
    chars = list(text)
    return {
        "characters": chars,
        "character_start_times_seconds": [i * step for i in range(len(chars))],
        "character_end_times_seconds": [(i + 1) * step for i in range(len(chars))],
    }


class ElevenLabsAlignment(unittest.TestCase):
    def test_latin_words_keep_punctuation_and_span(self):
        words = alignment_to_words(_alignment("In 1815, a volcano."))
        self.assertEqual([w.text for w in words], ["In", "1815,", "a", "volcano."])
        self.assertAlmostEqual(words[1].start, 0.3)
        self.assertAlmostEqual(words[1].end, 0.8)       # 5 chars * 0.1

    def test_cjk_one_word_per_glyph(self):
        words = alignment_to_words(_alignment("火山，欧洲"))
        self.assertEqual([w.text for w in words], ["火", "山", "，", "欧", "洲"])

    def test_restore_punctuation_marks_breaks_for_elevenlabs_words(self):
        text = "In 1815, a volcano. This is it."
        words = subtitles.restore_punctuation(alignment_to_words(_alignment(text)), text)
        self.assertTrue(words[3].break_after)            # "volcano."
        self.assertFalse(words[1].break_after)           # "1815," is a comma, not a break in Latin path
        cues = subtitles.build_cues(words, offset=0, max_chars=42)
        self.assertEqual([c.text for c in cues], ["In 1815, a volcano.", "This is it."])

    def test_rate_to_speed(self):
        self.assertEqual(rate_to_speed("+0%"), 1.0)
        self.assertEqual(rate_to_speed("-10%"), 0.9)
        self.assertEqual(rate_to_speed("+50%"), 1.2)     # clamped
        self.assertEqual(rate_to_speed("garbage"), 1.0)

    def test_synthesize_writes_audio_and_words_and_caches(self):
        prov = ElevenLabsProvider(rate="+0%")
        fake = {"audio_base64": "AAECAw==", "alignment": _alignment("Hi there.")}
        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(ElevenLabsProvider, "_request", return_value=fake) as req:
            out = Path(td) / "a.mp3"
            words = synthesize_cached(prov, "Hi there.", "JBFqnCBsd6RMkjVDRZzb", out)
            self.assertEqual([w.text for w in words], ["Hi", "there."])
            self.assertEqual(out.read_bytes(), bytes([0, 1, 2, 3]))
            self.assertEqual(req.call_count, 1)
            synthesize_cached(prov, "Hi there.", "JBFqnCBsd6RMkjVDRZzb", out)
            self.assertEqual(req.call_count, 1, "second call must hit the cache")
            # a different text -> new key -> new request
            synthesize_cached(prov, "Other.", "JBFqnCBsd6RMkjVDRZzb", out)
            self.assertEqual(req.call_count, 2)

    def test_voice_name_resolves_via_library(self):
        prov = ElevenLabsProvider()
        with mock.patch.object(ElevenLabsProvider, "_request",
                               return_value={"voices": [{"voice_id": "nPczCjzI2devNBz1zQrb", "name": "Brian"}]}):
            self.assertEqual(prov.resolve_voice("brian"), "nPczCjzI2devNBz1zQrb")
            self.assertEqual(prov.resolve_voice("JBFqnCBsd6RMkjVDRZzb"), "JBFqnCBsd6RMkjVDRZzb")
            with self.assertRaises(Exception):
                prov.resolve_voice("Nobody")


PHOTOS = [
    {"id": 1, "width": 1000, "height": 2000, "src": {"original": "u1o", "large2x": "u1l"}},  # portrait -> skip
    {"id": 2, "width": 4000, "height": 2000, "src": {"original": "u2o", "large2x": "u2l"}},
    {"id": 3, "width": 4000, "height": 2000, "src": {"original": "u3o", "large2x": "u3l"}},
]
VIDEOS = [
    {"id": 10, "width": 1920, "height": 1080, "duration": 5, "url": "v10", "user": {"name": "A"},
     "video_files": [{"file_type": "video/mp4", "width": 1280, "height": 720, "link": "l10a"},
                     {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "l10b"}]},
    {"id": 11, "width": 1920, "height": 1080, "duration": 30, "url": "v11", "user": {"name": "B"},
     "video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "l11a"},
                     {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "l11b"}]},
]


class PexelsSelection(unittest.TestCase):
    def test_pick_photo_skips_portrait_and_used(self):
        p, url = Pexels.pick_photo(PHOTOS, used={2}, width=1920)
        self.assertEqual((p["id"], url), (3, "u3o"))          # frame 1920 > 1880 -> original
        p, url = Pexels.pick_photo(PHOTOS, used=set(), width=1280)
        self.assertEqual((p["id"], url), (2, "u2l"))          # small frame -> large2x

    def test_pick_video_prefers_long_enough_and_smallest_sufficient_width(self):
        v, f = Pexels.pick_video(VIDEOS, used=set(), width=1920, min_duration=12)
        self.assertEqual((v["id"], f["width"]), (11, 1920))
        v, f = Pexels.pick_video(VIDEOS, used={11}, width=1920, min_duration=12)
        self.assertEqual((v["id"], f["width"]), (10, 3840), "fallback: too short, but widest >= frame")

    def test_photo_flow_downloads_indexes_and_reuses(self):
        with tempfile.TemporaryDirectory() as td:
            px = Pexels(Path(td))
            with mock.patch.object(Pexels, "_get", return_value={"photos": PHOTOS}) as get, \
                    mock.patch.object(Pexels, "_download",
                                      side_effect=lambda url, dest: (dest.write_bytes(b"x"), dest)[1]):
                a = px.photo("volcano", width=1920)
                b = px.photo("volcano", width=1920)
                self.assertEqual(a, b)
                self.assertEqual(get.call_count, 1, "same spec must come from the index")
                c = px.photo("lava", width=1920)
                self.assertNotEqual(a, c, "second query must not reuse the same photo id")
            px.save()
            idx = json.loads((Path(td) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(idx["used_ids"]), [2, 3])


class ProjectAssetSpecs(unittest.TestCase):
    def test_pexels_spec_is_deferred_and_local_path_is_checked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / "project.json").write_text(json.dumps({
                "title": "t", "tts": {"provider": "elevenlabs", "model": "eleven_flash_v2_5"},
                "segments": [
                    {"id": "s1", "text": "a", "image": "a.jpg"},
                    {"id": "s2", "text": "b", "image": "pexels:volcano"},
                    {"id": "s3", "text": "c", "video": "pexels:lava flow"},
                ]}), encoding="utf-8")
            p = proj.load(root)
            self.assertEqual(p.tts.model, "eleven_flash_v2_5")
            self.assertFalse(p.segments[0].needs_asset)
            self.assertTrue(p.segments[1].needs_asset)
            self.assertEqual(p.segments[2].source_kind, "video")
            (root / "project.json").write_text(json.dumps({
                "title": "t", "segments": [{"id": "s1", "text": "a", "image": "missing.jpg"}]}), encoding="utf-8")
            with self.assertRaises(proj.ProjectError):
                proj.load(root)


class RemotionSpecs(unittest.TestCase):
    def test_remotion_segment_parses_and_needs_no_asset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.json").write_text(json.dumps({"title": "t", "segments": [
                {"id": "tl", "text": "a", "remotion": {"composition": "Timeline", "props": {"events": []}}}]}),
                encoding="utf-8")
            p = proj.load(root)
            self.assertEqual(p.segments[0].remotion.composition, "Timeline")
            self.assertFalse(p.segments[0].needs_asset)
            (root / "project.json").write_text(json.dumps({"title": "t", "segments": [
                {"id": "x", "text": "a", "image": "a.jpg", "remotion": {"composition": "TitleCard"}}]}), encoding="utf-8")
            with self.assertRaises(proj.ProjectError):
                proj.load(root)

    def test_render_uses_cache_key_from_props(self):
        from vidforge import remotion
        with tempfile.TemporaryDirectory() as td, mock.patch.object(remotion, "_remotion_cli", return_value=["x"]),                 mock.patch("subprocess.run") as run:
            def fake_run(cmd, **kw):
                Path(cmd[4]).write_bytes(b"v")   # ["remotion", "render", entry, composition, out, ...]
                return mock.Mock(returncode=0, stderr="", stdout="")
            run.side_effect = fake_run
            a = remotion.render("TitleCard", {"title": "A"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            b = remotion.render("TitleCard", {"title": "A"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            c = remotion.render("TitleCard", {"title": "B"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            self.assertEqual(a, b)
            self.assertNotEqual(a, c)
            self.assertEqual(run.call_count, 2)
            props = json.loads(a.with_suffix(".props.json").read_text(encoding="utf-8"))
            self.assertEqual(props["durationInFrames"], 60)
            with self.assertRaises(remotion.RemotionError):
                remotion.render("Nope", {}, duration=1, fps=30, width=1, height=1, out_dir=Path(td))


class VideoSegmentRender(unittest.TestCase):
    """Real ffmpeg: a 2 s test-pattern clip must be looped to cover a 5 s narration."""

    def test_video_background_is_looped_and_trimmed(self):
        from vidforge import ffmpeg, render
        try:
            ffmpeg.find_binary("ffmpeg")
        except ffmpeg.FfmpegError:
            self.skipTest("ffmpeg not installed")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clip, audio, out = root / "bg.mp4", root / "n.mp3", root / "out.mp4"
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-t", "2",
                        "-pix_fmt", "yuv420p", str(clip)])
            ffmpeg.run(["-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "5", str(audio)])
            p = proj.Project(title="t", segments=[], root=root, width=320, height=180, fps=30)
            seg = proj.Segment(id="v", text="x", video=clip, pause_after=0.5)
            dur = render.render_segment(p, seg, audio, out)
            self.assertAlmostEqual(dur, 5.5, places=1)
            self.assertAlmostEqual(ffmpeg.duration(out), 5.5, delta=0.15)


if __name__ == "__main__":
    unittest.main()
