"""TTS providers. Each provider returns the audio file plus word-level timings.

Provider contract (see edge.py / elevenlabs.py):
    synthesize(text, voice, out_path) -> list[Word]
    list_voices(lang_prefix) -> list[(short_name, description)]
    cache_key(text, voice) -> str          # everything that changes the audio

`synthesize_cached` wraps a provider so a finished project never touches the
network again: a sidecar .json next to the mp3 stores the key and the words.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Protocol


@dataclass
class Word:
    text: str
    start: float     # seconds from the start of this segment's audio
    duration: float
    break_after: bool = False   # a clause/sentence boundary follows (set by subtitles.restore_punctuation)

    @property
    def end(self) -> float:
        return self.start + self.duration


class TtsProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, out_path: Path) -> list[Word]: ...
    def cache_key(self, text: str, voice: str) -> str: ...
    def list_voices(self, lang_prefix: str | None) -> list[tuple[str, str]]: ...


def synthesize_cached(provider: TtsProvider, text: str, voice: str, out_path: Path) -> list[Word]:
    out_path = Path(out_path)
    meta_path = out_path.with_suffix(".json")
    key = f"{provider.name}:{provider.cache_key(text, voice)}"

    if out_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("key") == key and meta.get("words"):
                return [Word(**w) for w in meta["words"]]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # corrupt sidecar -> regenerate

    out_path.parent.mkdir(parents=True, exist_ok=True)
    words = None
    for attempt in range(3):                      # edge-tts is an unofficial endpoint: transient failures happen
        try:
            words = provider.synthesize(text, voice, out_path)
            break
        except Exception as e:  # noqa: BLE001
            if attempt == 2 or "API key" in str(e) or "quota" in str(e).lower():
                raise
            import time as _t
            _t.sleep(2 * (attempt + 1))
    assert words is not None
    meta_path.write_text(json.dumps({
        "key": key, "provider": provider.name, "voice": voice,
        "words": [asdict(w) for w in words],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return words


def get_provider(name: str, **kwargs) -> TtsProvider:
    if name == "edge":
        from .edge import EdgeProvider
        return EdgeProvider(rate=kwargs.get("rate", "+0%"))
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsProvider
        return ElevenLabsProvider(rate=kwargs.get("rate", "+0%"), **kwargs.get("config", {}))
    if name == "silent":
        from .silent import SilentProvider
        return SilentProvider(rate=kwargs.get("rate", "+0%"))
    raise ValueError(f"unknown TTS provider '{name}'")
