"""ElevenLabs provider — paid, the de-facto standard for English faceless channels.

Uses `POST /v1/text-to-speech/{voice_id}/with-timestamps`, which returns the mp3 plus a
character-level alignment; we fold characters into words (one word per CJK glyph so
Chinese subtitles can still break). Key: ELEVENLABS_API_KEY (see env.py).

`voice` may be a voice_id or a voice name from your library ("Brian", "Rachel", …).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import env
from . import Word

API = "https://api.elevenlabs.io/v1"
_VOICE_ID = re.compile(r"^[A-Za-z0-9]{20,}$")


class ElevenLabsError(RuntimeError):
    pass


def _is_cjk(ch: str) -> bool:
    return "CJK" in unicodedata.name(ch, "")


def alignment_to_words(alignment: dict) -> list[Word]:
    """Fold ElevenLabs' character alignment into words.

    A word is a run of non-whitespace characters; a CJK character is a word on its own.
    """
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words: list[Word] = []
    buf: list[str] = []
    w_start = w_end = 0.0

    def flush() -> None:
        nonlocal buf
        if buf:
            words.append(Word(text="".join(buf), start=w_start, duration=max(0.0, w_end - w_start)))
            buf = []

    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            flush()
            continue
        if _is_cjk(ch):
            flush()
            words.append(Word(text=ch, start=s, duration=max(0.0, e - s)))
            continue
        if not buf:
            w_start = s
        buf.append(ch)
        w_end = e
    flush()
    return words


def rate_to_speed(rate: str) -> float:
    """edge-tts style "+10%" -> ElevenLabs voice_settings.speed (0.7 … 1.2)."""
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%\s*", rate or "+0%")
    pct = float(m.group(1)) if m else 0.0
    return round(min(1.2, max(0.7, 1 + pct / 100)), 3)


class ElevenLabsProvider:
    name = "elevenlabs"

    def __init__(self, rate: str = "+0%", model: str = "eleven_multilingual_v2",
                 stability: float = 0.5, similarity_boost: float = 0.75, style: float = 0.0,
                 speaker_boost: bool = True, output_format: str = "mp3_44100_128", **_: object):
        self.model = model
        self.speed = rate_to_speed(rate)
        self.settings = {
            "stability": stability, "similarity_boost": similarity_boost,
            "style": style, "use_speaker_boost": speaker_boost, "speed": self.speed,
        }
        self.output_format = output_format
        self._voices: list[dict] | None = None

    # -- HTTP -------------------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
        url = f"{API}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "xi-api-key": env.require("ELEVENLABS_API_KEY"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            hint = {401: "invalid API key", 402: "quota exceeded / payment required",
                    422: "bad request (unknown voice/model?)", 429: "rate limited"}.get(e.code, "")
            raise ElevenLabsError(f"ElevenLabs {method} {path} -> HTTP {e.code} {hint}\n{detail}") from None
        except urllib.error.URLError as e:
            raise ElevenLabsError(f"ElevenLabs unreachable: {e.reason}") from None

    # -- provider contract -------------------------------------------------------
    def cache_key(self, text: str, voice: str) -> str:
        blob = json.dumps([self.model, self.settings, self.output_format, voice, text], sort_keys=True)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]

    def resolve_voice(self, voice: str) -> str:
        if _VOICE_ID.match(voice):
            return voice
        for v in self._all_voices():
            if v["name"].lower() == voice.lower():
                return v["voice_id"]
        names = ", ".join(v["name"] for v in self._all_voices())
        raise ElevenLabsError(f"voice '{voice}' not found in your ElevenLabs library. Available: {names}")

    def synthesize(self, text: str, voice: str, out_path: Path) -> list[Word]:
        voice_id = self.resolve_voice(voice)
        resp = self._request(
            "POST", f"/text-to-speech/{voice_id}/with-timestamps",
            body={"text": text, "model_id": self.model, "voice_settings": self.settings},
            query={"output_format": self.output_format},
        )
        audio = base64.b64decode(resp["audio_base64"])
        if not audio:
            raise ElevenLabsError("ElevenLabs returned empty audio")
        Path(out_path).write_bytes(audio)
        alignment = resp.get("alignment") or resp.get("normalized_alignment")
        if not alignment:
            return []
        return alignment_to_words(alignment)

    def _all_voices(self) -> list[dict]:
        if self._voices is None:
            self._voices = self._request("GET", "/voices").get("voices", [])
        return self._voices

    def list_voices(self, lang_prefix: str | None) -> list[tuple[str, str]]:
        out = []
        for v in self._all_voices():
            labels = v.get("labels") or {}
            desc = " ".join(str(labels.get(k, "")) for k in ("gender", "age", "accent", "use_case", "description"))
            if lang_prefix and lang_prefix.lower() not in (desc + v.get("name", "")).lower():
                continue
            out.append((f'{v["name"]} ({v["voice_id"]})', f'{v.get("category", ""):<12} {desc.strip()}'))
        return out
