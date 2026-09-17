"""ui.serve()'s port-conflict handling.

Two `vidforge start` launches on the same port used to silently double-bind on Windows (HTTPServer
sets allow_reuse_address=True, which Windows honours even for a genuinely occupied port) — requests
would then route unpredictably between an old, possibly stale-code process and the new one. Fixed
by disabling reuse and, on a real conflict, either reusing an already-healthy vidforge instance or
falling back to the next free port instead of erroring or double-binding."""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from vidforge import ui


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ReuseExistingInstance(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
