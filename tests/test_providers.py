"""Run: python -m unittest discover -s tests -v

No network, no API keys: ElevenLabs / Pexels / Pixabay / Commons HTTP calls are stubbed; ffmpeg is real.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import project as proj, subtitles
from vidforge.assets import Candidate, Library, pexels, wikimedia
from vidforge.tts import synthesize_cached
from vidforge.tts.elevenlabs import ElevenLabsProvider, alignment_to_words, rate_to_speed


def _alignment(text: str, step: float = 0.1) -> dict:
    chars = list(text)
    return {"characters": chars,
            "character_start_times_seconds": [i * step for i in range(len(chars))],
            "character_end_times_seconds": [(i + 1) * step for i in range(len(chars))]}


class ElevenLabsAlignment(unittest.TestCase):
    def test_latin_words_keep_punctuation_and_span(self):
        words = alignment_to_words(_alignment("In 1815, a volcano."))
        self.assertEqual([w.text for w in words], ["In", "1815,", "a", "volcano."])
        self.assertAlmostEqual(words[1].start, 0.3)
        self.assertAlmostEqual(words[1].end, 0.8)

    def test_cjk_one_word_per_glyph(self):
        self.assertEqual([w.text for w in alignment_to_words(_alignment("火山，欧洲"))], ["火", "山", "，", "欧", "洲"])

    def test_restore_punctuation_marks_breaks(self):
        text = "In 1815, a volcano. This is it."
        words = subtitles.restore_punctuation(alignment_to_words(_alignment(text)), text)
        self.assertTrue(words[3].break_after)
        cues = subtitles.build_cues(words, offset=0, max_chars=42)
        self.assertEqual([c.text for c in cues], ["In 1815, a volcano.", "This is it."])

    def test_rate_to_speed(self):
        self.assertEqual(rate_to_speed("-10%"), 0.9)
        self.assertEqual(rate_to_speed("+50%"), 1.2)

    def test_synthesize_caches(self):
        prov = ElevenLabsProvider(rate="+0%")
        fake = {"audio_base64": "AAECAw==", "alignment": _alignment("Hi there.")}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(ElevenLabsProvider, "_request", return_value=fake) as req:
            out = Path(td) / "a.mp3"
            self.assertEqual([w.text for w in synthesize_cached(prov, "Hi there.", "JBFqnCBsd6RMkjVDRZzb", out)], ["Hi", "there."])
            synthesize_cached(prov, "Hi there.", "JBFqnCBsd6RMkjVDRZzb", out)
            self.assertEqual(req.call_count, 1)


PEXELS_PHOTOS = [
    {"id": 1, "width": 1000, "height": 2000, "url": "p1", "photographer": "A", "src": {"original": "u1o", "large2x": "u1l", "medium": "u1m"}},
    {"id": 2, "width": 4000, "height": 2000, "url": "p2", "photographer": "B", "src": {"original": "u2o", "large2x": "u2l", "medium": "u2m"}},
]
PEXELS_VIDEOS = [{"id": 10, "width": 1920, "height": 1080, "duration": 12, "url": "v10", "image": "th", "user": {"name": "C"},
                  "video_files": [{"file_type": "video/mp4", "width": 960, "height": 540, "link": "small"},
                                  {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "hd"},
                                  {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "uhd"}]}]


class Providers(unittest.TestCase):
    def test_pexels_mapping(self):
        prov = pexels.PexelsProvider()
        with mock.patch.object(pexels.PexelsProvider, "_get", return_value={"photos": PEXELS_PHOTOS}):
            cands = prov.search("volcano", "image")
        self.assertEqual([c.id for c in cands], ["1", "2"])
        self.assertFalse(cands[0].landscape)
        self.assertEqual(cands[1].download_url, "u2o", "wide photo -> original")
        with mock.patch.object(pexels.PexelsProvider, "_get", return_value={"videos": PEXELS_VIDEOS}):
            v = prov.search("lava", "video")[0]
        self.assertEqual((v.download_url, v.preview_url, v.duration), ("hd", "small", 12.0))

    def test_commons_licence_filter_and_thumb_rewrite(self):
        self.assertTrue(wikimedia.licence_ok("Public domain"))
        self.assertTrue(wikimedia.licence_ok("CC BY-SA 4.0"))
        self.assertTrue(wikimedia.licence_ok("CC0"))
        self.assertFalse(wikimedia.licence_ok("CC BY-NC 2.0"))
        self.assertFalse(wikimedia.licence_ok("Fair use"))
        self.assertFalse(wikimedia.licence_ok(""))
        self.assertEqual(wikimedia.thumb_at("https://x/thumb/a/ab/F.jpg/640px-F.jpg", 2560), "https://x/thumb/a/ab/F.jpg/2560px-F.jpg")
        pages = {"query": {"pages": [
            {"pageid": 5, "title": "File:Tambora.jpg", "imageinfo": [{"thumburl": "https://x/thumb/a/ab/T.jpg/640px-T.jpg", "url": "https://x/a/ab/T.jpg", "width": 3000, "height": 2000,
             "descriptionurl": "d", "extmetadata": {"LicenseShortName": {"value": "Public domain"}, "Artist": {"value": "<a href='#'>J. Doe</a>"}}}]},
            {"pageid": 6, "title": "File:NC.jpg", "imageinfo": [{"thumburl": "https://x/thumb/n.jpg/640px-n.jpg", "width": 3000, "height": 2000,
             "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}}}]},
        ]}}
        with mock.patch("vidforge.assets.wikimedia.http_json", return_value=pages):
            cands = wikimedia.CommonsProvider().search("tambora", "image")
        self.assertEqual([c.id for c in cands], ["5"])
        self.assertEqual(cands[0].author, "J. Doe")
        self.assertEqual(cands[0].download_url, "https://x/a/ab/T.jpg", "3000 px jpg -> original")
        self.assertEqual(wikimedia.allowed_width(1014), 960)
        self.assertEqual(wikimedia.allowed_width(5000), 1920)
        self.assertEqual(wikimedia.CommonsProvider().search("x", "video"), [])

    def test_library_records_and_credits(self):
        with tempfile.TemporaryDirectory() as td:
            lib = Library(Path(td))
            c = Candidate(provider="pexels", id="2", kind="image", thumb_url="", preview_url="", download_url="u",
                          width=4000, height=2000, duration=None, author="B", license="Pexels License", page_url="p2")
            dest = Path(td) / "assets" / "pexels" / "x-2.jpg"
            dest.parent.mkdir(parents=True); dest.write_bytes(b"x")
            lib.remember(c, dest); lib.save()
            lib2 = Library(Path(td))
            self.assertEqual(lib2.used_ids("pexels"), {"2"})
            self.assertIn("B — Pexels License — p2", lib2.credits({"assets/pexels/x-2.jpg"}))
            self.assertEqual(lib2.credits({"other"}), "")


class ProjectClips(unittest.TestCase):
    def _load(self, segs, extra=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x"); (root / "v.mp4").write_bytes(b"x")
            (root / "project.json").write_text(json.dumps({"title": "t", "segments": segs, **(extra or {})}), encoding="utf-8")
            return proj.load(root)

    def test_legacy_single_visual_becomes_one_clip(self):
        p = self._load([{"id": "s", "text": "a", "image": "a.jpg", "motion": "pan_left"},
                        {"id": "r", "text": "b", "remotion": {"composition": "TitleCard", "props": {"title": "X"}}}])
        self.assertEqual(len(p.segments[0].clips), 1)
        self.assertEqual(p.segments[0].clips[0].motion, "pan_left")
        self.assertEqual(p.segments[0].image.name, "a.jpg")
        self.assertEqual(p.segments[1].remotion.composition, "TitleCard")

    def test_clips_with_slices_and_sources(self):
        p = self._load([{"id": "s", "text": "a", "fit": "trim", "clips": [
            {"video": "v.mp4", "in": 4, "out": 9.5}, {"image": "a.jpg", "duration": 3},
            {"video": "pexels:lava"}, {"image": "commons:tambora painting"}]}])
        s = p.segments[0]
        self.assertEqual(s.fit, "trim")
        self.assertEqual(s.clips[0].slice_length, 5.5)
        self.assertEqual(s.clips[1].duration, 3)
        self.assertTrue(s.clips[2].needs_asset and s.clips[2].is_video)
        self.assertEqual(s.clips[3].source_kind, "image")
        self.assertTrue(s.needs_asset)

    def test_invalid_clips_rejected(self):
        for bad in ([{"image": "a.jpg", "in": 1}], [{"video": "v.mp4", "in": 5, "out": 2}], [{"image": "a.jpg", "video": "v.mp4"}]):
            with self.assertRaises(proj.ProjectError, msg=str(bad)):
                self._load([{"id": "s", "text": "a", "clips": bad}])
        with self.assertRaises(proj.ProjectError):
            self._load([{"id": "s", "text": "a", "image": "a.jpg", "clips": [{"image": "a.jpg"}]}])
        with self.assertRaises(proj.ProjectError):
            self._load([{"id": "s", "text": "a"}])

    def test_quality_and_silent_provider_fields(self):
        p = self._load([{"id": "s", "text": "a", "image": "a.jpg"}],
                       {"quality": "draft", "tts": {"provider": "silent"}, "transition": 0.5})
        self.assertEqual((p.quality, p.effective_supersample, p.tts.provider, p.transition), ("draft", 1, "silent", 0.5))


class RemotionSpecs(unittest.TestCase):
    def test_render_uses_cache_key_from_props(self):
        from vidforge import remotion
        with tempfile.TemporaryDirectory() as td, mock.patch.object(remotion, "_remotion_cli", return_value=["x"]), \
                mock.patch("subprocess.run") as run:
            def fake_run(cmd, **kw):
                Path(cmd[4]).write_bytes(b"v")
                return mock.Mock(returncode=0, stderr="", stdout="")
            run.side_effect = fake_run
            a = remotion.render("TitleCard", {"title": "A"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            b = remotion.render("TitleCard", {"title": "A"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            c = remotion.render("TitleCard", {"title": "B"}, duration=2, fps=30, width=320, height=180, out_dir=Path(td), log=lambda *_: None)
            self.assertEqual(a, b); self.assertNotEqual(a, c); self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
