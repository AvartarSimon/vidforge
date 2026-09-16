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


def require(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        hint = KEYS.get(name, "")
        raise RuntimeError(
            f"{name} is not set. Put `{name}=...` in a .env file next to project.json "
            f"(or in the vidforge folder) or export it. {hint}"
        )
    return v
