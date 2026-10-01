"""The default UI boots: index.html, its hashed bundle, and the legacy fallback at /old."""

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

from vidforge import ui


@unittest.skipUnless(ui.react_ready(), "React bundle not built (npm run build in vidforge/ui/react)")
class ReactIsDefault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp()
        root = Path(cls.td)
        (root / "assets").mkdir()
        (root / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        cls.state = ui.State(root / "project.json")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(cls.state))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        shutil.rmtree(cls.td, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()

    def test_root_serves_the_react_page_not_the_old_one(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"/assets/", body)                 # the built bundle, not the inline old UI
        self.assertNotIn(b"/static/app.js", body)

    def test_the_hashed_bundle_is_reachable_and_is_javascript(self):
        _, _, body = self.get("/")
        import re
        m = re.search(rb'src="(/assets/[^"]+\.js)"', body)
        self.assertIsNotNone(m, "index.html should reference a bundle")
        status, ctype, js = self.get(m.group(1).decode())
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertGreater(len(js), 10_000)

    def test_a_path_outside_dist_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/assets/../../../pyproject.toml")
        self.assertIn(cm.exception.code, (400, 403, 404))

    def test_the_old_ui_is_still_reachable_as_a_fallback(self):
        status, ctype, body = self.get("/old")
        self.assertEqual(status, 200)
        self.assertIn(b"/static/app.js", body)

    def test_health_reports_which_ui_is_live(self):
        _, _, body = self.get("/api/health")
        self.assertEqual(json.loads(body)["ui"], "react")


class BuildFallback(unittest.TestCase):
    def test_without_node_it_says_so_and_keeps_the_old_ui(self):
        lines = []
        with mock.patch.object(ui, "react_ready", return_value=False), \
                mock.patch("shutil.which", return_value=None):
            self.assertFalse(ui.build_react(log=lines.append))
        self.assertTrue(any("Node" in x for x in lines), lines)


if __name__ == "__main__":
    unittest.main()
