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

from . import awake, env, ffmpeg, render, subtitles, thumbnail
from .narration import prepare as prepare_own
from .project import Project, RemotionSpec, Segment
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
                pc.clip.video = remotion.render(pc.clip.remotion.composition, _graphics_props(project, pc.clip.remotion, seg), duration=pc.seconds,
                                                fps=project.fps, width=project.width, height=project.height,
                                                out_dir=bd / "remotion", log=lambda *_: None)
    if any(getattr(o, "me", None) for o in (*seg.clips, *seg.overlays)):
        from . import lipsync, me
        lib = me.MeLibrary(me.library_dir(project.root)); lib.scan()
        for obj in (*seg.clips, *seg.overlays):
            if getattr(obj, "me", None):
                take = lib.pick(obj.me.get("tags"), bool(obj.me.get("talking")), min_seconds=narration + seg.pause_after)
                if take is None:
                    raise RuntimeError("素材库里没有匹配的镜头")
                obj.video = lipsync.sync(take, audio, narration + seg.pause_after, bd / "lipsync", provider=project.lipsync) if obj.me.get("talking") else take
                obj.me = None
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
    fill_bare_segments(draft)
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
        self.said: dict[str, str] = {}              # what each segment's subtitles say (seg.said, or heard now)


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


# How many voices to synthesise at once, per engine. edge and ElevenLabs are network calls, so
# waiting for them one at a time is the single most wasteful thing a 40-segment build does; the
# counts stay modest because edge-tts is an unofficial free endpoint and ElevenLabs charges and
# rate-limits. VoxCPM runs the model on this machine, so parallel work would only fight itself.
TTS_WORKERS = {"edge": 4, "elevenlabs": 2, "silent": 8, "voxcpm": 1}


def _stage_tts(ctx: _Ctx) -> None:
    """Every segment's audio + word timings, from TTS or from your own recording.

    Cached by text/voice (TTS) or by the recording's size/mtime (own voice). The network-backed
    TTS engines run in parallel; own recordings run serially because each one loads the same
    Whisper model, and two copies of it on one machine only fight for the same cores."""
    p = ctx.project
    tts = get_provider(p.tts.provider, rate=p.rate, config=p.tts.__dict__)
    own = [s for s in p.segments if s.narration]
    fx = f" · 人声 {p.voice_fx}" if p.voice_fx != "none" else ""
    how = f"tts {tts.name} · voice {p.voice}" if len(own) < len(p.segments) else "own voice"
    if own and len(own) < len(p.segments):
        how += f" · {len(own)}/{len(p.segments)} 段用自己的录音"
    _log(f"{len(p.segments)} segments · {how}{fx} · {p.quality} · {ctx.encoder}")
    for w in p.warnings:
        _log(f"warning: {w}")
    _set_progress("tts", 0, len(p.segments))

    def one(seg):
        _check_cancel()
        audio = ctx.bd / "audio" / f"{_safe(seg.id)}.mp3"
        words = synthesize_cached(tts, seg.text, seg.voice or p.voice, audio)
        return seg, audio, subtitles.restore_punctuation(words, seg.text)

    def one_own(seg):
        _check_cancel()
        audio = ctx.bd / "audio" / f"{_safe(seg.id)}.own.mp3"
        _log(f"  own  {seg.id:<12} {Path(seg.narration).name}")
        said, against = seg.said, ("录音" if seg.spoken_fresh else "脚本")
        if not seg.spoken_fresh and p.narration_mode == "free":
            # spoken in your own words and not heard yet: the subtitles are what the take says,
            # not the script it was planned from. Said in the log, because nobody has checked it.
            from .narration import NarrationError, spoken as hear_spoken
            try:
                said = hear_spoken(seg.narration, audio, lang=p.language, trim=p.narration_trim, hint=seg.text)["text"] or seg.text
                against = "录音" if said != seg.text else against
                _log(f"  字幕来自录音（自动识别，还没核对）：{said[:24]}…")
            except NarrationError as e:
                _log(f"warning: {seg.id} 没法识别录音（{e}），字幕先用脚本")
        ctx.said[seg.id] = said
        words = prepare_own(seg.narration, audio, said, lang=p.language,
                            trim=p.narration_trim, log=_log, against=against)
        return seg, audio, subtitles.restore_punctuation(words, said)

    synth = [s for s in p.segments if not s.narration]
    results: dict[str, tuple] = {}
    for seg in own:                                     # serial: one Whisper model, reused
        s2, audio, words = one_own(seg)
        results[s2.id] = (s2, audio, words)
    if synth:
        workers = min(TTS_WORKERS.get(tts.name, 1), max(1, len(synth)))
        if workers == 1:
            pairs = [one(seg) for seg in synth]
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                pairs = list(ex.map(one, synth))
        for s2, audio, words in pairs:
            results[s2.id] = (s2, audio, words)

    done = 0
    for seg in p.segments:                              # log in script order, not finish order
        _, audio, words = results[seg.id]
        ctx.words[seg.id] = words
        ctx.audio[seg.id] = audio
        ctx.narration[seg.id] = ffmpeg.duration(audio) + seg.pause_after
        done += 1
        _set_progress("tts", done, len(p.segments))
        kind = "own" if seg.narration else "tts"
        _log(f"  {kind}  {seg.id:<12} {len(words):>4} words  {ctx.narration[seg.id]:6.2f}s")


def _stage_retention(ctx: _Ctx) -> None:
    """Report the retention problems of the script being rendered, every single build.

    The hook rules are easy to agree with and easy to forget three weeks later, so they are
    checked where they cannot be skipped: right after TTS, when the real segment lengths are
    known. This never blocks a build — it is the author's call whether a 41-second opening is
    worth it — but it does not let the decision be made by accident either."""
    from . import structure
    # what the viewer hears: a hook with a number in the script but not in the take does not hook
    segs = [{"id": s.id, "text": ctx.said.get(s.id, s.said), "label": s.label or ""} for s in ctx.project.segments]
    issues = structure.check(segs, dict(ctx.narration))
    problems = [i for i in issues if i.level == "problem"]
    if not issues:
        _log("retention: 没发现问题")
        return
    _log(f"retention: {len(problems)} 个要改、1 个建议" if len(issues) - len(problems) == 1
         else f"retention: {len(problems)} 个要改、{len(issues) - len(problems)} 个建议")
    for i in issues[:8]:
        mark = "✗" if i.level == "problem" else "·"
        _log(f"  {mark} {i.where or '整体':<10} {i.what} → {i.fix}")
    if len(issues) > 8:
        _log(f"  …还有 {len(issues) - 8} 条，完整列表：vidforge structure check <项目>")


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


def _bottom_corner(o) -> str | None:
    """"left" / "right" when an overlay sits in a bottom corner of the frame, else None."""
    pos = str(getattr(o, "position", "") or "")
    if "," in pos:
        try:
            fx, fy = (float(v) for v in pos.split(","))
        except ValueError:
            return None
        return ("right" if fx > 0.5 else "left") if fy > 0.5 else None
    if "bottom" in pos:
        return "left" if "left" in pos else "right" if "right" in pos else None
    return None


def _graphics_props(project: Project, spec: RemotionSpec, seg: Segment | None = None) -> dict:
    """A chart's props, in the template's colours unless the segment chose its own, and told how
    much of the bottom a burned subtitle line takes (landscape; the vertical band is already clear).
    A small window in a bottom corner of the segment sends the source caption to the other side:
    the caption is the chart's evidence, and a round window sat right on top of it."""
    from . import theme
    props = spec.props
    taken = {_bottom_corner(o) for o in (seg.overlays if seg else []) if (o.size or 1) < 0.6} - {None}
    if len(taken) == 1 and "captionSide" not in props:
        props = {**props, "captionSide": "left" if taken == {"right"} else "right"}
    colours = theme.graphics_theme(project.theme)
    if colours and "theme" not in props:
        props = {**props, "theme": colours}
    sub = project.subtitles
    if sub.burn and project.width >= project.height and "clearBottom" not in props:
        props = {**props, "clearBottom": subtitles.band(sub.font_size, sub.margin_v, 2 if sub.bilingual else 1)}
    return props


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
                    pc.clip.remotion.composition, _graphics_props(ctx.project, pc.clip.remotion, seg), duration=pc.seconds,
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


def _stage_me(ctx: _Ctx) -> None:
    """Takes of you from the footage library -> clip/overlay videos. Speaking takes are lip-synced
    to the narration (project.lipsync provider) and mark the video as synthetic media."""
    from . import lipsync, me
    p = ctx.project
    lib = me.MeLibrary(me.library_dir(p.root))
    if not lib.items():
        lib.scan()
    used: set[str] = set()
    jobs = [(seg, obj) for seg in p.segments for obj in (*seg.clips, *seg.overlays) if getattr(obj, "me", None)]
    if not jobs:
        return
    if not lib.items():
        raise RuntimeError(f"素材库为空：把你的镜头放进 {lib.folder}（文件名即标签，例 backyard_glasses_talking_01.mp4），或在第 3 步「我的镜头」里上传")
    _set_progress("remotion", 0, len(jobs))
    for k, (seg, obj) in enumerate(jobs):
        _check_cancel()
        spec = obj.me
        need = ctx.narration[seg.id]
        take = lib.pick(spec.get("tags"), bool(spec.get("talking")), min_seconds=need if not spec.get("talking") else 0, avoid=used)
        if take is None:
            raise RuntimeError(f"segment {seg.id}: 素材库里没有 {'说话' if spec.get('talking') else '沉默'} 镜头（标签 {spec.get('tags')}）")
        used.add(take.name)
        lib.record_use(take)
        if spec.get("talking"):
            if p.lipsync == "none":
                _log(f"warning: {seg.id} 用了说话镜头但 lipsync=none，口型不会对上；设 lipsync: synclabs|musetalk 或改用沉默镜头")
            video = lipsync.sync(take, ctx.audio[seg.id], need, ctx.bd / "lipsync", provider=p.lipsync, log=_log)
            if p.lipsync != "none":
                p.youtube.disclosure.realistic_presenter = True
        else:
            video = take
        obj.video = video
        obj.me = None
        _set_progress("remotion", k + 1, len(jobs))
        _log(f"  me   {seg.id:<12} {take.name}{'  · lip-sync ' + p.lipsync if spec.get('talking') else ''}")


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


def _segment_key(project: Project, seg: Segment, audio: Path, encoder: str, beats: list[float] | None = None) -> str:
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
    # every project setting render_segment reads: one left out here is a setting that changes in
    # the UI and silently does nothing until the cache is cleared (look, transition style and the
    # segment fade did exactly that)
    settings = [project.width, project.height, project.fps, project.quality, encoder, project.motion_amount,
                project.effective_supersample, project.transition, project.transition_style, project.segment_fade,
                project.look, project.look_strength, project.punch_in, project.normalize_audio,
                project.voice_fx, project.voice_pitch, project.presenter.provider, render.CLIP_FORMAT,
                render.AUDIO_FORMAT]
    # The words are not in it: they reach the picture only through the narration audio (here) and
    # the sentence breaks 口播推近 cuts on (`beats`, when it is on). A fixed typo in the subtitles,
    # or the spoken text checked, re-dresses the segment instead of drawing it again.
    shape = {k: v for k, v in enc(seg).items() if k not in ("text", "spoken", "spoken_checked", "points", "alt_text")}
    blob = json.dumps([shape, enc(audio), settings, beats if project.punch_in else None],
                      sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def _sentence_breaks(words) -> list[float]:
    """Mid-pause after every clause mark in the narration: where a cut between shots lands unseen."""
    out = []
    for w, nxt in zip(words, words[1:]):
        if w.break_after:
            out.append(round((w.end + nxt.start) / 2, 3))
    return out


def _stage_render(ctx: _Ctx) -> None:
    """Segments in parallel (CPU/GPU-bound). A segment whose key is unchanged is reused from
    clips/<id>.<key>.mp4 — editing one segment re-renders only that one. The last 5 versions
    of each segment's clip are kept so reverting a segment is instant."""
    p = ctx.project

    def one(seg):
        _check_cancel()
        beats = _sentence_breaks(ctx.words.get(seg.id) or [])
        key = _segment_key(p, seg, ctx.audio[seg.id], ctx.encoder, beats)
        clip = ctx.bd / "clips" / f"{_safe(seg.id)}.{key}.mp4"
        if clip.exists() and clip.stat().st_size > 0:
            try:
                return seg.id, clip, ffmpeg.duration(clip), True
            except ffmpeg.FfmpegError:
                clip.unlink(missing_ok=True)
        dur = render.render_segment(p, seg, ctx.audio[seg.id], clip, encoder=ctx.encoder, beats=beats)
        # <seg>.<key>.mp4 only: the dressed copies (<seg>.<key>.d<k>.mp4) go with their clip
        siblings = sorted((f for f in (ctx.bd / "clips").glob(f"{_safe(seg.id)}.*.mp4") if f.stem.count(".") == 1),
                          key=lambda f: f.stat().st_mtime)
        for old in siblings[:-5]:
            old.unlink(missing_ok=True)
            for d in old.parent.glob(f"{old.stem}.d*.mp4"):
                d.unlink(missing_ok=True)
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
    # The opener is rendered first because its length decides where the narration starts: a
    # subtitle file written from zero would be early by exactly that much for the whole video.
    branded, lead, trail = _with_brand(ctx, bd, [ctx.clips[s.id] for s in p.segments])
    cues, timeline, cursor = [], [], lead
    if lead:
        timeline.append({"id": "__intro__", "label": None, "start": 0.0, "end": round(lead, 3)})
    for seg in p.segments:
        seg_cues = subtitles.build_cues(ctx.words[seg.id], offset=cursor, max_chars=p.subtitles.max_chars)
        if p.subtitles.bilingual and seg.alt_text:
            seg_cues = subtitles.bilingual(seg_cues, seg.alt_text)
        cues += seg_cues
        timeline.append({"id": seg.id, "label": seg.label, "start": round(cursor, 3), "end": round(cursor + ctx.durations[seg.id], 3)})
        cursor += ctx.durations[seg.id]
    if trail:
        timeline.append({"id": "__outro__", "label": None, "start": round(cursor, 3),
                         "end": round(cursor + trail, 3)})
    (bd / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    srt = bd / "final.srt"
    subtitles.write_srt(cues, srt)                       # the sidecar YouTube gets, always plain
    if not cues:
        _log("warning: no word timings received - subtitles skipped")
    if cues and p.subtitles.burn and not ffmpeg.has_filter("subtitles"):
        _log("warning: 这个 ffmpeg 没有 libass，字幕没有烧进画面（final.srt 照常生成）。macOS: brew install ffmpeg-full")

    # The unburned picture, for vertical shorts (they burn their own, bigger captions): a stream copy.
    merged = bd / "merged.mp4"
    render.concat(branded, merged)
    _set_progress("assemble", 1, 3)
    _check_cancel()

    dressed = _stage_dress(ctx, lead, cursor + trail)
    head, tail = (branded[:1] if lead else []), (branded[-1:] if trail else [])
    joined = bd / "dressed.mp4"
    render.concat([*head, *dressed, *tail], joined)
    _check_cancel()
    final = bd / "final.mp4"
    sound = None
    if p.transition_sfx != "none":
        from . import sfx
        # every hand-over between two segments; not the opener's (it has its own sting)
        cuts = [t["start"] for t in timeline if not t["id"].startswith("__")][1:]
        sound = sfx.track(p.transition_sfx, cuts, cursor + trail, bd / "sfx.wav")
        if sound:
            _log(f"  sfx        {p.transition_sfx} × {len(cuts)}")
    # the picture is finished per segment: here only the sound is mixed, the video stream-copied
    render.finalize(p, joined, None, cursor + trail, final, hook_at=lead, sfx=sound, content_end=cursor, dressed=True)
    joined.unlink(missing_ok=True)                       # final.mp4 holds the same picture
    _set_progress("assemble", 2, 3)

    thumb_src = next((s.image for s in p.segments if s.image), None)
    if thumb_src is None:
        thumb_src = bd / "thumb_src.jpg"
        ffmpeg.run(["-y", "-ss", "1", "-i", str(ctx.clips[p.segments[0].id]), "-frames:v", "1", str(thumb_src)])
    thumbnail.make(thumb_src, p.thumbnail_text or p.title, bd / "thumbnail.jpg")
    try:
        # kept for the per-platform covers, which are drawn at each app's own shape at export
        from PIL import Image
        with Image.open(thumb_src) as im:
            im.convert("RGB").save(bd / "cover_src.jpg", quality=92)
    except OSError:
        pass
    credits = _credits(p)
    if credits:
        (bd / "credits.txt").write_text(credits, encoding="utf-8")
    _set_progress("assemble", 3, 3)
    return final, timeline, cursor


def _dress_key(p: Project, clip: Path, sub_text: str, hook_window, progress, over_face: bool, encoder: str) -> str:
    """Everything dress_segment lays on: a change to any of it re-dresses the segment."""
    import hashlib
    from . import brand as brandkit
    st = p.subtitles
    layers = [clip.name, sub_text, st.burn, st.font, st.font_size, st.style, st.margin_v, p.theme.get("badge") if p.theme else None,
              p.theme.get("palette") if p.theme else None, p.theme.get("side") if p.theme else None,
              p.hook.text, p.hook.seconds, hook_window, over_face, p.progress_bar, progress,
              brandkit.load(p.raw).accent, p.width, p.height, p.fps, p.quality, encoder, render.CLIP_FORMAT,
              ffmpeg.has_filter("subtitles")]
    blob = json.dumps(layers, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]


def _stage_dress(ctx: _Ctx, lead: float, total: float) -> list[Path]:
    """Each segment with its subtitles, badge, 开场大字 and progress bar, in script order.

    Cached beside the segment's clip, so a build where nothing changed re-encodes nothing and a
    build after one edit re-dresses one segment — the whole-video pass this replaces re-encoded
    every frame on every build (27 s for 3 minutes on an M1). Subtitles are written per segment
    from zero: a segment's cues never cross into the next one, the clip is cut there anyway."""
    p, bd = ctx.project, ctx.bd
    first = p.segments[0].clips[0] if p.segments and p.segments[0].clips else None
    over_face = bool(first and render.is_talking_head(first))
    burn = p.subtitles.burn and ffmpeg.has_filter("subtitles")
    colour = None
    if burn and p.subtitles.highlight != "none":
        from . import brand as brandkit
        colour = p.subtitles.highlight_colour or brandkit.load(p.raw).accent
        _log(f"  subtitles  {p.subtitles.highlight} highlight in {colour}")
    jobs, offset = [], 0.0
    for seg in p.segments:
        jobs.append((seg, offset))
        offset += ctx.durations[seg.id]
    subs_dir = bd / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    def one(job):
        seg, at = job
        _check_cancel()
        clip = ctx.clips[seg.id]
        sub = None
        sub_text = ""
        if burn:
            cues = subtitles.build_cues(ctx.words[seg.id], offset=0.0, max_chars=p.subtitles.max_chars)
            if p.subtitles.bilingual and seg.alt_text:
                cues = subtitles.bilingual(cues, seg.alt_text)
            if cues:
                if colour:
                    sub = subs_dir / f"{_safe(seg.id)}.ass"
                    subtitles.write_ass(cues, sub, font=p.subtitles.font, font_size=p.subtitles.font_size,
                                        margin_v=p.subtitles.margin_v, box=p.subtitles.style == "box",
                                        highlight=p.subtitles.highlight, colour=colour,
                                        width=p.width, height=p.height,
                                        box_colour=p.subtitles.box_colour, text_colour=p.subtitles.text_colour)
                else:
                    sub = subs_dir / f"{_safe(seg.id)}.srt"
                    subtitles.write_srt(cues, sub)
                sub_text = sub.read_text(encoding="utf-8")
        window = (0.0 - at, p.hook.seconds - at) if p.hook.text and p.hook.seconds - at > 0 else None
        progress = (lead + at, total) if p.progress_bar else None
        key = _dress_key(p, clip, sub_text, window, progress, over_face, ctx.encoder)
        out = clip.with_name(f"{clip.stem}.d{key}.mp4")
        if out.is_file() and out.stat().st_size > 0:
            return out, True
        for old in clip.parent.glob(f"{clip.stem}.d*.mp4"):       # one dressed copy per clip is enough
            old.unlink(missing_ok=True)
        dressed = render.dress_segment(p, clip, out, encoder=ctx.encoder, srt=sub, hook_window=window,
                                       hook_over_face=over_face, progress=progress)
        return dressed, dressed == clip            # nothing to lay on: the clip itself, no work done

    with ThreadPoolExecutor(max_workers=_workers(p)) as pool:
        results = list(pool.map(one, jobs))
    fresh = sum(1 for _, cached in results if not cached)
    if fresh:
        _log(f"  dress      {fresh} segment(s) re-dressed, {len(results) - fresh} cached")
    return [r for r, _ in results]


def _with_brand(ctx, bd: Path, clips: list[Path]) -> tuple[list[Path], float, float]:
    """Put the channel's opener in front and its end card at the back.

    The opener goes *after* nothing — it is the first thing in the file — but it is kept to about
    a second because an intro over ~5 s measurably lowers the share of viewers still there at
    0:30. A channel that wants a cold open simply turns `brand.intro` off and starts on its hook.
    Failures here never sink a render: the video is the point, the badge is not.

    Returns (clips, opener seconds, end-card seconds). The opener length matters to the caller:
    it pushes every word of narration later in the file, so subtitles and chapter marks have to
    move with it or the whole video's captions run early."""
    from . import brand as brandkit
    p = ctx.project
    kit = brandkit.for_project(brandkit.load(p.raw), p.theme)
    if not (kit.name and (kit.intro or kit.outro)):
        return clips, 0.0, 0.0
    folder = bd / "brand"
    folder.mkdir(parents=True, exist_ok=True)
    head, tail = [], []
    try:
        if kit.intro:
            clip = brandkit.render_opener(kit, folder, p.width, p.height, p.fps, log=_log)
            head = [brandkit.with_audio(clip, Path(kit.sting) if kit.sting else None,
                                        folder / "intro.mp4", kit.intro_seconds)]
        if kit.outro:
            clip = brandkit.render_endcard(kit, folder, p.width, p.height, p.fps, log=_log)
            tail = [brandkit.with_audio(clip, Path(kit.outro_music) if kit.outro_music else None,
                                        folder / "outro.mp4", kit.outro_seconds)]
    except Exception as e:  # noqa: BLE001  a missing Node or a bad logo must not fail the video
        _log(f"warning: brand clips skipped ({e})")
        return clips, 0.0, 0.0
    if clips:
        head = [render.match_clip(c, clips[0], p, ctx.encoder, c.with_name(c.stem + "_matched.mp4")) for c in head]
        tail = [render.match_clip(c, clips[0], p, ctx.encoder, c.with_name(c.stem + "_matched.mp4")) for c in tail]
    lead = ffmpeg.duration(head[0]) if head else 0.0
    trail = ffmpeg.duration(tail[0]) if tail else 0.0
    return [*head, *clips, *tail], lead, trail


def build(project: Project, *, only_tts: bool = False, burn: bool | None = None) -> Path:
    """TTS -> (title cards) -> assets -> remotion -> render segments -> assemble."""
    with awake.hold():      # a render outlasts a laptop's idle-sleep timer, and nobody is typing
        return _build(project, only_tts=only_tts, burn=burn)


_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def fill_bare_segments(project: Project, log=None) -> list[str]:
    """Pictures are optional: a segment nobody gave one to still renders, with the best thing it has.

        your own recording as its narration, and it is a video  -> that take, full screen
        only a small window (a take over nothing)                 -> the window, full screen
        nothing at all                                            -> a page in the template's
                                                                     colour with the chapter name
    Said in the log, segment by segment — never silent; pictures can be added later at any time."""
    from .project import Clip
    filled = []
    for seg in project.segments:
        if seg.clips:
            continue
        own = seg.narration if seg.narration and Path(seg.narration).suffix.lower() in _VIDEO_EXT else None
        window = next((o for o in seg.overlays if o.video and not o.avatar and (o.height is None or o.size < 1)), None)
        if own:
            seg.clips = [Clip(video=Path(own))]
            why = "用你录的这段视频全屏"
        elif window is not None:
            seg.overlays.remove(window)
            seg.clips = [Clip(video=window.video, in_=window.in_, out=window.out)]
            why = "把小窗放大成全屏"
        else:
            seg.clips = [Clip(image=render.plain_page(project, seg.id, seg.label or ""), motion="none")]
            why = "用纯色底" + ("（写着章节名）" if seg.label else "")
        filled.append(seg.id)
        if log:
            log(f"  画面 {seg.id:<12} 还没配图：{why}——想配图随时去第 3 步「画面」")
    return filled


def _build(project: Project, *, only_tts: bool, burn: bool | None) -> Path:
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
        _stage_retention(ctx)
        if only_tts:
            return bd
        _stage_title_cards(ctx)
        _stage_assets(ctx)
        _stage_remotion(ctx)
        _stage_me(ctx)
        _stage_presenter(ctx)
        fill_bare_segments(ctx.project, log=_log)
        _stage_render(ctx)
        final, timeline, total = _stage_assemble(ctx)
        _set_progress("done", 1, 1)
        # the file's own length: the narration's end left out the end card's seconds
        _log(f"done in {time.time() - t0:.1f}s · {ffmpeg.duration(final):.1f}s video · {final}")
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
