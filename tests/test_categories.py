"""Topic-vertical presets (vidforge/categories.py): plain-JSON CRUD + export/import merge, and
the /api/new wiring that applies a category's defaults (voice, tts provider, ...) to a fresh
project. No database involved by design — see the module docstring for why."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from vidforge import categories as cat
from vidforge import ui


class Crud(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(cat, "DIR", self.td / "categories")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def test_save_assigns_slug_id_and_round_trips(self):
        rec = cat.save({"name": "中国古代历史人文", "topic_notes": "讲故事", "platforms": ["YouTube", "抖音"]})
        self.assertEqual(rec["id"], "中国古代历史人文")   # non-ASCII names keep readable ids
        self.assertIn("updated", rec)
        got = cat.load(rec["id"])
        self.assertEqual(got["topic_notes"], "讲故事")
        self.assertEqual([c["id"] for c in cat.list_categories()], [rec["id"]])

    def test_save_without_name_rejected(self):
        with self.assertRaises(cat.CategoryError):
            cat.save({"topic_notes": "no name"})

    def test_save_again_with_same_id_overwrites_not_duplicates(self):
        rec = cat.save({"name": "FND", "banned_keywords": ["a"]})
        cat.save({"id": rec["id"], "name": "FND", "banned_keywords": ["a", "b"]})
        self.assertEqual(len(cat.list_categories()), 1)
        self.assertEqual(cat.load(rec["id"])["banned_keywords"], ["a", "b"])

    def test_delete(self):
        rec = cat.save({"name": "temp"})
        cat.delete(rec["id"])
        self.assertIsNone(cat.load(rec["id"]))
        self.assertEqual(cat.list_categories(), [])

    def test_load_missing_returns_none_not_error(self):
        self.assertIsNone(cat.load("nope"))

    def test_export_then_import_merge_keeps_existing(self):
        cat.save({"name": "A"})
        bundle = cat.export_all()
        cat.delete("a")
        cat.save({"name": "B"})
        saved = cat.import_bundle(bundle, merge=True)
        self.assertEqual(len(saved), 1)
        ids = {c["id"] for c in cat.list_categories()}
        self.assertEqual(ids, {"a", "b"})   # B survived the merge, A came back from the bundle

    def test_import_replace_drops_existing(self):
        cat.save({"name": "A"})
        bundle = {"categories": [{"name": "C"}]}
        cat.import_bundle(bundle, merge=False)
        ids = {c["id"] for c in cat.list_categories()}
        self.assertEqual(ids, {"c"})

    def test_import_bad_shape_rejected(self):
        with self.assertRaises(cat.CategoryError):
            cat.import_bundle({"categories": "not a list"})


class ServerIntegration(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.cat_dir = self.td / "cat-store"
        self.patch = mock.patch.object(cat, "DIR", self.cat_dir)
        self.patch.start()
        root = self.td / "proj"
        (root / "assets").mkdir(parents=True)
        (root / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.state = ui.State(root / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        self.patch.stop()
        shutil.rmtree(self.td, ignore_errors=True)

    def call(self, path, body=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_crud_over_http(self):
        st, j = self.call("/api/categories")
        self.assertEqual((st, j["categories"]), (200, []))
        st, j = self.call("/api/categories", {"name": "中文历史", "defaults": {"voice": "zh-CN-YunxiNeural", "tts_provider": "edge"}})
        self.assertEqual(st, 200)
        cid = j["category"]["id"]
        st, j = self.call("/api/categories")
        self.assertEqual(len(j["categories"]), 1)
        st, j = self.call("/api/categories/delete", {"id": cid})
        self.assertEqual(j["categories"], [])

    def test_new_project_applies_category_defaults_and_stamps_id(self):
        self.call("/api/categories", {"name": "中文历史", "defaults": {"voice": "zh-CN-YunxiNeural", "tts_provider": "edge", "outro_vocab": 4}})
        st, j = self.call("/api/new", {"name": "p1", "title": "T", "language": "zh", "category": "中文历史", "dir": str(self.td / "work")})
        self.assertEqual(st, 200)
        data = json.loads(Path(j["opened"]).read_text(encoding="utf-8"))
        self.assertEqual(data["category"], "中文历史")
        self.assertEqual(data["voice"], "zh-CN-YunxiNeural")
        self.assertEqual(data["tts"]["provider"], "edge")
        self.assertEqual(data["outro_vocab"], 4)

    def test_new_project_unknown_category_is_ignored_not_fatal(self):
        st, j = self.call("/api/new", {"name": "p2", "title": "T", "category": "no-such-category", "dir": str(self.td / "work")})
        self.assertEqual(st, 200)
        data = json.loads(Path(j["opened"]).read_text(encoding="utf-8"))
        self.assertNotIn("category", data)


if __name__ == "__main__":
    unittest.main()
