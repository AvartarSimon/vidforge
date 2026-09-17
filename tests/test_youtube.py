"""YouTube upload: description/chapters are pure; the API client is a MagicMock (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import project as proj
from vidforge.upload import build_description, chapters_text


class Chapters(unittest.TestCase):
    def test_merges_short_segments_and_starts_at_zero(self):
        tl = [{"id": "hook", "start": 0.1, "end": 8}, {"id": "b", "start": 8, "end": 12},
              {"id": "c", "label": "The eruption", "start": 12, "end": 40}, {"id": "d", "start": 40, "end": 90}]
        text = chapters_text(tl)
        self.assertEqual(text.splitlines(), ["00:00 Hook", "00:12 The eruption", "00:40 D"])

    def test_fewer_than_three_chapters_yields_nothing(self):
        self.assertEqual(chapters_text([{"id": "a", "start": 0, "end": 30}, {"id": "b", "start": 30, "end": 60}]), "")

    def test_hours_format(self):
        tl = [{"id": "a", "start": 0}, {"id": "b", "start": 600}, {"id": "c", "start": 3725}]
        self.assertIn("01:02:05 C", chapters_text(tl))


class Upload(unittest.TestCase):
    def _project(self, root: Path) -> proj.Project:
        (root / "a.jpg").write_bytes(b"x")
        (root / "project.json").write_text(json.dumps({
            "title": "T", "youtube": {"description": "About.", "tags": ["h"], "playlist_id": "PL1"},
            "segments": [{"id": "s1", "text": "a", "image": "a.jpg"}]}), encoding="utf-8")
        p = proj.load(root)
        bd = p.build_dir
        bd.mkdir()
        (bd / "final.mp4").write_bytes(b"\x00" * 10)
        (bd / "final.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        (bd / "thumbnail.jpg").write_bytes(b"\xff\xd8")
        (bd / "credits.txt").write_text("Stock via Pexels:\nA — u", encoding="utf-8")
        (bd / "timeline.json").write_text(json.dumps(
            [{"id": "a", "start": 0}, {"id": "b", "start": 20}, {"id": "c", "start": 50}]), encoding="utf-8")
        return p

    def test_description_composes_all_parts(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._project(Path(td))
            d = build_description(p, p.build_dir)
            self.assertTrue(d.startswith("About."))
            self.assertIn("Chapters:\n00:00 A\n00:20 B\n00:50 C", d)
            self.assertIn("A — u", d)
            self.assertTrue(d.endswith("AI-synthesised narration."), "default disclosure (AI voice) closes the description")

    def test_upload_then_rerun_updates_instead_of_reuploading(self):
        from vidforge.upload import youtube
        yt = mock.MagicMock()
        req = yt.videos().insert.return_value
        req.next_chunk.side_effect = [(None, None), (None, {"id": "VID123"})]
        yt.captions.return_value.insert.return_value.execute.return_value = {"id": "CAP1"}
        # MediaFileUpload keeps final.mp4 open on Windows -> ignore cleanup errors
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            p = self._project(Path(td))
            state = youtube.upload(p, yt=yt, log=lambda *_: None)
            self.assertEqual(state["url"], "https://youtu.be/VID123")
            body = yt.videos().insert.call_args.kwargs["body"]
            self.assertEqual(body["status"]["privacyStatus"], "private")
            self.assertEqual(body["snippet"]["categoryId"], "27")
            self.assertFalse(body["status"]["containsSyntheticMedia"], "AI voice alone does not set YouTube's synthetic flag")
            yt.thumbnails().set.assert_called_once()
            yt.playlistItems().insert.assert_called_once()
            self.assertEqual(state["caption_id"], "CAP1")

            # second run: metadata update only, no second insert / caption / playlist
            youtube.upload(p, yt=yt, publish_at="2026-10-01T09:00:00Z", log=lambda *_: None)
            self.assertEqual(yt.videos().insert.call_count, 1)
            upd = yt.videos().update.call_args.kwargs["body"]
            self.assertEqual(upd["status"]["publishAt"], "2026-10-01T09:00:00Z")
            self.assertEqual(yt.captions().insert.call_count, 1)
            self.assertEqual(yt.playlistItems().insert.call_count, 1)

    def test_missing_final_mp4_is_a_clear_error(self):
        from vidforge.upload import youtube
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / "project.json").write_text(json.dumps(
                {"title": "T", "segments": [{"id": "s1", "text": "a", "image": "a.jpg"}]}), encoding="utf-8")
            with self.assertRaises(youtube.YouTubeError):
                youtube.upload(proj.load(root), yt=mock.MagicMock(), log=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
