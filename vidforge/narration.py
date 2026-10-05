"""Narration that isn't TTS: your own recording, turned into what the pipeline expects.

A segment may carry `"narration": "assets/narration/seg1.m4a"` instead of being spoken by a TTS
voice. The pipeline needs exactly two things from it — an mp3 and a `list[Word]` — so that is what
`prepare()` returns, cached the same way `tts.synthesize_cached` caches a synthesis:

    source file (any audio, or a video to pull the audio out of)
        -> decode to mp3, trimming the silence at either end
        -> force-align against the segment's script text  (align.py)
        -> sidecar .json holding the key and the words

The sidecar is what keeps a rebuild cheap: Whisper runs once per recording, not once per build.
Its key covers the source file's size and mtime, the script text and the Whisper model, so
re-recording a take or editing the line re-aligns, and nothing else does.

Why trim the silence: you press record, walk to the chair, and start talking. Those three seconds
are not narration, and left in place they push every subsequent cue late. The trim is conservative
(-45 dB, needs a tenth of a second) and its result is reported, because the one thing worse than
leaving the silence in is eating the first word.

Tone shaping is deliberately *not* here. It happens in render.py with `loudnorm`, from
`project.voice_fx`, so the same presets apply whether the voice is yours or synthesised — and
changing a preset does not invalidate these alignments, which would mean running Whisper again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from . import align as aligner, ffmpeg
from .tts import Word

AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".wma")
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".m4v", ".avi")
# a tenth of a second under -45 dBFS: quiet enough to be the room, long enough not to be a breath
_TRIM = ("silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB:detection=peak,"
         "areverse,"
         "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB:detection=peak,"
         "areverse")


class NarrationError(RuntimeError):
    pass


def is_supported(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXT + VIDEO_EXT


def extract(source: Path, out: Path, *, trim: bool = True, log=None) -> float:
    """Decode `source` (audio file or video) to a mono 44.1 kHz mp3. Returns seconds kept."""
    source, out = Path(source), Path(out)
    if not source.is_file():
        raise NarrationError(f"找不到录音文件：{source}")
    if not is_supported(source):
        raise NarrationError(f"不支持的格式 {source.suffix}（可用：{', '.join(AUDIO_EXT + VIDEO_EXT)}）")
    out.parent.mkdir(parents=True, exist_ok=True)
    before = ffmpeg.duration(source)
    args = ["-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "44100"]
    if trim:
        args += ["-af", _TRIM]
    args += ["-c:a", "libmp3lame", "-q:a", "2", str(out)]
    ffmpeg.run(args)
    after = ffmpeg.duration(out)
    if log and trim and before - after > 0.15:
        log(f"  掐掉首尾静音 {before - after:.2f}s（{before:.2f}s → {after:.2f}s）")
    return after


def _key(source: Path, text: str, trim: bool) -> str:
    st = source.stat()
    model = os.environ.get("VIDFORGE_WHISPER_MODEL", aligner.DEFAULT_MODEL)
    digest = hashlib.sha1(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:12]
    return f"own:{source.name}:{st.st_size}:{int(st.st_mtime)}:{digest}:{model}:trim={trim}"


def prepare(source: Path, out: Path, text: str, *, lang: str | None = None,
            trim: bool = True, log=None) -> list[Word]:
    """The mp3 at `out` plus word timings for `text`, reusing both when nothing changed."""
    source, out = Path(source), Path(out)
    if not source.is_file():
        raise NarrationError(f"找不到录音文件：{source}")
    meta_path = out.with_suffix(".json")
    key = _key(source, text, trim)

    if out.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("key") == key and meta.get("words"):
                return [Word(**w) for w in meta["words"]]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass          # corrupt sidecar -> redo it

    extract(source, out, trim=trim, log=log)
    words = aligner.align(out, text, lang=lang, log=log)
    meta_path.write_text(json.dumps({
        "key": key, "provider": "own", "source": str(source),
        "words": [asdict(w) for w in words],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return words


def save_upload(root: Path, seg_id: str, data: bytes, suffix: str) -> Path:
    """Store a recording made in the browser next to the project, and say where it went.

    `<project>/assets/narration/<seg>.<ext>` — inside the project, because a narration track is as
    much a part of the video as its pictures: copy the folder and it still builds."""
    if not data:
        raise NarrationError("录音是空的")
    suffix = "." + suffix.lstrip(".").lower()
    if suffix not in AUDIO_EXT + VIDEO_EXT:
        raise NarrationError(f"不支持的格式 {suffix}")
    # a single path component, and a tidy one: dots collapse so a segment id like "../x" cannot
    # even look like a traversal in the logs
    safe = re.sub(r"_+", "_", re.sub(r"[^\w-]", "_", seg_id)).strip("_") or "segment"
    folder = Path(root) / "assets" / "narration"
    folder.mkdir(parents=True, exist_ok=True)
    # one recording per segment: re-recording replaces the take rather than piling up files, and
    # the old alignment is dropped because its key no longer matches the new size/mtime
    for old in folder.glob(f"{safe}.*"):
        old.unlink(missing_ok=True)
    path = folder / f"{safe}{suffix}"
    path.write_bytes(data)
    return path
