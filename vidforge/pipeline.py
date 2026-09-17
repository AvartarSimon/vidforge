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
from .project import Project, Segment
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
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:60]


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


def preview_segment(project: Project, seg_id: str) -> tuple[Path, float]:
    """Render ONE segment at draft quality into build/preview/ (the UI's per-segment check):
    TTS (cached) -> assets -> remotion -> clips -> mux. Seconds, not the whole film."""
    import dataclasses
    seg = next(s for s in project.segments if s.id == seg_id)
    draft = dataclasses.replace(project, quality="draft", segments=[seg])
    bd = project.build_dir
    audio, narration = synthesize_segment(draft, seg_id)
    from . import assets
    assets.resolve_all(draft, {seg_id: narration + seg.pause_after}, log=lambda *_: None)
    if any(c.remotion for c in seg.clips):
        from . import remotion
        for pc in render.plan_clips(seg, narration + seg.pause_after):
            if pc.clip.remotion is not None:
                pc.clip.video = remotion.render(pc.clip.remotion.composition, pc.clip.remotion.props, duration=pc.seconds,
                                                fps=project.fps, width=project.width, height=project.height,
                                                out_dir=bd / "remotion", log=lambda *_: None)
    idx = next(i for i, s in enumerate(project.segments) if s.id == seg_id)
    if project.presenter.provider != "none" and (any(o.avatar for o in seg.overlays) or _wants_presenter(project, seg, idx)):
        from . import avatar
        from .project import Overlay
        layers = [o for o in seg.overlays if o.avatar]
        if not layers:
            ov = Overlay(avatar=True, position=project.presenter.position, size=project.presenter.size, border=False, animate="fade")
            seg.overlays.append(ov); layers = [ov]
        video = avatar.render_presenter(project, seg, audio, narration + seg.pause_after, bd / "presenter", log=lambda *_: None)
        for ov in layers:
            ov.video = video; ov.avatar = False
    out = bd / "preview" / f"{_safe(seg_id)}.mp4"
    dur = render.render_segment(draft, seg, audio, out, cache_dir=bd / "preview")
    return out, dur


def _workers(project: Project) -> int:
    if project.parallel > 0:
        return project.parallel
    return max(1, (os.cpu_count() or 2) // 2)


# -- structured progress (read by the UI; no log parsing) -------------------------------------
_progress: dict = {"phase": "idle", "done": 0, "total": 0}
PHASE_WEIGHT = {"tts": (0, 15), "assets": (15, 20), "remotion": (20, 25), "render": (25, 92), "assemble": (92, 100)}


def progress() -> dict:
    lo, hi = PHASE_WEIGHT.get(_progress["phase"], (0, 0))
    frac = _progress["done"] / _progress["total"] if _progress["total"] else 0
    pct = 100 if _progress["phase"] == "done" else lo + (hi - lo) * frac
    return {**_progress, "percent": round(pct, 1)}


def _set_progress(phase: str, done: int = 0, total: int = 0) -> None:
    _progress.update(phase=phase, done=done, total=total)


class _Ctx:
    """Everything the stages hand to each other."""

    def __init__(self, project: Project):
        self.project = project
        self.bd = project.build_dir
        self.encoder = render.pick_encoder(project)
        self.audio: dict[str, Path] = {}
        self.words: dict[str, list] = {}
        self.narration: dict[str, float] = {}       # narration + pause, per segment
        self.clips: dict[str, Path] = {}
        self.durations: dict[str, float] = {}       # real muxed length per segment


def _stage_vocab(project: Project) -> None:
    """Learner edition: append a 'vocab' segment — a Vocab card read aloud (word list)."""
    if project.outro_vocab <= 0 or any(s.id == "vocab" for s in project.segments):
        return
    from . import vocab
    from .project import Clip, RemotionSpec
    script = " ".join(s.text for s in project.segments)
    items = vocab.extract(script, project.outro_vocab, project.build_dir)
    if not items:
        return
    words = ", ".join(i["word"] for i in items)
    zh = project.subtitles.bilingual_lang.startswith("zh")
    seg = Segment(id="vocab", label="Vocabulary" if not zh else "本集词汇", text=f"Words from this episode: {words}.",
                  pause_after=1.5, clips=[Clip(remotion=RemotionSpec("Vocab", {"title": "本集词汇 · Vocabulary" if zh else "Vocabulary", "items": items}))])
    seg.alt_text = "本集词汇：" + "，".join(f"{i['word']}（{i.get('meaning') or ''}）" if i.get("meaning") else i["word"] for i in items) if zh else None
    project.segments.append(seg)
    _log(f"vocab card: {len(items)} words")


def _stage_tts(ctx: _Ctx) -> None:
    """Serial (network-bound), cached by text/voice."""
    p = ctx.project
    tts = get_provider(p.tts.provider, rate=p.rate, config=p.tts.__dict__)
    _log(f"{len(p.segments)} segments · tts {tts.name} · voice {p.voice} · {p.quality} · {ctx.encoder}")
    for w in p.warnings:
        _log(f"warning: {w}")
    _set_progress("tts", 0, len(p.segments))
    for i, seg in enumerate(p.segments):
        _check_cancel()
        audio = ctx.bd / "audio" / f"{_safe(seg.id)}.mp3"
        words = synthesize_cached(tts, seg.text, seg.voice or p.voice, audio)
        ctx.words[seg.id] = subtitles.restore_punctuation(words, seg.text)
        ctx.audio[seg.id] = audio
        ctx.narration[seg.id] = ffmpeg.duration(audio) + seg.pause_after
        _set_progress("tts", i + 1, len(p.segments))
        _log(f"  tts  {seg.id:<12} {len(words):>4} words  {ctx.narration[seg.id]:6.2f}s")


def _stage_title_cards(ctx: _Ctx) -> None:
    """auto_title_cards: a 3 s TitleCard in front of every labelled segment (needs Remotion)."""
    if not ctx.project.auto_title_cards:
        return
    from .project import Clip, RemotionSpec
    from .remotion import APP_DIR
    if not (APP_DIR / "node_modules").exists():
        _log("warning: auto_title_cards needs Remotion (vidforge remotion setup) — skipped")
        return
    n = 0
    for seg in ctx.project.segments:
        first = seg.clips[0] if seg.clips else None
        if seg.label and not (first and first.remotion and first.remotion.composition == "TitleCard"):
            n += 1
            seg.clips.insert(0, Clip(remotion=RemotionSpec("TitleCard", {"kicker": f"Chapter {n}", "title": seg.label}), duration=3.0))
    _log(f"auto title cards: {n}")


def _stage_assets(ctx: _Ctx) -> None:
    """Remote search clips (pexels:/pixabay:/commons:) -> local files, now that lengths are known."""
    from . import assets
    _set_progress("assets", 0, 1)
    assets.resolve_all(ctx.project, ctx.narration, log=_log)
    _set_progress("assets", 1, 1)


def _stage_remotion(ctx: _Ctx) -> None:
    """Animated clips -> mp4 (cached by props), each at its planned share of the segment."""
    todo = [seg for seg in ctx.project.segments if any(c.remotion for c in seg.clips)]
    _set_progress("remotion", 0, len(todo))
    for i, seg in enumerate(todo):
        from . import remotion
        for pc in render.plan_clips(seg, ctx.narration[seg.id]):
            if pc.clip.remotion is not None:
                _check_cancel()
                pc.clip.video = remotion.render(
                    pc.clip.remotion.composition, pc.clip.remotion.props, duration=pc.seconds,
                    fps=ctx.project.fps, width=ctx.project.width, height=ctx.project.height,
                    out_dir=ctx.bd / "remotion", log=_log)
        _set_progress("remotion", i + 1, len(todo))


def _wants_presenter(project: Project, seg: Segment, index: int) -> bool:
    if project.presenter.provider == "none":
        return False
    if seg.presenter is not None:
        return seg.presenter
    where = project.presenter.where
    return where == "all" or (where == "first_last" and index in (0, len(project.segments) - 1))


def _stage_presenter(ctx: _Ctx) -> None:
    """Digital host videos -> overlay layers (segments that want the presenter, plus explicit
    {"avatar": true} overlays)."""
    from .project import Overlay
    p = ctx.project
    todo: list[tuple[Segment, list[Overlay]]] = []
    for i, seg in enumerate(p.segments):
        avatar_layers = [o for o in seg.overlays if o.avatar]
        if not avatar_layers and _wants_presenter(p, seg, i):
            ov = Overlay(avatar=True, position=p.presenter.position, size=p.presenter.size, border=False, animate="fade")
            seg.overlays.append(ov)
            avatar_layers = [ov]
        if avatar_layers:
            todo.append((seg, avatar_layers))
    if not todo:
        return
    from . import avatar
    _set_progress("remotion", 0, len(todo))
    for k, (seg, layers) in enumerate(todo):
        _check_cancel()
        video = avatar.render_presenter(p, seg, ctx.audio[seg.id], ctx.narration[seg.id], ctx.bd / "presenter", log=_log)
        for ov in layers:
            ov.video = video
            ov.avatar = False
        _set_progress("remotion", k + 1, len(todo))
        _log(f"  host {seg.id:<12} {p.presenter.provider}")


def _segment_key(project: Project, seg: Segment, audio: Path, encoder: str) -> str:
    """Everything that changes a segment's rendered clip: its definition (clips, overlays, pause),
    the narration file, and the render settings. Same key => reuse the cached clip."""
    import dataclasses
    import hashlib

    def enc(o):
        if dataclasses.is_dataclass(o):
            return {k: enc(v) for k, v in dataclasses.asdict(o).items()}
        if isinstance(o, Path):
            try:
                return f"{o.name}:{o.stat().st_size}:{int(o.stat().st_mtime)}"
            except OSError:
                return str(o)
        if isinstance(o, (list, tuple)):
            return [enc(v) for v in o]
        if isinstance(o, dict):
            return {k: enc(v) for k, v in o.items()}
        return o
    settings = [project.width, project.height, project.fps, project.quality, encoder, project.motion_amount,
                project.effective_supersample, project.transition, project.normalize_audio, project.presenter.provider]
    blob = json.dumps([enc(seg), enc(audio), settings], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def _stage_render(ctx: _Ctx) -> None:
    """Segments in parallel (CPU/GPU-bound). A segment whose key is unchanged is reused from
    clips/<id>.<key>.mp4 — editing one segment re-renders only that one. The last 5 versions
    of each segment's clip are kept so reverting a segment is instant."""
    p = ctx.project

    def one(seg):
        _check_cancel()
        key = _segment_key(p, seg, ctx.audio[seg.id], ctx.encoder)
        clip = ctx.bd / "clips" / f"{_safe(seg.id)}.{key}.mp4"
        if clip.exists() and clip.stat().st_size > 0:
            try:
                return seg.id, clip, ffmpeg.duration(clip), True
            except ffmpeg.FfmpegError:
                clip.unlink(missing_ok=True)
        dur = render.render_segment(p, seg, ctx.audio[seg.id], clip, encoder=ctx.encoder)
        siblings = sorted((ctx.bd / "clips").glob(f"{_safe(seg.id)}.*.mp4"), key=lambda f: f.stat().st_mtime)
        for old in siblings[:-5]:
            old.unlink(missing_ok=True)
            import shutil
            shutil.rmtree(old.with_name(old.stem + "_parts"), ignore_errors=True)
        return seg.id, clip, dur, False

    n = _workers(p)
    _log(f"rendering {len(p.segments)} segments with {n} worker(s)")
    _set_progress("render", 0, len(p.segments))
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = {pool.submit(one, seg): seg for seg in p.segments}
        for k, fut in enumerate(as_completed(futures)):
            sid, clip, dur, cached = fut.result()
            ctx.clips[sid], ctx.durations[sid] = clip, dur
            seg = futures[fut]
            kinds = ",".join(c.remotion.composition if c.remotion else ("video" if c.video else c.motion) for c in seg.clips)
            _set_progress("render", k + 1, len(p.segments))
            _log(f"  clip {sid:<12} {dur:6.2f}s  ({len(seg.clips)} clip{'s' if len(seg.clips) > 1 else ''}: {kinds}){'  · cached' if cached else ''}")
    _check_cancel()


def _stage_assemble(ctx: _Ctx) -> tuple[Path, list[dict], float]:
    """Subtitles + timeline from REAL segment lengths, concat, BGM/burn, thumbnail, credits."""
    p, bd = ctx.project, ctx.bd
    _set_progress("assemble", 0, 3)
    cues, timeline, cursor = [], [], 0.0
    for seg in p.segments:
        seg_cues = subtitles.build_cues(ctx.words[seg.id], offset=cursor, max_chars=p.subtitles.max_chars)
        if p.subtitles.bilingual and seg.alt_text:
            seg_cues = subtitles.bilingual(seg_cues, seg.alt_text)
        cues += seg_cues
        timeline.append({"id": seg.id, "label": seg.label, "start": round(cursor, 3), "end": round(cursor + ctx.durations[seg.id], 3)})
        cursor += ctx.durations[seg.id]
    (bd / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    srt = bd / "final.srt"
    subtitles.write_srt(cues, srt)
    if not cues:
        _log("warning: no word timings received - subtitles skipped")

    merged = bd / "merged.mp4"
    render.concat([ctx.clips[s.id] for s in p.segments], merged)
    _set_progress("assemble", 1, 3)
    _check_cancel()
    final = bd / "final.mp4"
    render.finalize(p, merged, srt if cues else None, cursor, final)
    _set_progress("assemble", 2, 3)

    thumb_src = next((s.image for s in p.segments if s.image), None)
    if thumb_src is None:
        thumb_src = bd / "thumb_src.jpg"
        ffmpeg.run(["-y", "-ss", "1", "-i", str(ctx.clips[p.segments[0].id]), "-frames:v", "1", str(thumb_src)])
    thumbnail.make(thumb_src, p.thumbnail_text or p.title, bd / "thumbnail.jpg")
    credits = _credits(p)
    if credits:
        (bd / "credits.txt").write_text(credits, encoding="utf-8")
    _set_progress("assemble", 3, 3)
    return final, timeline, cursor


def build(project: Project, *, only_tts: bool = False, burn: bool | None = None) -> Path:
    """TTS -> (title cards) -> assets -> remotion -> render segments -> assemble."""
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
        _stage_vocab(project)
        ctx = _Ctx(project)
        _stage_tts(ctx)
        if only_tts:
            return bd
        _stage_title_cards(ctx)
        _stage_assets(ctx)
        _stage_remotion(ctx)
        _stage_presenter(ctx)
        _stage_render(ctx)
        final, timeline, total = _stage_assemble(ctx)
        _set_progress("done", 1, 1)
        _log(f"done in {time.time() - t0:.1f}s · {total:.1f}s video · {final}")
        _log("chapters:\n" + "\n".join(_chapter_line(t) for t in timeline))
        return final
    except BaseException:
        _set_progress("idle")
        raise
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
