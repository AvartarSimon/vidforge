"""The build: project -> final.mp4 + final.srt + thumbnail.jpg.

Build directory layout (under project.out_dir, default `build/`):
    audio/<seg>.mp3 + .json   TTS output + word timings (cached by text/voice hash)
    clips/<seg>.mp4           rendered segment
    merged.mp4                concat of all clips (narration only)
    final.srt                 subtitles for the whole video
    final.mp4                 + BGM, optional burned subtitles
    thumbnail.jpg
    timeline.json             segment start/end times (for chapters, editing)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import render, subtitles, thumbnail
from .project import Project
from .tts import edge


def _log(msg: str) -> None:
    print(f"[vidforge] {msg}", flush=True)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def build(project: Project, *, only_tts: bool = False, burn: bool | None = None) -> Path:
    t0 = time.time()
    bd = project.build_dir
    (bd / "audio").mkdir(parents=True, exist_ok=True)
    (bd / "clips").mkdir(parents=True, exist_ok=True)
    if burn is not None:
        project.subtitles.burn = burn

    # 1. TTS per segment (cached)
    _log(f"{len(project.segments)} segments · voice {project.voice}")
    words_by_seg = {}
    for seg in project.segments:
        audio = bd / "audio" / f"{_safe(seg.id)}.mp3"
        words = edge.synthesize(seg.text, seg.voice or project.voice, project.rate, audio)
        words = subtitles.restore_punctuation(words, seg.text)
        words_by_seg[seg.id] = (audio, words)
        _log(f"  tts  {seg.id:<12} {len(words):>4} words")
    if only_tts:
        return bd

    # 2. Render each segment; accumulate the timeline
    clips: list[Path] = []
    timeline: list[dict] = []
    cues = []
    cursor = 0.0
    for seg in project.segments:
        audio, words = words_by_seg[seg.id]
        clip = bd / "clips" / f"{_safe(seg.id)}.mp4"
        dur = render.render_segment(project, seg, audio, clip)
        cues += subtitles.build_cues(words, offset=cursor, max_chars=project.subtitles.max_chars)
        timeline.append({"id": seg.id, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
        cursor += dur
        clips.append(clip)
        _log(f"  clip {seg.id:<12} {dur:6.2f}s  ({seg.motion})")

    (bd / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    srt = bd / "final.srt"
    subtitles.write_srt(cues, srt)

    # 3. Concat, then one finishing pass (BGM / burn)
    merged = bd / "merged.mp4"
    render.concat(clips, merged)
    final = bd / "final.mp4"
    if not cues:
        _log("warning: no word timings received - subtitles skipped")
    render.finalize(project, merged, srt if cues else None, cursor, final)

    # 4. Thumbnail
    thumb_text = project.thumbnail_text or project.title
    thumbnail.make(project.segments[0].image, thumb_text, bd / "thumbnail.jpg")

    _log(f"done in {time.time() - t0:.1f}s · {cursor:.1f}s video · {final}")
    _log("chapters:\n" + "\n".join(_chapter_line(t) for t in timeline))
    return final


def _chapter_line(t: dict) -> str:
    s = int(t["start"])
    return f"  {s // 60:02d}:{s % 60:02d} {t['id']}"
