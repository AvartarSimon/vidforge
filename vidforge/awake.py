"""Keep the computer from idle-sleeping while a long job runs.

A render or a picture run takes minutes with nobody touching the keyboard, and a laptop set to
sleep after a minute suspends it half-way: measured on a MacBook on 2026-11-17, a 90-second
autofill took 18 minutes, the machine waking for 45 seconds every quarter of an hour. Only the
system's idle sleep is held back — the display may still turn off, closing the lid still sleeps —
and only for as long as the job runs. `VIDFORGE_KEEP_AWAKE=0` turns it off.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from contextlib import contextmanager

_local = threading.local()      # Windows keeps this state per thread, so the nesting count is too

_ES_CONTINUOUS, _ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def _on():
    """Start holding; returns what _off() needs, or None when there is nothing to do here."""
    system = platform.system()
    if system == "Darwin":
        exe = shutil.which("caffeinate")
        if exe:
            # -w: caffeinate lets go by itself if vidforge dies without getting to _off()
            return subprocess.Popen([exe, "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif system == "Windows":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        return "win"
    return None                 # Linux desktops differ too much to guess; a server does not sleep


def _off(handle) -> None:
    if handle == "win":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    elif handle is not None:
        handle.terminate()


@contextmanager
def hold():
    """`with awake.hold():` around a job. Nests; never raises — a job must not fail over this."""
    depth = getattr(_local, "depth", 0)
    _local.depth = depth + 1
    handle = None
    if depth == 0 and os.environ.get("VIDFORGE_KEEP_AWAKE", "1") != "0":
        try:
            handle = _on()
        except Exception:  # noqa: BLE001
            handle = None
    try:
        yield
    finally:
        _local.depth = depth
        try:
            _off(handle)
        except Exception:  # noqa: BLE001
            pass
