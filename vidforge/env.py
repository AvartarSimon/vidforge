"""API keys come from the environment, never from project.json.

`load_dotenv()` reads `KEY=value` lines from the first `.env` found in: the project
directory, the current directory, the vidforge repository root. Existing environment
variables win over the file.
"""

from __future__ import annotations

import os
from pathlib import Path

KEYS = {
    "ELEVENLABS_API_KEY": "ElevenLabs TTS (https://elevenlabs.io -> Profile -> API keys)",
    "PEXELS_API_KEY": "Pexels stock photos/videos (https://www.pexels.com/api/)",
    "PIXABAY_API_KEY": "Pixabay stock photos/videos (https://pixabay.com/api/docs/)",
    "YOUTUBE_API_KEY": "YouTube Data API v3, for exact competitor-video stats (https://console.cloud.google.com/apis/credentials)",
    "SYNC_API_KEY": "sync.so lip-sync API (https://sync.so)",
}


def load_dotenv(*dirs: Path) -> Path | None:
    candidates = [Path(d) for d in dirs] + [Path.cwd(), Path(__file__).resolve().parent.parent]
    for d in candidates:
        f = d / ".env"
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            return f
    return None


def save(target_dir: Path, key: str, value: str) -> Path:
    """Write/update one KEY=value line in <target_dir>/.env, preserving every other line, and
    set it in os.environ immediately so it takes effect without restarting the server."""
    f = Path(target_dir) / ".env"
    lines = f.read_text(encoding="utf-8").splitlines() if f.is_file() else []
    line = f"{key}={value}"
    for i, existing in enumerate(lines):
        k = existing.split("=", 1)[0].strip()
        if k == key:
            lines[i] = line
            break
    else:
        lines.append(line)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value
    return f


def require(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        hint = KEYS.get(name, "")
        raise RuntimeError(
            f"{name} is not set. Put `{name}=...` in a .env file next to project.json "
            f"(or in the vidforge folder) or export it. {hint}"
        )
    return v
