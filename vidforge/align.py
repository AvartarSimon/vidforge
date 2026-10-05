"""Force-align a narration recording to the script it reads out.

TTS tells us where every word landed, which is what drives the subtitles, the keyword highlighting,
the chapter marks and the vertical re-cut. A recording of your own voice tells us nothing, so this
module recovers the same information: feed it the audio and the script, get back the same
`list[Word]` every TTS provider returns, and nothing downstream needs to know the difference.

Why not just use the transcription? Because the transcription is *wrong* in the ways that matter —
it mishears names, drops punctuation, writes 「二零二五」 where the script says 「2025」. The script
is the truth for what the subtitle says; Whisper is only consulted about *when*. So:

    script tokens  ──┐
                     ├─ difflib.SequenceMatcher on normalised keys ─→ times for matched tokens
    whisper tokens ──┘                                                 ─→ interpolate the rest

Unmatched script tokens get a time interpolated between their nearest matched neighbours, so a
misheard name borrows the timing of the words around it instead of breaking the whole track. The
result degrades gracefully: perfect where the transcription agrees, approximately right where it
does not, and never out of order.

faster-whisper is an optional dependency — it pulls in CTranslate2 and a model download, which a
user who only ever uses TTS has no reason to carry:

    pip install faster-whisper

Models cache in `~/.vidforge/models/whisper/`. `small` is the default: on Chinese it is clearly
better than `base` and the difference from `medium` does not show up in word *timings*, which is
all we take from it. Override with `VIDFORGE_WHISPER_MODEL`. CPU is fine here — unlike TTS this
runs once per recording, and a 60 s take takes a few seconds on `small`.
"""

from __future__ import annotations

import difflib
import os
import re
import unicodedata
from pathlib import Path

from . import ffmpeg
from .tts import Word

MODELS_DIR = Path.home() / ".vidforge" / "models" / "whisper"
DEFAULT_MODEL = "small"

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿぀-ヿ]")
_STRIP = "“”„‟\"'‘’`()[]{}<>《》〈〉「」『』,，.。!！?？:：;；、…—–-·~～ \t\n"
_model = None


class AlignError(RuntimeError):
    pass


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _load_model():
    """Loaded once per process: the model costs seconds to load and nothing to keep."""
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise AlignError(
            "字幕对齐需要 faster-whisper，这台机器上没装。装一次就好：pip install faster-whisper"
            "（模型会下载到 ~/.vidforge/models/whisper/，CPU 够用）"
        ) from None
    name = os.environ.get("VIDFORGE_WHISPER_MODEL", DEFAULT_MODEL)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    _model = WhisperModel(name, device="auto", compute_type="int8",
                          download_root=str(MODELS_DIR))
    return _model


def is_cjk(text: str) -> bool:
    letters = [c for c in text if c.isalpha() or _CJK.match(c)]
    if not letters:
        return False
    return sum(bool(_CJK.match(c)) for c in letters) > len(letters) * 0.3


# Whisper writes a spoken year as digits; a script for this channel writes it either way. Mapping
# the plain numerals (not 百/十, which need parsing, not substitution) makes 「二零二一」 match 「2021」.
_DIGITS = str.maketrans("零〇一二三四五六七八九", "00123456789")


def _key(token: str) -> str:
    """What two tokens have to share to count as the same word.

    Width matters: Whisper writes full-width ＡＢＣ and ０１２ for Chinese audio often enough that
    comparing them raw would miss every number in the script."""
    t = unicodedata.normalize("NFKC", token).strip(_STRIP).lower()
    return re.sub(r"\s+", "", t).translate(_DIGITS)


def tokenize(text: str) -> list[str]:
    """The units a subtitle is built from: characters for CJK, whitespace words otherwise."""
    if is_cjk(text):
        return [c for c in text if not c.isspace() and c not in _STRIP]
    return [t for t in text.split() if _key(t)]


def _spread(token: str, start: float, end: float, cjk: bool) -> list[tuple[str, float, float]]:
    """One Whisper word becomes several script-sized tokens, sharing its span."""
    if not cjk:
        return [(token, start, end)]
    chars = [c for c in token if not c.isspace() and c not in _STRIP]
    if not chars:
        return []
    step = (end - start) / len(chars)
    return [(c, start + i * step, start + (i + 1) * step) for i, c in enumerate(chars)]


def _samples(audio: Path):
    """Decode to the mono 16 kHz float array Whisper wants, using ffmpeg rather than PyAV.

    faster-whisper would happily open the file itself, but it does so through PyAV, and PyAV 19
    removed the `metadata_errors` argument that faster-whisper 1.2 still passes — the pair simply
    raises TypeError. vidforge already requires ffmpeg and already decodes audio everywhere else,
    so handing Whisper an array sidesteps that version pairing instead of pinning around it."""
    import numpy as np

    raw = ffmpeg.pcm(audio, rate=16000)
    if not raw:
        return np.zeros(0, dtype="float32")
    return np.frombuffer(raw, dtype="<f4").astype("float32")


def transcribe(audio: Path, lang: str | None = None) -> list[tuple[str, float, float]]:
    """Whisper's own words with timestamps, flattened to (text, start, end)."""
    model = _load_model()
    data = _samples(audio)
    if not len(data):
        return []
    segments, _info = model.transcribe(data, language=lang, word_timestamps=True,
                                       vad_filter=True, beam_size=5)
    out: list[tuple[str, float, float]] = []
    for seg in segments:
        for w in (seg.words or []):
            if w.word and w.word.strip():
                out.append((w.word.strip(), float(w.start), float(w.end)))
    return out


def even_spread(text: str, seconds: float) -> list[Word]:
    """The fallback when alignment is unavailable: tokens shared evenly over the real length.

    The same thing VoxCPM does for lack of a timestamp API. At normal narration pace the cue
    breaks land close to right; they are not frame-accurate."""
    tokens = tokenize(text)
    if not tokens or seconds <= 0:
        return []
    step = seconds / len(tokens)
    return [Word(text=t, start=i * step, duration=step * 0.92) for i, t in enumerate(tokens)]


def align(audio: Path, text: str, *, lang: str | None = None, log=None) -> list[Word]:
    """Word timings for `text` as actually spoken in `audio`.

    Falls back to an even spread when faster-whisper is missing or hears nothing at all, so a
    build never fails just because alignment is unavailable."""
    audio = Path(audio)
    if not audio.is_file():
        raise AlignError(f"找不到音频：{audio}")
    seconds = ffmpeg.duration(audio)
    tokens = tokenize(text)
    if not tokens:
        return []

    if not available():
        if log:
            log("  没装 faster-whisper，字幕按时长平均摊（不会帧级准确）")
        return even_spread(text, seconds)

    heard = transcribe(audio, (lang or "")[:2] or None)
    if not heard:
        if log:
            log("  这段音频里没听到语音，字幕按时长平均摊")
        return even_spread(text, seconds)

    cjk = is_cjk(text)
    flat: list[tuple[str, float, float]] = []
    for token, start, end in heard:
        flat.extend(_spread(token, start, end, cjk))
    if not flat:
        return even_spread(text, seconds)

    matched = _match(tokens, flat)
    filled = _interpolate(matched, seconds)
    if log:
        hits = sum(1 for m in matched if m is not None)
        log(f"  对齐 {hits}/{len(tokens)} 个词命中转写（其余按相邻词插值）")
    return [Word(text=t, start=s, duration=max(0.01, e - s)) for t, (s, e) in zip(tokens, filled)]


def _match(tokens: list[str], flat: list[tuple[str, float, float]]) -> list[tuple[float, float] | None]:
    """Line the script up against the transcription; None where the transcription disagrees."""
    want = [_key(t) for t in tokens]
    got = [_key(t) for t, _, _ in flat]
    out: list[tuple[float, float] | None] = [None] * len(tokens)
    sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        for i in range(size):
            out[a + i] = (flat[b + i][1], flat[b + i][2])
    return out


def _interpolate(matched: list[tuple[float, float] | None], seconds: float) -> list[tuple[float, float]]:
    """Give every unmatched token a slot between its nearest matched neighbours.

    The gaps are shared evenly, which keeps the sequence monotonic — a subtitle track that goes
    backwards is worse than one that is slightly off."""
    n = len(matched)
    anchors = [i for i, m in enumerate(matched) if m is not None]
    if not anchors:
        step = seconds / n
        return [(i * step, (i + 1) * step) for i in range(n)]

    out: list[tuple[float, float] | None] = list(matched)

    # before the first anchor: walk backwards from it, never before zero
    first = anchors[0]
    if first > 0:
        end = matched[first][0]
        step = end / (first + 1)
        for i in range(first):
            out[i] = (i * step, (i + 1) * step)

    # after the last anchor: walk forwards to the end of the audio
    last = anchors[-1]
    if last < n - 1:
        start = matched[last][1]
        step = max(0.01, (seconds - start) / (n - last))
        for i in range(last + 1, n):
            k = i - last - 1
            out[i] = (start + k * step, start + (k + 1) * step)

    # the holes in between
    for a, b in zip(anchors, anchors[1:]):
        if b - a <= 1:
            continue
        start, end = matched[a][1], matched[b][0]
        step = max(0.0, end - start) / (b - a - 1) if end > start else 0.0
        for i in range(a + 1, b):
            k = i - a - 1
            s = start + k * step
            out[i] = (s, s + step if step > 0 else s + 0.01)

    filled = [o if o is not None else (0.0, 0.01) for o in out]
    # Whisper timestamps are per transcription segment and occasionally overlap where two of them
    # meet, which would hand back a subtitle track that runs backwards. Clamp the starts forward:
    # slightly late is survivable, out of order is not.
    clamped: list[tuple[float, float]] = []
    prev = 0.0
    for start, end in filled:
        start = max(start, prev)
        clamped.append((start, max(end, start)))
        prev = start
    return clamped
