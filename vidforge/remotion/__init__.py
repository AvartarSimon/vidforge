"""Remotion segments: animated graphics (title cards, timelines, charts) rendered by the
bundled Remotion project in ./app, then treated like any video background.

Segment shape:
    { "id": "vei", "text": "…", "remotion": { "composition": "BarChart", "props": { … } } }

The composition's length is the narration length: vidforge injects durationInFrames, fps,
width and height into the props; `Root.tsx` reads them in calculateMetadata. Rendered clips
are cached by a hash of (composition, props, size) in build/remotion/.

Requirements: Node.js >= 18 and one `vidforge remotion-setup` (npm install, downloads a
headless Chrome on first render). Remotion is free for individuals and companies of up to
three people; larger companies need a company license (remotion.dev/license).
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / "app"
COMPOSITIONS = ("TitleCard", "Timeline", "BarChart")


class RemotionError(RuntimeError):
    pass


def _bin(name: str) -> str:
    exe = shutil.which(name) or shutil.which(name + ".cmd")
    if not exe:
        raise RemotionError(f"{name} not found — install Node.js >= 18 (https://nodejs.org) and reopen the terminal")
    return exe


def _remotion_cli() -> list[str]:
    ext = ".cmd" if platform.system() == "Windows" else ""
    cli = APP_DIR / "node_modules" / ".bin" / f"remotion{ext}"
    if not cli.exists():
        raise RemotionError("Remotion is not installed yet — run `vidforge remotion-setup` once (needs Node.js)")
    return [str(cli)]


def setup(log=print) -> None:
    """npm install in the bundled app (once; ~250 packages, ~1 min)."""
    npm = _bin("npm")
    log(f"[remotion] npm install in {APP_DIR}")
    proc = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"],
                          cwd=APP_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RemotionError(f"npm install failed:\n{proc.stderr.strip()[-2000:]}")
    log("[remotion] ok — the first render also downloads a headless Chrome (~150 MB)")


def studio() -> None:
    """Open Remotion Studio to tweak compositions interactively."""
    subprocess.run(_remotion_cli() + ["studio", "src/index.ts"], cwd=APP_DIR)


def render(composition: str, props: dict, *, duration: float, fps: int, width: int, height: int,
           out_dir: Path, log=print) -> Path:
    if composition not in COMPOSITIONS:
        raise RemotionError(f"unknown composition '{composition}'; available: {', '.join(COMPOSITIONS)}")
    full = dict(props)
    full.update({"durationInFrames": max(1, round(duration * fps)), "fps": fps, "width": width, "height": height})
    key = hashlib.sha1(json.dumps([composition, full], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{composition}-{key}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out

    props_file = out.with_suffix(".props.json")
    props_file.write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
    cmd = _remotion_cli() + ["render", "src/index.ts", composition, str(out),
                             f"--props={props_file}", "--codec=h264", "--log=error"]
    log(f"[remotion] rendering {composition} ({full['durationInFrames']} frames)")
    proc = subprocess.run(cmd, cwd=APP_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not out.exists():
        raise RemotionError(f"remotion render failed ({composition}):\n{(proc.stderr or proc.stdout).strip()[-3000:]}")
    return out
