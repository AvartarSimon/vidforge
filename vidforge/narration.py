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
import threading
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


def speech_edges(source: Path, *, threshold_db: float = -45.0, min_silence: float = 0.1) -> tuple[float, float]:
    """(first sound, last sound) in seconds, with the same threshold the narration trim uses.

    For a take that is both the voice and the picture of a segment: cutting the video at these
    points leaves the audio with no edge silence for `extract()` to remove, so the trimmed mp3
    and the picture start on the same frame and the lips stay on the words."""
    import subprocess
    total = ffmpeg.duration(source)
    r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(source), "-vn",
                        "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    first, last = 0.0, total
    if starts and starts[0] <= 0.05 and ends:
        first = ends[0]
    if starts and (len(ends) < len(starts) or ends[-1] >= total - 0.05):
        last = starts[-1]
    if last - first < 0.3:                 # all silence (or nearly): keep the take as it is
        return 0.0, total
    return max(0.0, first), min(total, last)


def _key(source: Path, text: str, trim: bool) -> str:
    st = source.stat()
    model = os.environ.get("VIDFORGE_WHISPER_MODEL", aligner.DEFAULT_MODEL)
    digest = hashlib.sha1(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()[:12]
    return f"own:{source.name}:{st.st_size}:{int(st.st_mtime)}:{digest}:{model}:trim={trim}"


# One alignment at a time: the studio warms a fresh take in the background while a build may be
# asking for the same file. Waiting for the other one and then reading its sidecar beats two
# Whisper runs fighting over the same cores and the same output file.
_PREPARE_LOCK = threading.Lock()


def prepare(source: Path, out: Path, text: str, *, lang: str | None = None,
            trim: bool = True, log=None) -> list[Word]:
    """The mp3 at `out` plus word timings for `text`, reusing both when nothing changed."""
    source, out = Path(source), Path(out)
    if not source.is_file():
        raise NarrationError(f"找不到录音文件：{source}")
    with _PREPARE_LOCK:
        return _prepare(source, out, text, lang=lang, trim=trim, log=log)


def _prepare(source: Path, out: Path, text: str, *, lang: str | None, trim: bool, log) -> list[Word]:
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

    `<project>/assets/narration/<seg>_<time>.<ext>` — inside the project, because a narration track is as
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
    # every recording is kept: re-recording a segment used to delete the previous take, and a take
    # is the one thing that cannot be made again. Each gets its own timestamped name; the project
    # simply points at the newest, and the studio lists the rest so any of them can be put back.
    import time
    path = folder / f"{safe}_{time.strftime('%Y%m%d-%H%M%S')}{suffix}"
    n = 1
    while path.exists():
        path = folder / f"{safe}_{time.strftime('%Y%m%d-%H%M%S')}-{n}{suffix}"
        n += 1
    path.write_bytes(data)
    if suffix == ".webm":
        _fix_webm_duration(path)
    return path


def _fix_webm_duration(path: Path) -> None:
    """A browser's MediaRecorder writes webm as it goes and never goes back to fill in the length,
    so ffprobe guesses — a 40 s take was listed as 599.5 s. A stream copy writes the header
    properly; nothing is re-encoded. A take that will not remux is kept as it came."""
    tmp = path.with_name(path.stem + ".fixed.webm")
    try:
        ffmpeg.run(["-y", "-i", str(path), "-c", "copy", str(tmp)])
        if tmp.is_file() and tmp.stat().st_size > 0:
            os.replace(tmp, path)
    except ffmpeg.FfmpegError:
        pass
    finally:
        tmp.unlink(missing_ok=True)
