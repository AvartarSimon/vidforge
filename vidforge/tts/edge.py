"""edge-tts provider: Microsoft Edge neural voices, free, no API key.

Caveat: this is an unofficial endpoint and may change; keep the cache so a
finished video never depends on it being up.

Word boundaries arrive as stream chunks {"type": "WordBoundary", "offset", "duration",
"text"} with times in 100-nanosecond ticks. We accumulate them ourselves rather than
using edge_tts.SubMaker, whose API changed between major versions. edge-tts 7.x only
emits them when `boundary="WordBoundary"` is requested.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import edge_tts

from . import Word

TICKS_PER_SECOND = 10_000_000


class EdgeProvider:
    name = "edge"

    def __init__(self, rate: str = "+0%"):
        self.rate = rate

    def cache_key(self, text: str, voice: str) -> str:
        return hashlib.sha1(f"wb1|{voice}|{self.rate}|{text}".encode("utf-8")).hexdigest()[:16]

    def synthesize(self, text: str, voice: str, out_path: Path) -> list[Word]:
        return asyncio.run(self._synth(text, voice, out_path))

    async def _synth(self, text: str, voice: str, out_path: Path) -> list[Word]:
        communicate = edge_tts.Communicate(text, voice, rate=self.rate, boundary="WordBoundary")
        words: list[Word] = []
        with open(out_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    words.append(Word(
                        text=chunk["text"],
                        start=chunk["offset"] / TICKS_PER_SECOND,
                        duration=chunk["duration"] / TICKS_PER_SECOND,
                    ))
        if out_path.stat().st_size == 0:
            raise RuntimeError(f"edge-tts returned no audio for voice '{voice}'")
        return words

    def list_voices(self, lang_prefix: str | None) -> list[tuple[str, str]]:
        voices = asyncio.run(edge_tts.list_voices())
        if lang_prefix:
            voices = [v for v in voices if v["Locale"].lower().startswith(lang_prefix.lower())]
        voices.sort(key=lambda v: (v["Locale"], v["ShortName"]))
        return [(v["ShortName"], f'{v["Gender"]:<7} {",".join(v.get("VoiceTag", {}).get("VoicePersonalities", []))}')
                for v in voices]
