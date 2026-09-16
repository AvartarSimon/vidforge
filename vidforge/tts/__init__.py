"""TTS providers. Each provider returns the audio file plus word-level timings.

Provider contract:
    synthesize(text, voice, rate, out_path) -> list[Word]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Word:
    text: str
    start: float     # seconds from the start of this segment's audio
    duration: float
    break_after: bool = False   # a clause/sentence boundary follows (set by subtitles.restore_punctuation)

    @property
    def end(self) -> float:
        return self.start + self.duration
