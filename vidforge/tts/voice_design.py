"""Design a brand voice from a text description (ElevenLabs Voice Design).

No real person is cloned: the model synthesises a new voice that matches the description
("deep, warm, magnetic male narrator in his forties, unhurried, slight British colour").
Three previews come back; keep one and it becomes a voice_id usable everywhere in vidforge.

    vidforge voice design --desc "…" [--text "…"]          -> saves previews to ~/.vidforge/voices/
    vidforge voice keep <generated_voice_id> --name "Narrator"   -> prints the voice_id

Endpoints: POST /v1/text-to-voice/design and POST /v1/text-to-voice (2025 API); the older
/create-previews + /create-voice-from-preview pair is tried when the new ones 404.
Requires ELEVENLABS_API_KEY (Creator plan or above for Voice Design). ⚠ Not exercised here.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .. import env

API = "https://api.elevenlabs.io/v1"
SAMPLE_EN = ("In April 1815, on an island most Europeans had never heard of, a mountain tore itself apart. "
             "Within a year, snow was falling in June and the harvests of two continents had failed.")
SAMPLE_ZH = "一八一五年四月，在一个多数欧洲人从未听说过的岛上，一座山把自己撕开了。一年之内，六月飘雪，两个大陆的收成全部落空。"


class VoiceDesignError(RuntimeError):
    pass


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"xi-api-key": env.require("ELEVENLABS_API_KEY"), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise VoiceDesignError(f"ElevenLabs {path} -> HTTP {e.code}: {detail}") from None


def design(description: str, text: str | None = None, out_dir: Path | None = None) -> list[dict]:
    """-> [{generated_voice_id, audio (Path), duration}] — three previews of the described voice."""
    text = (text or "").strip() or (SAMPLE_ZH if any("一" <= ch <= "鿿" for ch in description) else SAMPLE_EN)
    if len(text) < 100:
        text = (text + " ") * (100 // max(1, len(text)) + 1)      # the API wants >= 100 characters
    body = {"voice_description": description, "text": text}
    try:
        data = _post("/text-to-voice/design", {**body, "model_id": "eleven_multilingual_ttv_v2"})
    except VoiceDesignError as e:
        if "404" not in str(e):
            raise
        data = _post("/text-to-voice/create-previews", body)
    out_dir = Path(out_dir or (Path.home() / ".vidforge" / "voices"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    result = []
    for i, p in enumerate(data.get("previews", [])):
        f = out_dir / f"design_{stamp}_{i + 1}.mp3"
        f.write_bytes(base64.b64decode(p["audio_base64"]))
        result.append({"generated_voice_id": p["generated_voice_id"], "audio": f, "duration": p.get("duration_secs")})
    if not result:
        raise VoiceDesignError("ElevenLabs returned no previews")
    return result


def keep(generated_voice_id: str, name: str, description: str) -> str:
    """Save a preview as a permanent voice; returns its voice_id."""
    body = {"voice_name": name, "voice_description": description, "generated_voice_id": generated_voice_id}
    try:
        data = _post("/text-to-voice", body)
    except VoiceDesignError as e:
        if "404" not in str(e):
            raise
        data = _post("/text-to-voice/create-voice-from-preview", body)
    return data["voice_id"]
