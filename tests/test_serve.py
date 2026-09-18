"""ui.serve()'s port-conflict handling.

Two `vidforge start` launches on the same port used to silently double-bind on Windows (HTTPServer
sets allow_reuse_address=True, which Windows honours even for a genuinely occupied port) — requests
would then route unpredictably between an old, possibly stale-code process and the new one. Fixed
by disabling reuse and, on a real conflict, either reusing an already-healthy vidforge instance or
falling back to the next free port instead of erroring or double-binding."""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from vidforge import ui


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ReuseExistingInstance(unittest.TestCase):
    def setUp(self):
        # serve()/State touch ~/.vidforge (recent-projects list, history) — isolate that from
        # the real one so a test run doesn't leave temp-directory clutter in the user's actual
        # "recent projects" file.
        self.config_dir = Path(tempfile.mkdtemp()) / "vidforge-config"
        self.patches = [mock.patch.object(ui, "CONFIG_DIR", self.config_dir),
                        mock.patch.object(ui, "RECENT", self.config_dir / "recent.json")]
        for p in self.patches:
            p.start()
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        (self.td / "project.json").write_text(json.dumps({"title": "T", "segments": []}), encoding="utf-8")
        self.port = _free_port()
        self.thread = threading.Thread(target=ui.serve, args=(str(self.td),), kwargs={"port": self.port, "open_browser": False}, daemon=True)
        self.thread.start()
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=0.5)
                break
            except Exception:
                time.sleep(0.1)
        else:
            self.fail("server never came up")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.td, ignore_errors=True)
        shutil.rmtree(self.config_dir.parent, ignore_errors=True)

    def test_second_serve_call_reuses_the_running_instance_instead_of_erroring(self):
        # a second `serve()` on the same port must return promptly (not block, not raise, not
        # silently double-bind) once it notices a healthy vidforge is already there.
        t0 = time.time()
        ui.serve(str(self.td), port=self.port, open_browser=False)
        self.assertLess(time.time() - t0, 5.0)
        # the original instance is still the one actually answering
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=2) as r:
            self.assertIn("ffmpeg", json.loads(r.read()))


class PortIsOurs(unittest.TestCase):
    def test_false_for_a_plain_closed_port(self):
        self.assertFalse(ui._port_is_ours(_free_port(), timeout=0.3))

    def test_false_for_a_non_vidforge_listener(self):
        port = _free_port()
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", port)); srv.listen(1)
        try:
            self.assertFalse(ui._port_is_ours(port, timeout=0.3))
        finally:
            srv.close()

    def test_disables_reuse_address_so_windows_cannot_silently_double_bind(self):
        self.assertFalse(ui._Server.allow_reuse_address)


class SpawnInstance(unittest.TestCase):
    """spawn_instance() launches a genuinely separate `vidforge ui` process so two projects can
    render/edit in parallel — this server has exactly one build slot and one current project by
    design (see ReuseExistingInstance above), so real concurrency means a second process."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        (self.td / "assets").mkdir()
        (self.td / "project.json").write_text(json.dumps({"title": "spawned", "segments": []}), encoding="utf-8")
        self.url: str | None = None

    def tearDown(self):
        if self.url:
            port = int(self.url.rstrip("/").rsplit(":", 1)[1])
            self._kill_by_port(port)   # spawn_instance() starts a real detached process — clean it up
        shutil.rmtree(self.td, ignore_errors=True)

    @staticmethod
    def _kill_by_port(port: int) -> None:
        try:
            import subprocess
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
        except Exception:  # noqa: BLE001 — best-effort cleanup, never fail the test over it
            pass

    def test_spawns_a_real_independent_process_serving_the_given_project(self):
        self.url = ui.spawn_instance(self.td, timeout=30.0)
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))
        with urllib.request.urlopen(self.url + "api/health", timeout=3) as r:
            health = json.loads(r.read())
        self.assertIn("ffmpeg", health)
        with urllib.request.urlopen(self.url + "api/project", timeout=3) as r:
            proj = json.loads(r.read())
        self.assertEqual(proj["raw"]["title"], "spawned")

    def test_raises_a_clear_error_for_a_nonexistent_project(self):
        # the spawned process exits almost immediately (SystemExit: project file not found), so
        # it never answers /api/health — a short timeout is enough to prove spawn_instance()
        # surfaces that as an error instead of hanging or returning a dead URL.
        with self.assertRaises(RuntimeError):
            ui.spawn_instance(self.td / "does-not-exist", timeout=5.0)


if __name__ == "__main__":
    unittest.main()
