"""'silent' provider: no network, no voice — silence of the length the narration *would* take,
with evenly spaced word timings so subtitles still render. For layout previews, stress tests
(a 30-minute build in minutes) and offline work. Swap `tts.provider` back to edge/elevenlabs
for the real thing; the audio cache is keyed by provider so nothing is mixed up."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

from .. import ffmpeg
from . import Word

WORDS_PER_SECOND = 2.6        # unhurried English narration
CJK_CHARS_PER_SECOND = 3.8


def estimate_seconds(text: str) -> float:
    cjk = sum(1 for ch in text if "CJK" in unicodedata.name(ch, ""))
    words = len(text.split())
    if cjk > len(text) * 0.3:
        return max(1.0, cjk / CJK_CHARS_PER_SECOND)
    return max(1.0, words / WORDS_PER_SECOND)


class SilentProvider:
    name = "silent"

    def __init__(self, rate: str = "+0%"):
        self.rate = rate

    def cache_key(self, text: str, voice: str) -> str:
        return hashlib.sha1(f"silent1|{text}".encode("utf-8")).hexdigest()[:16]

    def synthesize(self, text: str, voice: str, out_path: Path) -> list[Word]:
        secs = estimate_seconds(text)
        ffmpeg.run(["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{secs:.3f}",
                    "-c:a", "libmp3lame", "-b:a", "64k", str(out_path)])
        tokens = text.split() or [text]
        if len(tokens) == 1 and len(text) > 8:          # CJK: one token per character
            tokens = [ch for ch in text if not ch.isspace()]
        step = secs / max(1, len(tokens))
        return [Word(text=t, start=i * step, duration=step * 0.9) for i, t in enumerate(tokens)]

    def list_voices(self, lang_prefix: str | None) -> list[tuple[str, str]]:
        return [("silent", "no audio — layout preview")]
