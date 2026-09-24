"""Locate and run ffmpeg / ffprobe."""

from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def find_binary(name: str) -> str:
    """Resolve `ffmpeg` / `ffprobe`.

    Order: VIDFORGE_FFMPEG_DIR env var -> PATH -> winget install folder (Windows)
    -> Homebrew (macOS).
    """
    env_dir = os.environ.get("VIDFORGE_FFMPEG_DIR")
    exe = name + (".exe" if platform.system() == "Windows" else "")
    if env_dir and (Path(env_dir) / exe).exists():
        return str(Path(env_dir) / exe)

    found = shutil.which(name)
    if found:
        return found

    candidates: list[str] = []
    if platform.system() == "Windows":
        candidates += glob.glob(
            os.path.expandvars(
                r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\\" + exe
            )
        )
        candidates += [r"C:\ffmpeg\bin\\" + exe]
    else:
        candidates += ["/opt/homebrew/bin/" + name, "/usr/local/bin/" + name]

    for c in candidates:
        if Path(c).exists():
            return c

    raise FfmpegError(
        f"{name} not found. Install it (Windows: `winget install Gyan.FFmpeg`; "
        f"macOS: `brew install ffmpeg`) or set VIDFORGE_FFMPEG_DIR."
    )


def run(args: list[str], *, quiet: bool = True) -> None:
    """Run ffmpeg with the given arguments (without the leading binary)."""
    cmd = [find_binary("ffmpeg"), "-hide_banner", "-nostdin"]
    if quiet:
        cmd += ["-loglevel", "error"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FfmpegError(
            "ffmpeg failed (exit %d)\n  cmd: %s\n  stderr:\n%s"
            % (proc.returncode, " ".join(_quote(a) for a in cmd), proc.stderr.strip())
        )


def duration(path: str | Path) -> float:
    """Media duration in seconds via ffprobe."""
    cmd = [
        find_binary("ffprobe"), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed on {path}:\n{proc.stderr.strip()}")
    return float(json.loads(proc.stdout)["format"]["duration"])


def video_size(path: str | Path) -> tuple[int, int]:
    """(width, height) of a file's first video stream, via ffprobe."""
    cmd = [find_binary("ffprobe"), "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height", "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed on {path}:\n{proc.stderr.strip()}")
    streams = json.loads(proc.stdout).get("streams") or []
    if not streams:
        raise FfmpegError(f"no video stream in {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])


def filter_path(path: str | Path) -> str:
    """Escape a filesystem path for use inside an ffmpeg filter option (e.g. subtitles=)."""
    p = str(Path(path).resolve()).replace("\\", "/")
    # In a filter graph ':' separates options and '\' escapes; both must be escaped.
    p = p.replace(":", "\\:")
    return p


def _quote(a: str) -> str:
    return f'"{a}"' if " " in a else a


def print_versions() -> None:
    for name in ("ffmpeg", "ffprobe"):
        try:
            b = find_binary(name)
            out = subprocess.run([b, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
            print(f"{name}: {b}\n  {out}")
        except FfmpegError as e:
            print(f"{name}: NOT FOUND — {e}", file=sys.stderr)
