"""vidforge/tts/voxcpm.py — the free/local, open-source Voice Design alternative to ElevenLabs.

VoxCPM2 itself isn't installed here (it pulls in PyTorch + a multi-GB model — nobody wants that
as a vidforge test dependency), so `_load_model()` and `soundfile` are stubbed: a fake model
whose `generate()` returns silence and a fake `soundfile.write()` that writes a real WAV via the
stdlib `wave` module, so the ffmpeg mux step in synthesize() runs against real, valid audio and
is genuinely exercised. Everything downstream of that boundary (seed/description resolution,
saved-voice profiles, cache keys, word timing) is real code, not mocked.
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

from vidforge import ffmpeg
from vidforge.tts import voxcpm
from vidforge.tts.voxcpm import VoxCPMError, VoxCPMProvider


def _ff() -> bool:
    try:
        ffmpeg.find_binary("ffmpeg"); return True
    except ffmpeg.FfmpegError:
        return False


class _FakeModel:
    """Stands in for VoxCPM.from_pretrained(...): records calls, returns a fixed-length silent
    'wav' (a plain list — no numpy dependency needed for the test)."""

    class _TtsModel:
        sample_rate = 24000

    def __init__(self):
        self.tts_model = self._TtsModel()
        self.calls: list[dict] = []

    def generate(self, text, cfg_value=None, inference_timesteps=None, seed=None):
        self.calls.append({"text": text, "cfg_value": cfg_value, "inference_timesteps": inference_timesteps, "seed": seed})
        return [0.0] * (self.tts_model.sample_rate // 2)   # 0.5s of silence


def _fake_soundfile_write(path, wav, samplerate):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(samplerate)
        f.writeframes(struct.pack(f"<{len(wav)}h", *([0] * len(wav))))


class Tokenize(unittest.TestCase):
    def test_latin_splits_on_spaces(self):
        self.assertEqual(voxcpm._tokenize("In 1815 a volcano erupted."), ["In", "1815", "a", "volcano", "erupted."])

    def test_cjk_falls_back_to_one_token_per_character(self):
        self.assertEqual(voxcpm._tokenize("一八一五年四月火山爆发"), list("一八一五年四月火山爆发"))

    def test_short_line_not_forced_into_characters(self):
        # < 9 chars: not worth the CJK special-case even if it were CJK; here just checks the guard
        self.assertEqual(voxcpm._tokenize("Hi there"), ["Hi", "there"])


class ProfileStorage(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(voxcpm, "VOICES_DIR", self.td / "voxcpm")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def test_keep_then_resolve_round_trips_description_and_seed(self):
        name = voxcpm.keep("voxcpm:424242", "Narrator", "deep warm male voice")
        self.assertEqual(name, "Narrator")
        prov = VoxCPMProvider()
        desc, seed = prov._resolve("Narrator")
        self.assertEqual((desc, seed), ("deep warm male voice", 424242))

    def test_keep_rejects_a_non_voxcpm_id(self):
        with self.assertRaises(VoxCPMError):
            voxcpm.keep("elevenlabs-style-id", "Narrator", "desc")

    def test_inline_description_needs_no_saved_profile(self):
        prov = VoxCPMProvider()
        desc, seed = prov._resolve("(a cheerful young woman)")
        self.assertEqual((desc, seed), ("a cheerful young woman", None))

    def test_resolve_unknown_name_raises_with_actionable_message(self):
        prov = VoxCPMProvider()
        with self.assertRaisesRegex(VoxCPMError, "no saved VoxCPM2 voice"):
            prov._resolve("nonexistent")

    def test_list_voices_reads_saved_profiles_and_filters_by_substring(self):
        voxcpm.keep("voxcpm:1", "WarmMan", "deep warm magnetic male narrator")
        voxcpm.keep("voxcpm:2", "BrightWoman", "cheerful bright young woman")
        prov = VoxCPMProvider()
        self.assertEqual({n for n, _ in prov.list_voices(None)}, {"WarmMan", "BrightWoman"})
        self.assertEqual([n for n, _ in prov.list_voices("warm")], ["WarmMan"])

    def test_not_installed_gives_actionable_error_not_a_bare_import_traceback(self):
        with mock.patch.dict(sys.modules, {"voxcpm": None}):
            with self.assertRaisesRegex(VoxCPMError, "pip install voxcpm"):
                voxcpm._load_model()


@unittest.skipUnless(_ff(), "ffmpeg not installed")
class Synthesize(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(voxcpm, "VOICES_DIR", self.td / "voxcpm")]
        for p in self.patches:
            p.start()
        self.model = _FakeModel()
        self.fake_sf = types.ModuleType("soundfile")
        self.fake_sf.write = _fake_soundfile_write
        self.sys_patch = mock.patch.dict(sys.modules, {"soundfile": self.fake_sf})
        self.sys_patch.start()

    def tearDown(self):
        self.sys_patch.stop()
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def test_synthesize_uses_saved_seed_and_produces_real_muxed_audio_with_even_word_timing(self):
        voxcpm.keep("voxcpm:99", "Narrator", "warm deep male voice")
        prov = VoxCPMProvider()
        with mock.patch.object(prov, "_model_lazy", return_value=self.model):
            out = self.td / "out.mp3"
            words = prov.synthesize("In 1815 a volcano erupted", "Narrator", out)
        self.assertTrue(out.exists())
        self.assertAlmostEqual(ffmpeg.duration(out), 0.5, delta=0.15)
        self.assertEqual([w.text for w in words], ["In", "1815", "a", "volcano", "erupted"])
        # word spans must tile the *real* rendered duration, not a pre-estimate
        self.assertAlmostEqual(words[-1].end, ffmpeg.duration(out), delta=0.2)
        call = self.model.calls[0]
        self.assertEqual(call["seed"], 99)
        self.assertTrue(call["text"].startswith("(warm deep male voice)"))

    def test_design_returns_n_independent_previews_with_distinct_seeds(self):
        with mock.patch.object(voxcpm, "_load_model", return_value=self.model):
            out_dir = self.td / "previews"
            previews = voxcpm.design("cheerful young woman", out_dir=out_dir, n=2)
        self.assertEqual(len(previews), 2)
        seeds = {p["seed"] for p in previews}
        self.assertEqual(len(seeds), 2, "each preview should use a different seed")
        for p in previews:
            self.assertTrue(Path(p["audio"]).exists())
            self.assertTrue(p["generated_voice_id"].startswith("voxcpm:"))

    def test_cache_key_differs_by_voice_and_text(self):
        prov = VoxCPMProvider()
        a = prov.cache_key("hello", "Narrator")
        b = prov.cache_key("hello", "Other")
        c = prov.cache_key("goodbye", "Narrator")
        self.assertEqual(len({a, b, c}), 3)


if __name__ == "__main__":
    unittest.main()
