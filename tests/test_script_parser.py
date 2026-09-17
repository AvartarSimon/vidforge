from __future__ import annotations

import unittest

from vidforge.script_parser import parse


class ScriptParser(unittest.TestCase):
    def test_markdown_headings_keep_blocks(self):
        segs = parse("## 1. The eruption\nTambora erupted in April 1815. Ash rose.\n\n## 2. Europe\nSnow fell in June.")
        self.assertEqual([s["label"] for s in segs], ["1. The eruption", "2. Europe"])
        self.assertTrue(segs[0]["text"].startswith("Tambora"))

    def test_paragraphs_under_a_heading_stay_separate_segments(self):
        segs = parse("## Opening\nFirst idea here.\n\nSecond idea here.\n\n## Next\nThird.")
        self.assertEqual([(s["label"], s["text"]) for s in segs],
                         [("Opening", "First idea here."), (None, "Second idea here."), ("Next", "Third.")])

    def test_chinese_numbering_and_brackets(self):
        segs = parse("一、开天辟地\n盘古挥斧，天地初分。\n\n第二章 女娲造人\n女娲抟土造人。\n【结尾】\n故事讲完了。")
        self.assertEqual([s["label"] for s in segs], ["开天辟地", "女娲造人", "结尾"])

    def test_screenplay_two_columns(self):
        segs = parse("Scene 1: Opening\n画面: 火山远景，红光\n旁白: 一八一五年，火山喷发。\n字幕: 1815\n旁白: 欧洲失去了夏天。")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["visual_hint"], "火山远景，红光")
        self.assertIn("欧洲失去了夏天", segs[0]["text"])
        self.assertNotIn("1815\n", segs[0]["text"])

    def test_plain_paragraphs_split_long_ones(self):
        long = " ".join(f"Sentence number {i} is here." for i in range(30))
        segs = parse("Short first paragraph.\n\n" + long)
        self.assertEqual(segs[0]["text"], "Short first paragraph.")
        self.assertGreater(len(segs), 2, "150-word paragraph split at sentence ends")
        self.assertTrue(all(len(s["text"].split()) <= 62 for s in segs))

    def test_numbered_sentence_is_not_a_heading(self):
        segs = parse("1. In 1815 the volcano erupted and this is clearly a full sentence of narration, not a title.\n\n2. Europe froze.")
        self.assertTrue(all(s["label"] is None for s in segs))

    def test_bare_title_before_visual_line_is_recognised_as_a_heading(self):
        """Real GPT output for our own copy-paste format spec: it wrote plain title lines (no
        '##') but did keep 'Visual: ...' before each paragraph. Before this rule, every such
        title became a one-line segment indistinguishable from real narration, and — worse —
        every Visual: line in the whole document collapsed onto the very first segment because
        no heading was ever recognised to split blocks apart."""
        text = ("The Year Without a Summer\n\nVisual: Mount Tambora volcano, 1815\n\n"
                "Imagine waking up in June.\n\nIt should be summer.\n\n"
                "The Volcano\n\nVisual: Mount Tambora eruption, ash\n\nThe story began one year earlier.")
        segs = parse(text)
        self.assertEqual([s["label"] for s in segs if s["label"]], ["The Year Without a Summer", "The Volcano"])
        self.assertEqual(segs[0]["visual_hint"], "Mount Tambora volcano, 1815")
        # the second chapter's visual must NOT have leaked onto the first chapter's segments
        self.assertIsNone(segs[1]["visual_hint"])
        third = next(s for s in segs if s["text"].startswith("The story began"))
        self.assertEqual(third["visual_hint"], "Mount Tambora eruption, ash")

    def test_visual_line_itself_is_never_mistaken_for_a_bare_title(self):
        """A 'Visual:'/'画面:' line is short and has no ending punctuation too — it must not
        become a heading just because the line after it also happens to be a marker line."""
        segs = parse("Scene 1: Opening\nVisual: a\nNarration: first line\nVisual: b\nNarration: second line")
        self.assertEqual(len(segs), 1)               # both narration lines join into one paragraph
        self.assertEqual(segs[0]["visual_hint"], "a; b")

    def test_each_visual_line_attaches_to_its_own_paragraph_not_the_whole_block(self):
        segs = parse("## Chapter\nVisual: first shot\n\nFirst paragraph.\n\nVisual: second shot\n\nSecond paragraph.")
        self.assertEqual([s["visual_hint"] for s in segs], ["first shot", "second shot"])

    def test_empty(self):
        self.assertEqual(parse("  \n "), [])


if __name__ == "__main__":
    unittest.main()
