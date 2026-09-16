"""Language variants: project.load(lang), localized props, i18n export/import round trip."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vidforge import i18n, project as proj

BASE = {
    "title": "The Year", "thumbnail_text": "THE YEAR", "voice": "en-US-AndrewNeural",
    "subtitles": {"font": "Arial", "font_size": 22, "burn": True},
    "youtube": {"description": "About.", "tags": ["history"]},
    "variants": {"zh": {"voice": "zh-CN-YunxiNeural", "title": "那一年",
                        "subtitles": {"font": "Microsoft YaHei"}, "youtube": {"description": "简介"}}},
    "segments": [
        {"id": "hook", "text": "In 1815.", "text_zh": "一八一五年。", "label": "Hook", "label_zh": "开场", "image": "a.jpg"},
        {"id": "tl", "text": "Timeline.", "text_zh": "时间轴。",
         "remotion": {"composition": "Timeline", "props": {
             "title": {"en": "From eruption", "zh": "从喷发"},
             "events": [{"date": "1815", "text": {"en": "Eruption", "zh": "喷发"}}],
             "theme": {"accent": "#fff"}}}},
    ],
}


def _write(root: Path, data: dict) -> None:
    (root / "a.jpg").write_bytes(b"x")
    (root / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class Variants(unittest.TestCase):
    def test_base_language_resolves_localized_props_to_en(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), BASE)
            p = proj.load(td)
            self.assertEqual(p.segments[1].remotion.props["title"], "From eruption")
            self.assertEqual(p.segments[1].remotion.props["events"][0]["text"], "Eruption")
            self.assertEqual(p.segments[1].remotion.props["theme"], {"accent": "#fff"}, "ordinary dicts untouched")
            self.assertEqual(p.build_dir.name, "build")

    def test_zh_variant_swaps_text_voice_overrides_and_out_dir(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), BASE)
            p = proj.load(td, lang="zh")
            self.assertEqual(p.language, "zh")
            self.assertEqual(p.voice, "zh-CN-YunxiNeural")
            self.assertEqual(p.title, "那一年")
            self.assertEqual(p.thumbnail_text, "THE YEAR", "not overridden -> base value")
            self.assertEqual((p.subtitles.font, p.subtitles.font_size, p.subtitles.burn), ("Microsoft YaHei", 22, True))
            self.assertEqual((p.youtube.description, p.youtube.tags), ("简介", ["history"]))
            self.assertEqual(p.segments[0].text, "一八一五年。")
            self.assertEqual(p.segments[0].label, "开场")
            self.assertEqual(p.segments[1].remotion.props["events"][0]["text"], "喷发")
            self.assertEqual(p.build_dir.name, "build_zh")

    def test_missing_translation_lists_segments(self):
        with tempfile.TemporaryDirectory() as td:
            data = json.loads(json.dumps(BASE))
            del data["segments"][1]["text_zh"]
            _write(Path(td), data)
            with self.assertRaises(proj.ProjectError) as cm:
                proj.load(td, lang="zh")
            self.assertIn("tl", str(cm.exception))
            with self.assertRaises(proj.ProjectError):
                proj.load(td, lang="fr")                 # no variant declared


class Sheets(unittest.TestCase):
    def test_export_then_import_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = json.loads(json.dumps(BASE))
            del data["variants"]
            for s in data["segments"]:
                s.pop("text_zh", None); s.pop("label_zh", None)
            _write(root, data)

            sheet_path = i18n.export(root, "zh")
            sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
            self.assertEqual(set(sheet["segments"]), {"hook", "tl"})
            self.assertEqual(sheet["segments"]["hook"]["text"]["source"], "In 1815.")
            self.assertIn("title", sheet["project"])

            sheet["segments"]["hook"]["text"]["zh"] = "一八一五年。"
            sheet["segments"]["hook"]["label"]["zh"] = "开场"
            sheet["project"]["title"]["zh"] = "那一年"
            sheet["youtube"]["description"]["zh"] = "简介"
            sheet_path.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")

            written, empty = i18n.import_(root, "zh")
            self.assertEqual(written, 4)
            self.assertEqual(empty, ["tl"])
            after = json.loads((root / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(after["segments"][0]["text_zh"], "一八一五年。")
            self.assertEqual(after["variants"]["zh"]["title"], "那一年")
            self.assertEqual(after["variants"]["zh"]["youtube"]["description"], "简介")
            self.assertEqual(after["variants"]["zh"]["voice"], "zh-CN-YunxiNeural")

            # second export lists only what is still empty
            sheet2 = json.loads(i18n.export(root, "zh").read_text(encoding="utf-8"))
            self.assertEqual(set(sheet2["segments"]), {"tl"})
            self.assertNotIn("title", sheet2["project"])


if __name__ == "__main__":
    unittest.main()
