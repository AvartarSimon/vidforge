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

from . import env, ffmpeg, render, subtitles, thumbnail
from .project import Project
from .tts import get_provider, synthesize_cached


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

    env.load_dotenv(project.root)

    # 1. TTS per segment (cached)
    tts = get_provider(project.tts.provider, rate=project.rate, config=project.tts.__dict__)
    _log(f"{len(project.segments)} segments · tts {tts.name} · voice {project.voice}")
    words_by_seg = {}
    narration_len: dict[str, float] = {}
    for seg in project.segments:
        audio = bd / "audio" / f"{_safe(seg.id)}.mp3"
        words = synthesize_cached(tts, seg.text, seg.voice or project.voice, audio)
        words = subtitles.restore_punctuation(words, seg.text)
        words_by_seg[seg.id] = (audio, words)
        narration_len[seg.id] = ffmpeg.duration(audio) + seg.pause_after
        _log(f"  tts  {seg.id:<12} {len(words):>4} words  {narration_len[seg.id]:6.2f}s")
    if only_tts:
        return bd

    # 1b. Fetch remote assets (pexels:…) now that narration lengths are known
    from . import assets
    assets.resolve_all(project, narration_len, log=_log)

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
        timeline.append({"id": seg.id, "label": seg.label, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
        cursor += dur
        clips.append(clip)
        _log(f"  clip {seg.id:<12} {dur:6.2f}s  ({'video' if seg.video else seg.motion})")

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
    thumb_src = next((s.image for s in project.segments if s.image), None)
    if thumb_src is None:                       # every segment is a video: grab the first frame
        thumb_src = bd / "thumb_src.jpg"
        ffmpeg.run(["-y", "-ss", "1", "-i", str(clips[0]), "-frames:v", "1", str(thumb_src)])
    thumbnail.make(thumb_src, thumb_text, bd / "thumbnail.jpg")

    credits = _credits(project)
    if credits:
        (bd / "credits.txt").write_text(credits, encoding="utf-8")

    _log(f"done in {time.time() - t0:.1f}s · {cursor:.1f}s video · {final}")
    _log("chapters:\n" + "\n".join(_chapter_line(t) for t in timeline))
    return final


def _credits(project: Project) -> str:
    idx = project.root / "assets" / "pexels" / "index.json"
    if not idx.exists():
        return ""
    from .assets.pexels import Pexels
    return Pexels(idx.parent).credits()


def _chapter_line(t: dict) -> str:
    s = int(t["start"])
    return f"  {s // 60:02d}:{s % 60:02d} {t.get('label') or t['id']}"
