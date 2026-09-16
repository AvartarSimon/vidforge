"""edge-tts provider: Microsoft Edge neural voices, free, no API key.

Caveat: this is an unofficial endpoint and may change; keep the cache so a
finished video never depends on it being up.

Word boundaries arrive as stream chunks {"type": "WordBoundary", "offset", "duration",
"text"} with times in 100-nanosecond ticks. We accumulate them ourselves rather than
using edge_tts.SubMaker, whose API changed between major versions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import edge_tts

from . import Word

TICKS_PER_SECOND = 10_000_000


async def _synth(text: str, voice: str, rate: str, out_path: Path) -> list[Word]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
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


def cache_key(text: str, voice: str, rate: str) -> str:
    return hashlib.sha1(f"wb1|{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:16]


def synthesize(text: str, voice: str, rate: str, out_path: Path) -> list[Word]:
    """Synthesize `text` to `out_path` (mp3). Cached: if a sidecar .json next to the
    audio carries the same key, the network is not touched."""
    out_path = Path(out_path)
    meta_path = out_path.with_suffix(".json")
    key = cache_key(text, voice, rate)

    if out_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("key") == key and meta.get("words"):
                return [Word(**w) for w in meta["words"]]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # corrupt sidecar -> regenerate

    out_path.parent.mkdir(parents=True, exist_ok=True)
    words = asyncio.run(_synth(text, voice, rate, out_path))
    meta_path.write_text(json.dumps({
        "key": key, "voice": voice, "rate": rate,
        "words": [w.__dict__ for w in words],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return words


def list_voices(lang_prefix: str | None = None) -> list[dict]:
    voices = asyncio.run(edge_tts.list_voices())
    if lang_prefix:
        voices = [v for v in voices if v["Locale"].lower().startswith(lang_prefix.lower())]
    return sorted(voices, key=lambda v: (v["Locale"], v["ShortName"]))
