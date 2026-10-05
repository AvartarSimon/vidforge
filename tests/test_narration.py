"""Own-voice narration: voice presets, force alignment, and the /api/narration|voicefx routes.

The alignment tests that need faster-whisper skip without it (it is an optional dependency and
pulls a model download); everything else — tokenising, matching, interpolation, the even-spread
fallback, trimming, caching — runs offline.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import align as aligner, ffmpeg, narration, project as proj, ui, voicefx
from vidforge.tts import Word

ZH = "去年全国有六百八十万平方米的新房没有卖掉。这个数字背后是三个故事。"
EN = "Last year six hundred thousand homes went unsold. That number hides three stories."


def tone(path: Path, seconds: float = 4.0, *, silence: float = 0.0) -> Path:
    """A sine tone, optionally with silence glued on either end."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if silence <= 0:
        ffmpeg.run(["-y", "-f", "lavfi", "-i", f"sine=f=220:d={seconds}",
                    "-c:a", "libmp3lame", str(path)])
        return path
    ffmpeg.run(["-y", "-f", "lavfi", "-i", f"sine=f=220:d={seconds}",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                "-filter_complex",
                f"[1:a]atrim=0:{silence},asetpts=N/SR/TB,asplit=2[s1][s2];"
                f"[s1][0:a][s2]concat=n=3:v=0:a=1[a]",
                "-map", "[a]", "-c:a", "libmp3lame", str(path)])
    return path


class VoiceFxTest(unittest.TestCase):
    def test_every_preset_is_listed(self):
        ids = {p["id"] for p in voicefx.listing()}
        self.assertEqual(ids, {p.id for p in voicefx.PRESETS})
        self.assertIn("none", ids)

    def test_none_is_an_empty_chain(self):
        self.assertEqual(voicefx.chain("none"), "")
        self.assertEqual(voicefx.chain(""), "")

    def test_a_chain_is_comma_terminated_so_it_splices(self):
        for p in voicefx.PRESETS:
            if p.chain:
                self.assertTrue(voicefx.chain(p.id).endswith(","), p.id)
                self.assertNotIn(",,", voicefx.chain(p.id) + "loudnorm")

    def test_unknown_preset_names_the_options(self):
        with self.assertRaises(KeyError) as cm:
            voicefx.get("sparkly")
        self.assertIn("warm", str(cm.exception))

    def test_case_and_space_are_forgiven(self):
        self.assertEqual(voicefx.get("  WARM ").id, "warm")

    def test_pitch_is_off_at_zero_and_a_ratio_otherwise(self):
        self.assertEqual(voicefx.pitch_filter(0), "")
        self.assertEqual(voicefx.pitch_filter(0.001), "")
        self.assertTrue(voicefx.pitch_filter(-1).startswith("rubberband=pitch=0.94"))
        self.assertTrue(voicefx.pitch_filter(12).startswith("rubberband=pitch=2.0")
                        if voicefx.MAX_PITCH >= 12 else True)

    def test_pitch_is_comma_terminated_so_it_splices(self):
        self.assertTrue(voicefx.pitch_filter(-2).endswith(","))

    def test_pitch_refuses_nonsense(self):
        for bad in (voicefx.MAX_PITCH + 1, -99, "x", None, float("nan")):
            with self.assertRaises(KeyError, msg=repr(bad)):
                voicefx.pitch_filter(bad)

    def test_only_deep_actually_lowers_the_pitch(self):
        # measured with autocorrelation on real speech: deep -0.97 semitones, warm +0.10, radio
        # +0.20. warm and radio reshape the tone; shifting pitch is deep's whole job.
        self.assertIn("rubberband", voicefx.get("deep").chain)
        for other in ("warm", "clear", "radio", "clean", "phone"):
            self.assertNotIn("rubberband", voicefx.get(other).chain, other)

    def test_no_preset_uses_a_filter_that_changes_length(self):
        # atempo/asetrate would slide the whole subtitle track, which is measured against this audio
        for p in voicefx.PRESETS:
            for banned in ("atempo", "asetrate", "atrim", "apad", "silenceremove"):
                self.assertNotIn(banned, p.chain, f"{p.id} must not use {banned}")

    def test_no_preset_changes_the_duration(self):
        # the word timings were measured against this audio: a filter that stretched it would
        # slide the whole subtitle track
        td = Path(tempfile.mkdtemp())
        try:
            src = tone(td / "src.mp3", 4.0)
            want = ffmpeg.duration(src)
            for p in voicefx.PRESETS:
                out = td / f"{p.id}.mp3"
                ffmpeg.run(["-y", "-i", str(src), "-af", p.chain or "anull", str(out)])
                self.assertAlmostEqual(ffmpeg.duration(out), want, delta=0.05, msg=p.id)
        finally:
            shutil.rmtree(td, ignore_errors=True)


class TokenTest(unittest.TestCase):
    def test_cjk_is_tokenised_per_character(self):
        self.assertEqual(aligner.tokenize("你好，世界。"), ["你", "好", "世", "界"])

    def test_latin_is_tokenised_per_word(self):
        self.assertEqual(aligner.tokenize("Hello, brave  world!"), ["Hello,", "brave", "world!"])

    def test_cjk_detection_tolerates_embedded_latin_and_digits(self):
        self.assertTrue(aligner.is_cjk("2026 年的中国房地产"))
        self.assertFalse(aligner.is_cjk("China's housing market in 2026"))
        self.assertFalse(aligner.is_cjk("12345 67890"))

    def test_key_ignores_case_width_and_punctuation(self):
        self.assertEqual(aligner._key("Hello,"), aligner._key("“hello”"))
        self.assertEqual(aligner._key("ＡＢＣ"), "abc")

    def test_key_maps_chinese_numerals_to_digits(self):
        # Whisper writes a spoken year as digits; the script may write it either way
        self.assertEqual(aligner._key("二零二一"), aligner._key("2021"))
        self.assertEqual(aligner._key("八"), "8")

    def test_key_leaves_the_magnitudes_alone(self):
        # 百/十 need parsing, not substitution — mapping them would make 十 equal to nothing useful
        self.assertEqual(aligner._key("百"), "百")


class EvenSpreadTest(unittest.TestCase):
    def test_tokens_share_the_real_length(self):
        words = aligner.even_spread(ZH, 10.0)
        self.assertEqual(len(words), len(aligner.tokenize(ZH)))
        self.assertAlmostEqual(words[0].start, 0.0)
        self.assertLessEqual(words[-1].end, 10.01)

    def test_empty_inputs(self):
        self.assertEqual(aligner.even_spread("", 10.0), [])
        self.assertEqual(aligner.even_spread(ZH, 0.0), [])


class MatchTest(unittest.TestCase):
    def flat(self, pairs):
        return [(t, s, e) for t, s, e in pairs]

    def test_a_perfect_transcription_matches_every_token(self):
        toks = ["a", "b", "c"]
        flat = self.flat([("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 2.0, 3.0)])
        self.assertEqual(aligner._match(toks, flat), [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)])

    def test_a_misheard_token_is_left_for_interpolation(self):
        toks = ["a", "zzz", "c"]
        flat = self.flat([("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 2.0, 3.0)])
        self.assertEqual(aligner._match(toks, flat)[1], None)

    def test_extra_transcribed_words_are_ignored(self):
        toks = ["a", "c"]
        flat = self.flat([("a", 0.0, 1.0), ("um", 1.0, 1.2), ("c", 2.0, 3.0)])
        self.assertEqual(aligner._match(toks, flat), [(0.0, 1.0), (2.0, 3.0)])


class InterpolateTest(unittest.TestCase):
    def test_holes_are_filled_between_anchors(self):
        out = aligner._interpolate([(0.0, 1.0), None, None, (4.0, 5.0)], 5.0)
        self.assertEqual(out[0], (0.0, 1.0))
        self.assertEqual(out[3], (4.0, 5.0))
        self.assertTrue(1.0 <= out[1][0] <= out[2][0] <= 4.0)

    def test_leading_hole_walks_back_to_zero(self):
        out = aligner._interpolate([None, None, (2.0, 3.0)], 5.0)
        self.assertAlmostEqual(out[0][0], 0.0)
        self.assertLessEqual(out[1][1], 2.001)

    def test_trailing_hole_walks_to_the_end_of_the_audio(self):
        out = aligner._interpolate([(0.0, 1.0), None, None], 6.0)
        self.assertLessEqual(out[-1][1], 6.001)
        self.assertGreater(out[-1][0], 1.0)

    def test_nothing_matched_falls_back_to_an_even_spread(self):
        out = aligner._interpolate([None, None, None, None], 8.0)
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(out[0][0], 0.0)
        self.assertAlmostEqual(out[-1][1], 8.0)

    def test_the_result_is_always_monotonic(self):
        # a subtitle track that goes backwards is worse than one that is slightly off
        cases = [
            [(1.0, 2.0), None, (1.5, 1.5), None, (9.0, 9.5)],
            [None, (0.0, 0.0), None, (0.0, 0.1), None],
            [(0.0, 5.0), None],
        ]
        for matched in cases:
            out = aligner._interpolate(matched, 10.0)
            starts = [s for s, _ in out]
            self.assertEqual(starts, sorted(starts), matched)


class AlignFallbackTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.audio = tone(self.td / "a.mp3", 6.0)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_without_faster_whisper_it_spreads_evenly_instead_of_failing(self):
        with mock.patch.object(aligner, "available", return_value=False):
            words = aligner.align(self.audio, ZH)
        self.assertEqual(len(words), len(aligner.tokenize(ZH)))

    def test_silence_spreads_evenly_too(self):
        with mock.patch.object(aligner, "available", return_value=True), \
             mock.patch.object(aligner, "transcribe", return_value=[]):
            words = aligner.align(self.audio, ZH)
        self.assertEqual(len(words), len(aligner.tokenize(ZH)))

    def test_a_missing_file_is_an_error_not_a_fallback(self):
        with self.assertRaises(aligner.AlignError):
            aligner.align(self.td / "nope.mp3", ZH)

    def test_empty_text(self):
        self.assertEqual(aligner.align(self.audio, "   "), [])

    def test_the_transcription_never_overrides_the_script(self):
        # the subtitle says what the script says; Whisper is only asked *when*
        heard = [("去", 0.0, 0.2), ("年", 0.2, 0.4), ("有", 0.4, 0.6)]
        with mock.patch.object(aligner, "available", return_value=True), \
             mock.patch.object(aligner, "transcribe", return_value=heard):
            words = aligner.align(self.audio, "去年有六百八十万")
        self.assertEqual("".join(w.text for w in words), "去年有六百八十万")


class NarrationTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_extract_trims_the_silence_at_either_end(self):
        src = tone(self.td / "take.mp3", 4.0, silence=1.5)
        self.assertGreater(ffmpeg.duration(src), 6.0)
        kept = narration.extract(src, self.td / "out.mp3")
        self.assertAlmostEqual(kept, 4.0, delta=0.5)

    def test_trim_can_be_turned_off(self):
        src = tone(self.td / "take.mp3", 4.0, silence=1.5)
        kept = narration.extract(src, self.td / "out.mp3", trim=False)
        self.assertGreater(kept, 6.0)

    def test_extract_pulls_the_audio_out_of_a_video(self):
        vid = self.td / "clip.mp4"
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-v", "error", "-y",
                        "-f", "lavfi", "-i", "color=c=black:s=320x180:d=3",
                        "-f", "lavfi", "-i", "sine=f=220:d=3",
                        "-shortest", str(vid)], check=True)
        kept = narration.extract(vid, self.td / "out.mp3", trim=False)
        self.assertAlmostEqual(kept, 3.0, delta=0.4)

    def test_an_unsupported_format_is_refused(self):
        bad = self.td / "take.txt"
        bad.write_text("not audio", encoding="utf-8")
        with self.assertRaises(narration.NarrationError):
            narration.extract(bad, self.td / "out.mp3")

    def test_prepare_caches_so_whisper_runs_once(self):
        src = tone(self.td / "take.mp3", 4.0)
        out = self.td / "seg1.own.mp3"
        calls = []

        def fake(audio, text, *, lang=None, log=None):
            calls.append(text)
            return aligner.even_spread(text, 4.0)

        with mock.patch.object(narration.aligner, "align", side_effect=fake):
            first = narration.prepare(src, out, ZH)
            second = narration.prepare(src, out, ZH)
        self.assertEqual(len(calls), 1, "second call should come from the sidecar")
        self.assertEqual([w.text for w in first], [w.text for w in second])

    def test_editing_the_line_re_aligns(self):
        src = tone(self.td / "take.mp3", 4.0)
        out = self.td / "seg1.own.mp3"
        calls = []

        def fake(audio, text, *, lang=None, log=None):
            calls.append(text)
            return aligner.even_spread(text, 4.0)

        with mock.patch.object(narration.aligner, "align", side_effect=fake):
            narration.prepare(src, out, ZH)
            narration.prepare(src, out, ZH + "还有一句。")
        self.assertEqual(len(calls), 2)

    def test_a_corrupt_sidecar_is_redone_not_raised(self):
        src = tone(self.td / "take.mp3", 4.0)
        out = self.td / "seg1.own.mp3"
        with mock.patch.object(narration.aligner, "align",
                               side_effect=lambda a, t, **k: aligner.even_spread(t, 4.0)):
            narration.prepare(src, out, ZH)
            out.with_suffix(".json").write_text("{ not json", encoding="utf-8")
            words = narration.prepare(src, out, ZH)
        self.assertTrue(words)

    def test_save_upload_replaces_the_previous_take(self):
        first = narration.save_upload(self.td, "seg1", b"aaa", "webm")
        second = narration.save_upload(self.td, "seg1", b"bbb", "m4a")
        self.assertFalse(first.exists(), "re-recording should not pile up files")
        self.assertEqual(second.read_bytes(), b"bbb")
        self.assertEqual(second.parent, self.td / "assets" / "narration")

    def test_save_upload_sanitises_the_segment_id(self):
        path = narration.save_upload(self.td, "../../evil seg", b"x", "wav")
        self.assertEqual(path.parent, self.td / "assets" / "narration")
        self.assertNotIn(".", path.stem)

    def test_save_upload_refuses_empty_and_unknown(self):
        with self.assertRaises(narration.NarrationError):
            narration.save_upload(self.td, "seg1", b"", "wav")
        with self.assertRaises(narration.NarrationError):
            narration.save_upload(self.td, "seg1", b"x", "exe")


class ProjectFieldTest(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        tone(self.td / "assets" / "take.mp3", 3.0)
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi",
                        "-i", "color=c=black:s=64x64", "-frames:v", "1",
                        str(self.td / "assets" / "a.png")], check=True)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def write(self, **extra):
        data = {"title": "T", "voice": "en-US-AndrewNeural",
                "segments": [{"id": "s1", "text": "Hello.", "clips": [{"image": "assets/a.png"}]}]}
        data.update(extra)
        (self.td / "project.json").write_text(json.dumps(data), encoding="utf-8")
        return proj.load(self.td / "project.json")

    def test_narration_defaults_to_none(self):
        self.assertIsNone(self.write().segments[0].narration)

    def test_narration_is_resolved_against_the_project(self):
        p = self.write(segments=[{"id": "s1", "text": "Hello.", "narration": "assets/take.mp3",
                                  "clips": [{"image": "assets/a.png"}]}])
        # resolve() on both sides: mkdtemp hands back an 8.3 short path on Windows
        self.assertEqual(p.segments[0].narration.resolve(),
                         (self.td / "assets" / "take.mp3").resolve())

    def test_a_missing_recording_fails_at_load(self):
        with self.assertRaises(proj.ProjectError) as cm:
            self.write(segments=[{"id": "s1", "text": "Hi.", "narration": "assets/gone.mp3",
                                  "clips": [{"image": "assets/a.png"}]}])
        self.assertIn("narration", str(cm.exception))

    def test_voice_fx_defaults_to_none_and_round_trips(self):
        self.assertEqual(self.write().voice_fx, "none")
        self.assertEqual(self.write(voice_fx="warm").voice_fx, "warm")

    def test_a_typo_in_voice_fx_fails_at_load(self):
        # three minutes into a render is the wrong place to find out
        with self.assertRaises(proj.ProjectError) as cm:
            self.write(voice_fx="wram")
        self.assertIn("wram", str(cm.exception))

    def test_narration_trim_defaults_on(self):
        self.assertTrue(self.write().narration_trim)
        self.assertFalse(self.write(narration_trim=False).narration_trim)

    def test_voice_fx_is_part_of_the_clip_cache_key(self):
        from vidforge import pipeline, render
        a, b = self.write(voice_fx="none"), self.write(voice_fx="warm")
        audio = self.td / "assets" / "take.mp3"
        enc = render.pick_encoder(a)
        self.assertNotEqual(pipeline._segment_key(a, a.segments[0], audio, enc),
                            pipeline._segment_key(b, b.segments[0], audio, enc))

    def test_voice_pitch_is_part_of_the_clip_cache_key(self):
        from vidforge import pipeline, render
        a, b = self.write(voice_pitch=0), self.write(voice_pitch=-1.5)
        audio = self.td / "assets" / "take.mp3"
        enc = render.pick_encoder(a)
        self.assertNotEqual(pipeline._segment_key(a, a.segments[0], audio, enc),
                            pipeline._segment_key(b, b.segments[0], audio, enc))

    def test_voice_pitch_defaults_to_zero_and_round_trips(self):
        self.assertEqual(self.write().voice_pitch, 0.0)
        self.assertEqual(self.write(voice_pitch=-1.5).voice_pitch, -1.5)

    def test_an_out_of_range_pitch_fails_at_load(self):
        with self.assertRaises(proj.ProjectError):
            self.write(voice_pitch=12)


class NarrationApi(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        tone(self.td / "assets" / "take.mp3", 3.0)
        subprocess.run([ffmpeg.find_binary("ffmpeg"), "-v", "error", "-y", "-f", "lavfi",
                        "-i", "color=c=black:s=64x64", "-frames:v", "1",
                        str(self.td / "assets" / "a.png")], check=True)
        (self.td / "project.json").write_text(json.dumps({
            "title": "T", "language": "zh", "voice": "zh-CN-YunxiNeural",
            "segments": [{"id": "s1", "text": ZH, "clips": [{"image": "assets/a.png"}]},
                         {"id": "s2", "text": "第二段。", "clips": [{"image": "assets/a.png"}]}],
        }, ensure_ascii=False), encoding="utf-8")
        self.state = ui.State(self.td / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                     method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_voicefx_lists_presets_and_the_current_one(self):
        status, j = self.call("/api/voicefx")
        self.assertEqual(status, 200)
        self.assertEqual({p["id"] for p in j["presets"]}, {p.id for p in voicefx.PRESETS})
        self.assertEqual(j["current"], "none")
        self.assertEqual(j["own_segments"], [])
        self.assertIsInstance(j["whisper"], bool)

    def test_upload_points_the_segment_at_the_recording(self):
        data = base64.b64encode((self.td / "assets" / "take.mp3").read_bytes()).decode()
        status, j = self.call("/api/narration/upload", {"segment": "s1", "data": data, "ext": "mp3"})
        self.assertEqual(status, 200)
        self.assertEqual(j["narration"], "assets/narration/s1.mp3")
        self.assertAlmostEqual(j["seconds"], 3.0, delta=0.4)
        on_disk = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["segments"][0]["narration"], "assets/narration/s1.mp3")
        self.assertNotIn("narration", on_disk["segments"][1])
        _, listing = self.call("/api/voicefx")
        self.assertEqual(listing["own_segments"], ["s1"])

    def test_clear_puts_the_segment_back_on_tts(self):
        data = base64.b64encode((self.td / "assets" / "take.mp3").read_bytes()).decode()
        self.call("/api/narration/upload", {"segment": "s1", "data": data, "ext": "mp3"})
        status, j = self.call("/api/narration/clear", {"segment": "s1"})
        self.assertEqual(status, 200)
        self.assertIsNone(j["narration"])
        on_disk = json.loads((self.td / "project.json").read_text(encoding="utf-8"))
        self.assertNotIn("narration", on_disk["segments"][0])

    def test_upload_rejects_an_unknown_segment_and_bad_data(self):
        self.assertEqual(self.call("/api/narration/upload",
                                   {"segment": "nope", "data": "", "ext": "mp3"})[0], 400)
        self.assertEqual(self.call("/api/narration/upload",
                                   {"segment": "s1", "data": "!!!not base64!!!"})[0], 400)
        self.assertEqual(self.call("/api/narration/upload", {"data": "AAAA"})[0], 400)

    def test_align_refuses_a_tts_segment(self):
        status, j = self.call("/api/narration/align", {"segment": "s2"})
        self.assertEqual(status, 400)
        self.assertIn("TTS", j["error"])

    def test_align_returns_words_for_an_uploaded_take(self):
        data = base64.b64encode((self.td / "assets" / "take.mp3").read_bytes()).decode()
        self.call("/api/narration/upload", {"segment": "s1", "data": data, "ext": "mp3"})
        with mock.patch.object(aligner, "available", return_value=False):
            status, j = self.call("/api/narration/align", {"segment": "s1"})
        self.assertEqual(status, 200)
        self.assertEqual(j["words"], len(aligner.tokenize(ZH)))
        self.assertTrue(j["preview"])
        self.assertTrue((self.td / "build" / "audio" / "s1.own.mp3").is_file())

    def test_voicefx_preview_renders_before_and_after(self):
        data = base64.b64encode((self.td / "assets" / "take.mp3").read_bytes()).decode()
        self.call("/api/narration/upload", {"segment": "s1", "data": data, "ext": "mp3"})
        with mock.patch.object(aligner, "available", return_value=False):
            status, j = self.call("/api/voicefx/preview", {"preset": "warm", "source": "s1"})
        self.assertEqual(status, 200)
        self.assertNotEqual(j["before"], j["after"])
        self.assertTrue(j["chain"])
        for rel in (j["before"], j["after"]):
            self.assertTrue((self.td / rel).is_file(), rel)

    def test_voicefx_preview_rejects_an_unknown_preset(self):
        status, _ = self.call("/api/voicefx/preview", {"preset": "sparkly"})
        self.assertEqual(status, 400)


@unittest.skipUnless(aligner.available(), "faster-whisper not installed")
class RealAlignmentTest(unittest.TestCase):
    """Alignment against ground truth: edge-tts reports where every word actually landed.

    Needs the network the first time (edge-tts for the audio, Hugging Face for the model)."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _truth(self, text, voice):
        from vidforge import subtitles
        from vidforge.tts import get_provider
        audio = self.td / "gt.mp3"
        prov = get_provider("edge", rate="+0%", config={})
        try:
            words = prov.synthesize(text, voice, audio)
        except Exception as e:                                  # noqa: BLE001 — offline / endpoint
            self.skipTest(f"edge-tts unavailable: {e}")
        return audio, subtitles.restore_punctuation(words, text)

    def _error(self, text, voice):
        audio, truth = self._truth(text, voice)
        got = aligner.align(audio, text)
        toks = aligner.tokenize(text)
        cjk = aligner.is_cjk(text)
        errs, pos = [], 0
        for w in truth:
            key = aligner._key(w.text)
            if not key:
                continue
            head = key[0] if cjk else key
            idx = next((i for i in range(pos, len(toks))
                        if aligner._key(toks[i]).startswith(head)), None)
            if idx is None:
                continue
            pos = idx + 1
            errs.append(abs(got[idx].start - w.start))
        self.assertTrue(errs, "nothing comparable")
        return sorted(errs), got

    def test_chinese_alignment_beats_an_even_spread(self):
        errs, got = self._error(ZH, "zh-CN-YunxiNeural")
        mean = sum(errs) / len(errs)
        self.assertLess(mean, 0.25, f"mean error {mean:.3f}s")
        self.assertLess(errs[len(errs) // 2], 0.15)
        self.assertEqual("".join(w.text for w in got), "".join(aligner.tokenize(ZH)))

    def test_english_alignment_beats_an_even_spread(self):
        errs, _ = self._error(EN, "en-US-AndrewNeural")
        mean = sum(errs) / len(errs)
        self.assertLess(mean, 0.25, f"mean error {mean:.3f}s")

    def test_timings_stay_inside_the_audio(self):
        audio, _ = self._truth(ZH, "zh-CN-YunxiNeural")
        seconds = ffmpeg.duration(audio)
        got = aligner.align(audio, ZH)
        self.assertGreaterEqual(got[0].start, 0.0)
        self.assertLessEqual(got[-1].end, seconds + 0.05)
        starts = [w.start for w in got]
        self.assertEqual(starts, sorted(starts))


if __name__ == "__main__":
    unittest.main()
