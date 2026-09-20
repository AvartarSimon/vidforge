"""env.save(): writes/updates one KEY=value line in a project's .env without disturbing the
rest of the file, and applies it to os.environ immediately (vidforge/env.py)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vidforge import env


class Save(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.saved_environ = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_environ)

    def test_creates_env_file_when_missing(self):
        f = env.save(self.td, "PEXELS_API_KEY", "abc123")
        self.assertEqual(f, self.td / ".env")
        self.assertEqual(f.read_text(encoding="utf-8").strip(), "PEXELS_API_KEY=abc123")
        self.assertEqual(os.environ["PEXELS_API_KEY"], "abc123")

    def test_appends_new_key_keeping_existing_lines(self):
        (self.td / ".env").write_text("SOMETHING_ELSE=1\n", encoding="utf-8")
        env.save(self.td, "PEXELS_API_KEY", "abc123")
        lines = (self.td / ".env").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["SOMETHING_ELSE=1", "PEXELS_API_KEY=abc123"])

    def test_updates_existing_key_in_place_not_duplicated(self):
        (self.td / ".env").write_text("PEXELS_API_KEY=old\nOTHER=1\n", encoding="utf-8")
        env.save(self.td, "PEXELS_API_KEY", "new")
        lines = (self.td / ".env").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["PEXELS_API_KEY=new", "OTHER=1"])

    def test_does_not_require_the_key_be_in_the_known_KEYS_registry(self):
        # save() itself is unrestricted; the UI/route layer is what limits it to env.KEYS
        env.save(self.td, "SOME_RANDOM_KEY", "x")
        self.assertEqual(os.environ["SOME_RANDOM_KEY"], "x")


class ApiRoute(unittest.TestCase):
    """POST /api/env only accepts known key names and writes into the *open* project's .env."""

    def setUp(self):
        import shutil
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer
        import json as jsonmod

        from vidforge import ui

        self.jsonmod = jsonmod
        self.urllib_request = urllib.request
        self.shutil = shutil
        self.td = Path(tempfile.mkdtemp())
        root = self.td / "proj"
        (root / "assets").mkdir(parents=True)
        (root / "project.json").write_text(jsonmod.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.root = root
        self.state = ui.State(root / "project.json")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.state))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.saved_environ = dict(os.environ)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.shutil.rmtree(self.td, ignore_errors=True)
        os.environ.clear()
        os.environ.update(self.saved_environ)

    def call(self, path, body):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = self.jsonmod.dumps(body).encode()
        req = self.urllib_request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with self.urllib_request.urlopen(req) as r:
                return r.status, self.jsonmod.loads(r.read() or b"{}")
        except Exception as e:  # noqa: BLE001 — urllib.error.HTTPError
            return e.code, self.jsonmod.loads(e.read() or b"{}")

    def test_rejects_unknown_key(self):
        st, j = self.call("/api/env", {"key": "NOT_A_REAL_KEY", "value": "x"})
        self.assertNotEqual(st, 200)
        self.assertIn("error", j)

    def test_rejects_empty_value(self):
        st, j = self.call("/api/env", {"key": "PEXELS_API_KEY", "value": "  "})
        self.assertNotEqual(st, 200)

    def test_writes_into_the_open_projects_env_file(self):
        st, j = self.call("/api/env", {"key": "PEXELS_API_KEY", "value": "sekrit"})
        self.assertEqual(st, 200)
        self.assertEqual((self.root / ".env").read_text(encoding="utf-8").strip(), "PEXELS_API_KEY=sekrit")


if __name__ == "__main__":
    unittest.main()
