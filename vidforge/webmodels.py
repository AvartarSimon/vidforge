"""Model files for the in-browser camera effects (人像分割 / 人脸关键点), fetched once on first use.

The effects run in the browser — the take being recorded *is* the processed canvas, so what you see
in the preview is what lands in the file. The browser cannot write to ~/.vidforge, so the backend
downloads each model there the first time a page asks for it and serves it from disk afterwards,
the same way `video/heads.py` handles YuNet. Nothing about the picture ever leaves the machine:
only the model file comes down.

The WASM runtime is not here: it ships inside the `@mediapipe/tasks-vision` npm package that the
UI build already installed, so the backend serves it straight out of node_modules.
"""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

MODEL_DIR = Path.home() / ".vidforge" / "models"

_BASE = "https://storage.googleapis.com/mediapipe-models"
# name -> (url, minimum plausible size). Apache-2.0 models published by Google for MediaPipe.
MODELS: dict[str, tuple[str, int]] = {
    # background / hair / body-skin / face-skin / clothes / other: one pass gives the person mask
    # for background swap, a real skin mask for 磨皮 (so the background is never smoothed), and the
    # clothes and hair masks for recolouring
    "selfie_multiclass_256x256.tflite": (
        f"{_BASE}/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite",
        10_000_000),
    # 478-point face mesh: eye centres for 大眼, jaw line for 瘦脸
    "face_landmarker.task": (
        f"{_BASE}/face_landmarker/face_landmarker/float16/latest/face_landmarker.task", 3_000_000),
}

_lock = threading.Lock()


class ModelError(RuntimeError):
    pass


def path(name: str, log=print) -> Path:
    """Local copy of a known model, downloading it the first time."""
    if name not in MODELS:
        raise ModelError(f"unknown model '{name}'")
    url, min_size = MODELS[name]
    dest = MODEL_DIR / name
    # two tabs opening the studio at once must not both write the same file
    with _lock:
        if dest.is_file() and dest.stat().st_size >= min_size:
            return dest
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        log(f"[vidforge] 第一次使用：下载模型 {name} …")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise ModelError(f"模型下载失败（{e}）。可手动下载 {url} 放到 {dest}") from e
        if tmp.stat().st_size < min_size:
            tmp.unlink(missing_ok=True)
            raise ModelError(f"下载到的模型文件不完整。可手动下载 {url} 放到 {dest}")
        tmp.replace(dest)
        return dest


def wasm_dir() -> Path | None:
    """Where the MediaPipe WASM runtime lives: the UI's node_modules (present wherever the UI was built)."""
    d = Path(__file__).resolve().parent / "ui" / "react" / "node_modules" / "@mediapipe" / "tasks-vision" / "wasm"
    return d if d.is_dir() else None
