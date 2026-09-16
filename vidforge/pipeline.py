"""The build: project -> final.mp4 + final.srt + thumbnail.jpg.

Build directory layout (under project.out_dir, default `build/`):
    audio/<seg>.mp3 + .json   TTS output + word timings (cached by text/voice hash)
    clips/<seg>.mp4           rendered segment (+ <seg>_parts/ per-clip intermediates)
    remotion/                 rendered compositions (cached by props hash)
    merged.mp4                concat of all clips (narration only)
    final.srt                 subtitles for the whole video
    final.mp4                 + BGM, optional burned subtitles
    thumbnail.jpg, credits.txt, timeline.json, build.log

Stages: TTS (serial, network) -> assets -> remotion -> segments (PARALLEL, cpu-bound)
-> concat -> finalize -> thumbnail. A 30-minute video is ~40 segments; with 4 workers the
segment stage runs in roughly a quarter of the serial time.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import env, ffmpeg, render, subtitles, thumbnail
from .project import Project
from .tts import get_provider, synthesize_cached

_sink = None          # set_log() lets a host (the web UI) capture build output
_cancel = threading.Event()


class BuildCancelled(RuntimeError):
    pass


def set_log(fn) -> None:
    global _sink
    _sink = fn


def cancel() -> None:
    _cancel.set()


def _check_cancel() -> None:
    if _cancel.is_set():
        raise BuildCancelled("build cancelled")


def _log(msg: str) -> None:
    line = f"[vidforge] {msg}"
    if _sink is not None:
        _sink(line)
    else:
        print(line, flush=True)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def synthesize_segment(project: Project, seg_id: str) -> tuple[Path, float]:
    """TTS for one segment only (the UI's proof-listen). Returns (mp3 path, seconds)."""
    seg = next(s for s in project.segments if s.id == seg_id)
    bd = project.build_dir
    (bd / "audio").mkdir(parents=True, exist_ok=True)
    env.load_dotenv(project.root)
    tts = get_provider(project.tts.provider, rate=project.rate, config=project.tts.__dict__)
    audio = bd / "audio" / f"{_safe(seg.id)}.mp3"
    synthesize_cached(tts, seg.text, seg.voice or project.voice, audio)
    return audio, ffmpeg.duration(audio)


def _workers(project: Project) -> int:
    if project.parallel > 0:
        return project.parallel
    return max(1, (os.cpu_count() or 2) // 2)


def build(project: Project, *, only_tts: bool = False, burn: bool | None = None) -> Path:
    _cancel.clear()
    t0 = time.time()
    bd = project.build_dir
    (bd / "audio").mkdir(parents=True, exist_ok=True)
    (bd / "clips").mkdir(parents=True, exist_ok=True)
    if burn is not None:
        project.subtitles.burn = burn
    env.load_dotenv(project.root)
    log_file = open(bd / "build.log", "a", encoding="utf-8")
    prev_sink = _sink

    def tee(line: str) -> None:
        log_file.write(line + "\n"); log_file.flush()
        if prev_sink is not None:
            prev_sink(line)
        else:
            print(line, flush=True)
    set_log(tee)

    try:
        # 1. TTS per segment (cached, serial: network-bound)
        tts = get_provider(project.tts.provider, rate=project.rate, config=project.tts.__dict__)
        encoder = render.pick_encoder(project)
        _log(f"{len(project.segments)} segments · tts {tts.name} · voice {project.voice} · {project.quality} · {encoder}")
        words_by_seg = {}
        narration_len: dict[str, float] = {}
        for seg in project.segments:
            _check_cancel()
            audio = bd / "audio" / f"{_safe(seg.id)}.mp3"
            words = synthesize_cached(tts, seg.text, seg.voice or project.voice, audio)
            words = subtitles.restore_punctuation(words, seg.text)
            words_by_seg[seg.id] = (audio, words)
            narration_len[seg.id] = ffmpeg.duration(audio) + seg.pause_after
            _log(f"  tts  {seg.id:<12} {len(words):>4} words  {narration_len[seg.id]:6.2f}s")
        if only_tts:
            return bd

        # 1b. Remote assets (pexels:… etc.) now that narration lengths are known
        from . import assets
        assets.resolve_all(project, narration_len, log=_log)

        # 1c. Remotion clips -> mp4 (cached), each sized to its planned share of the segment
        for seg in project.segments:
            if any(c.remotion for c in seg.clips):
                from . import remotion
                for pc in render.plan_clips(seg, narration_len[seg.id]):
                    if pc.clip.remotion is not None:
                        _check_cancel()
                        pc.clip.video = remotion.render(
                            pc.clip.remotion.composition, pc.clip.remotion.props, duration=pc.seconds,
                            fps=project.fps, width=project.width, height=project.height,
                            out_dir=bd / "remotion", log=_log)

        # 2. Render segments in parallel; timeline in script order
        clips_out: dict[str, Path] = {}
        durations: dict[str, float] = {}

        def one(seg):
            _check_cancel()
            clip = bd / "clips" / f"{_safe(seg.id)}.mp4"
            dur = render.render_segment(project, seg, words_by_seg[seg.id][0], clip, encoder=encoder)
            return seg.id, clip, dur

        n = _workers(project)
        _log(f"rendering {len(project.segments)} segments with {n} worker(s)")
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {pool.submit(one, seg): seg for seg in project.segments}
            for fut in as_completed(futures):
                sid, clip, dur = fut.result()
                clips_out[sid], durations[sid] = clip, dur
                seg = futures[fut]
                kinds = ",".join(c.remotion.composition if c.remotion else ("video" if c.video else c.motion) for c in seg.clips)
                _log(f"  clip {sid:<12} {dur:6.2f}s  ({len(seg.clips)} clip{'s' if len(seg.clips) > 1 else ''}: {kinds})")
        _check_cancel()

        cues, timeline, cursor = [], [], 0.0
        for seg in project.segments:
            cues += subtitles.build_cues(words_by_seg[seg.id][1], offset=cursor, max_chars=project.subtitles.max_chars)
            timeline.append({"id": seg.id, "label": seg.label, "start": round(cursor, 3), "end": round(cursor + durations[seg.id], 3)})
            cursor += durations[seg.id]
        (bd / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
        srt = bd / "final.srt"
        subtitles.write_srt(cues, srt)

        # 3. Concat, then one finishing pass (BGM / burn)
        merged = bd / "merged.mp4"
        render.concat([clips_out[s.id] for s in project.segments], merged)
        final = bd / "final.mp4"
        if not cues:
            _log("warning: no word timings received - subtitles skipped")
        _check_cancel()
        render.finalize(project, merged, srt if cues else None, cursor, final)

        # 4. Thumbnail + credits
        thumb_text = project.thumbnail_text or project.title
        thumb_src = next((s.image for s in project.segments if s.image), None)
        if thumb_src is None:
            thumb_src = bd / "thumb_src.jpg"
            ffmpeg.run(["-y", "-ss", "1", "-i", str(clips_out[project.segments[0].id]), "-frames:v", "1", str(thumb_src)])
        thumbnail.make(thumb_src, thumb_text, bd / "thumbnail.jpg")
        credits = _credits(project)
        if credits:
            (bd / "credits.txt").write_text(credits, encoding="utf-8")

        _log(f"done in {time.time() - t0:.1f}s · {cursor:.1f}s video · {final}")
        _log("chapters:\n" + "\n".join(_chapter_line(t) for t in timeline))
        return final
    finally:
        set_log(prev_sink)
        log_file.close()


def _credits(project: Project) -> str:
    from .assets import Library
    lib = Library(project.root)
    used = set()
    for s in project.segments:
        for c in s.clips:
            for p in (c.image, c.video):
                if p:
                    try:
                        used.add(p.resolve().relative_to(project.root.resolve()).as_posix())
                    except ValueError:
                        pass
    text = lib.credits(used)
    manual = [c.credit for s in project.segments for c in s.clips if c.credit]
    if manual:
        text += ("\n" if text else "Media credits\n") + "\n".join(f"  {m}" for m in dict.fromkeys(manual))
    return text


def _chapter_line(t: dict) -> str:
    s = int(t["start"])
    return f"  {s // 60:02d}:{s % 60:02d} {t.get('label') or t['id']}"
