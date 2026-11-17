"""Subtitle output: the plain .srt sidecar and the burned .ass with figures highlighted."""

from __future__ import annotations

import unittest
from pathlib import Path

from vidforge.tts import Word


class Highlight(unittest.TestCase):
    """Figures lit up as they are spoken — the one trick that falls out of the word timings."""

    def cues(self):
        from vidforge.subtitles import build_cues
        ws = [Word("中国", 0, .4), Word("去年", .4, .4), Word("增长", .8, .4),
              Word("5.2%", 1.2, .6), Word("。", 1.8, .1)]
        ws[-1].break_after = True
        return build_cues(ws, offset=0, max_chars=42)

    def test_cues_keep_their_word_timings(self):
        c = self.cues()[0]
        self.assertEqual([w.text for w in c.words], ["中国", "去年", "增长", "5.2%", "。"])
        self.assertAlmostEqual(c.words[3].start, 1.2)

    def test_offset_is_applied_to_the_kept_words_too(self):
        from vidforge.subtitles import build_cues
        ws = [Word("a", 0, .5), Word("b", .5, .5)]
        ws[-1].break_after = True
        c = build_cues(ws, offset=10.0, max_chars=42)[0]
        self.assertAlmostEqual(c.words[0].start, 10.0)

    def test_only_meaningful_figures_are_keys(self):
        from vidforge.subtitles import is_key_word
        for yes in ("5.2%", "1815", "14亿", "1,234", "$27.8", "2023年", "18.3万亿"):
            self.assertTrue(is_key_word(yes), yes)
        for no in ("1", "[1]", "GDP", "the", "中国", "百分之五"):
            self.assertFalse(is_key_word(no), no)

    def test_keywords_mode_colours_the_figure_and_restores_white(self):
        import tempfile
        from vidforge.subtitles import write_ass
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.ass"
            write_ass(self.cues(), f, font="Arial", font_size=22, margin_v=48, box=True,
                      highlight="keywords", colour="#d4793a")
            body = f.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1920", body)
        line = [l for l in body.splitlines() if l.startswith("Dialogue")][0]
        self.assertIn(r"{\c&H003A79D4}5.2%{\c&H00FFFFFF}", line)   # #d4793a as ASS BGR
        self.assertNotIn(r"{\c&H003A79D4}中国", line)

    def test_burned_size_is_the_same_share_of_the_frame_as_a_burned_srt(self):
        # font_size 22 went into a 1080-line file as 22 pixels: a third of the size the same
        # project got with highlighting off, and too small to read on a phone
        import tempfile
        from vidforge.subtitles import write_ass
        for height, width in ((1080, 1920), (1920, 1080), (2160, 3840)):
            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "a.ass"
                write_ass(self.cues(), f, font="Arial", font_size=22, margin_v=48, box=False, width=width, height=height)
                style = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Style:")][0].split(",")
            self.assertAlmostEqual(int(style[2]) / height, 22 / 288, delta=0.002)
            self.assertAlmostEqual(int(style[-2]) / height, 48 / 288, delta=0.002)

    def test_karaoke_mode_emits_one_line_per_word_and_keeps_figures_lit(self):
        import tempfile
        from vidforge.subtitles import write_ass
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "k.ass"
            write_ass(self.cues(), f, font="Arial", font_size=22, margin_v=48, box=False,
                      highlight="karaoke", colour="#d4793a")
            lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")]
        self.assertEqual(len(lines), 5)
        self.assertNotIn(r"{\c&H003A79D4}", lines[0])     # before the figure is spoken
        self.assertIn(r"{\c&H003A79D4}5.2%", lines[-1])   # and it stays lit afterwards

    def test_word_mode_lights_the_word_being_said_and_only_that_one(self):
        import tempfile
        from vidforge.subtitles import write_ass
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "w.ass"
            write_ass(self.cues(), f, font="Arial", font_size=22, margin_v=48, box=False,
                      highlight="word", colour="#d4793a")
            lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")]
        self.assertEqual(len(lines), 5)
        self.assertIn(r"{\c&H003A79D4\fscx112\fscy112}中国{\c&H00FFFFFF\fscx100\fscy100}去年", lines[0])
        self.assertEqual(lines[1].count(r"\fscx112"), 1, "one word at a time")
        self.assertIn(r"{\c&H003A79D4\fscx112\fscy112}去年", lines[1])
        self.assertIn(r"{\c&H003A79D4}5.2%{\c&H00FFFFFF}", lines[-1], "the figure stays lit once said")

    def test_a_figure_timed_together_with_a_word_is_still_lit_alone(self):
        # edge-tts gives "In 1815," as one word; the year went unlit in every English video
        import tempfile
        from vidforge.subtitles import Cue, is_key_word, write_ass
        self.assertTrue(is_key_word("In 1815,"))
        self.assertFalse(is_key_word("In the"))
        cue = Cue(0, 2, "In 1815, a volcano", [Word("In 1815,", 0, 1), Word("a", 1, .5), Word("volcano", 1.5, .5)])
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "g.ass"
            write_ass([cue], f, font="Arial", font_size=22, margin_v=48, box=False, highlight="keywords", colour="#d4793a")
            line = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")][0]
        self.assertIn(r"In {\c&H003A79D4}1815,{\c&H00FFFFFF} a volcano", line)

    def test_none_mode_is_plain_text(self):
        import tempfile
        from vidforge.subtitles import write_ass
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "n.ass"
            write_ass(self.cues(), f, font="Arial", font_size=22, margin_v=48, box=True, highlight="none")
            body = f.read_text(encoding="utf-8")
        self.assertNotIn(r"{\c", body)

    def test_braces_in_narration_cannot_break_the_ass_tags(self):
        import tempfile
        from vidforge.subtitles import Cue, write_ass
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "b.ass"
            write_ass([Cue(0, 1, "{\an8}hack", [Word("{\an8}hack", 0, 1)])], f,
                      font="Arial", font_size=22, margin_v=48, box=True, highlight="keywords")
            line = [l for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue")][0]
        self.assertIn("(", line)
        self.assertNotIn("{\an8}", line)


if __name__ == "__main__":
    unittest.main()
