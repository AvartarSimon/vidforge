"""ffmpeg rendering: clips -> segment clip -> concat -> BGM mix / subtitle burn.

Quality model
    draft : crf 23, preset veryfast, 1x supersample   (layout previews, ~3x faster)
    final : crf 18, preset medium,  2x supersample    (upload quality)
Segments are encoded once at final quality; concat is a stream copy; the finishing pass
re-encodes only when subtitles are burned. Hardware encoders (NVENC / QSV / AMF /
VideoToolbox) are used for the *segment* encodes when `encoder: auto` finds one — they
cut render time 3–6x on long videos; libx264 stays the default when none is present.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import ffmpeg
from .project import Clip, Project, Segment

MIN_IMAGE_SECONDS = 1.5


# -- encoder selection ------------------------------------------------------------------------
@lru_cache(maxsize=None)
def available_encoders() -> set[str]:
    try:
        out = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-encoders"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    except ffmpeg.FfmpegError:
        return set()
    return {line.split()[1] for line in out.splitlines() if line.startswith(" V") and len(line.split()) > 1}


@lru_cache(maxsize=None)
def encoder_works(name: str) -> bool:
    """A listed hardware encoder may still fail (no GPU, driver); probe with a 1-frame encode."""
    if name == "libx264":
        return True
    try:
        r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                            "-i", "color=c=black:s=256x256:r=30", "-frames:v", "3", "-c:v", name, "-f", "null", "-"],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def pick_encoder(project: Project) -> str:
    if project.encoder != "auto":
        return project.encoder
    for cand in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"):
        if cand in available_encoders() and encoder_works(cand):
            return cand
    return "libx264"


def video_codec_args(project: Project, encoder: str | None = None) -> list[str]:
    enc = encoder or pick_encoder(project)
    final = project.quality == "final"
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", "medium" if final else "veryfast", "-crf", "18" if final else "23",
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1"]
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5" if final else "p2", "-rc", "vbr", "-cq", "19" if final else "24",
                "-b:v", "0", "-pix_fmt", "yuv420p", "-profile:v", "high"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", "19" if final else "24", "-preset", "medium" if final else "veryfast",
                "-pix_fmt", "nv12", "-profile:v", "high"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality" if final else "speed", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21",
                "-pix_fmt", "yuv420p"]
    if enc == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-q:v", "65" if final else "50", "-pix_fmt", "yuv420p", "-profile:v", "high"]
    return ["-c:v", enc]


AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


# -- clip planning ------------------------------------------------------------------------------
@dataclass
class PlannedClip:
    clip: Clip
    seconds: float
    loop: bool = False       # video shorter than `seconds`: loop it


def plan_clips(seg: Segment, target: float) -> list[PlannedClip]:
    """Decide how long each clip shows so the segment lasts exactly `target` seconds.

    natural lengths: video slice (out-in) or the full video (probed), image `duration`;
    images without duration share what is left equally (>= MIN_IMAGE_SECONDS).
    Too long  -> shrink flexible images first, then cut from the end (`fit` is about
                 too-short; audio always wins when clips run over).
    Too short -> `stretch`: extend the last clip (video loops, image holds longer);
                 `trim`: same, there is nothing else sensible to do without a gap.
    """
    if not seg.clips:
        raise ValueError(f"segment {seg.id} has no clips")
    natural: list[float | None] = []
    for c in seg.clips:
        if c.remotion is not None:
            natural.append(c.duration)                 # fixed length if given, else its share
        elif c.video is not None:
            if c.slice_length:
                natural.append(c.slice_length)
            else:
                full = ffmpeg.duration(c.video)
                natural.append(max(0.1, full - (c.in_ or 0.0)))
        else:
            natural.append(c.duration)

    fixed = sum(n for n in natural if n is not None)
    flexible = [i for i, n in enumerate(natural) if n is None]
    share = max(MIN_IMAGE_SECONDS, (target - fixed) / len(flexible)) if flexible else 0.0
    seconds = [n if n is not None else share for n in natural]

    total = sum(seconds)
    if total > target + 0.01:
        # 1) flexible images -> minimum  2) fixed-duration images -> minimum (a typed hold is
        # softer than a deliberately sliced video)  3) cut video/remotion clips from the end
        excess = total - target
        soft = flexible + [i for i, c in enumerate(seg.clips) if c.image is not None and i not in flexible]
        for i in soft:
            take = min(max(0.0, seconds[i] - MIN_IMAGE_SECONDS), excess)
            seconds[i] -= take
            excess -= take
        for i in range(len(seconds) - 1, -1, -1):
            if excess <= 0.01:
                break
            if seg.clips[i].image is not None:
                continue
            take = min(seconds[i], excess)               # a clip cut to nothing is dropped below
            seconds[i] -= take
            excess -= take
        if excess > 0.01:                              # only images left: cut them too, from the end
            for i in range(len(seconds) - 1, -1, -1):
                take = min(seconds[i] if i > 0 else seconds[i], excess)
                seconds[i] -= take
                excess -= take
                if excess <= 0.01:
                    break
    elif total < target - 0.01:
        seconds[-1] += target - total

    planned = []
    for c, s in zip(seg.clips, seconds):
        if s <= 0.05:
            continue
        loop = c.video is not None and c.remotion is None and (c.slice_length or ffmpeg.duration(c.video) - (c.in_ or 0.0)) < s - 0.05
        planned.append(PlannedClip(c, round(s, 3), loop))
    return planned


# -- clip rendering ---------------------------------------------------------------------------------
def _zoompan_exprs(motion: str, amount: float, frames: int) -> tuple[str, str, str]:
    # smoothstep easing: the move starts and ends gently instead of the mechanical linear ramp
    t = f"(on/{frames})"
    p = f"({t}*{t}*(3-2*{t}))"
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z_max = 1 + amount
    if motion == "zoom_in":
        return f"1+{amount}*{p}", center_x, center_y
    if motion == "zoom_out":
        return f"{z_max}-{amount}*{p}", center_x, center_y
    if motion == "pan_right":
        return f"{z_max}", f"(iw-iw/zoom)*{p}", center_y
    if motion == "pan_left":
        return f"{z_max}", f"(iw-iw/zoom)*(1-{p})", center_y
    return "1", "0", "0"


def render_clip(project: Project, pc: PlannedClip, out: Path, encoder: str) -> None:
    """One clip -> silent mp4 of exactly pc.seconds at project size/fps."""
    c, dur = pc.clip, pc.seconds
    w, h, fps = project.width, project.height, project.fps
    out.parent.mkdir(parents=True, exist_ok=True)
    if c.video is not None:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps={fps},setsar=1"
        codec = video_codec_args(project, encoder)
        if pc.loop and (c.in_ or c.out is not None):
            # -stream_loop restarts at the file start, not at -ss: cut the slice first, then loop that
            slice_path = out.with_name(out.stem + "_slice.mp4")
            args = ["-y", "-ss", f"{c.in_ or 0:.3f}", "-i", str(c.video), "-an", "-vf", vf]
            if c.out is not None:
                args += ["-t", f"{max(0.1, c.out - (c.in_ or 0)):.3f}"]
            ffmpeg.run(args + [*codec, str(slice_path)])
            ffmpeg.run(["-y", "-stream_loop", "-1", "-i", str(slice_path), "-an", "-t", f"{dur:.3f}", "-c:v", "copy", str(out)])
            return
        args = ["-y"]
        if pc.loop:
            args += ["-stream_loop", "-1"]
        if c.in_:
            args += ["-ss", f"{c.in_:.3f}"]
        args += ["-i", str(c.video), "-an", "-vf", vf, "-t", f"{dur:.3f}", *codec, str(out)]
        ffmpeg.run(args)
        return
    ss = project.effective_supersample
    sw, sh = w * ss, h * ss
    frames = max(1, round(dur * fps))
    z, x, y = _zoompan_exprs(c.motion, project.motion_amount, frames)
    sharpen = ",unsharp=5:5:0.4:3:3:0.0" if project.quality == "final" else ""
    zp = f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps}{sharpen},setsar=1"
    if image_needs_fill(c.image, w, h):
        # portrait / square picture: blurred, darkened copy fills the frame, the whole picture sits on top
        vf = (f"[0:v]split=2[bg][fg];"
              f"[bg]scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=bicubic,crop={sw}:{sh},"
              f"boxblur=luma_radius={max(8, min(sw, sh) // 40)}:luma_power=2,eq=brightness=-0.15[bgb];"
              f"[fg]scale={sw}:{sh}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
              f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,{zp}[v]")
        ffmpeg.run(["-y", "-i", str(c.image), "-filter_complex", vf, "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(fps),
                    *video_codec_args(project, encoder), str(out)])
        return
    vf = f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,crop={sw}:{sh},{zp}"
    ffmpeg.run(["-y", "-i", str(c.image), "-vf", vf, "-t", f"{dur:.3f}", "-r", str(fps),
                *video_codec_args(project, encoder), str(out)])


@lru_cache(maxsize=4096)
def image_size(path: str) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def image_needs_fill(path: Path, w: int, h: int) -> bool:
    """True when cover-cropping would discard more than ~1/3 of the picture (portrait, square,
    tall maps): then we letterbox over a blurred fill instead."""
    try:
        iw, ih = image_size(str(path))
    except Exception:  # noqa: BLE001
        return False
    frame = w / h
    ratio = iw / ih if ih else frame
    return ratio < frame * 0.72 or ratio > frame * 1.6


def _xfade_join(project: Project, parts: list[Path], seconds: list[float], out: Path, encoder: str) -> None:
    """Crossfade consecutive clips (re-encode). Total length = sum(seconds) - (n-1)*t."""
    t = project.transition
    args = ["-y"]
    for p in parts:
        args += ["-i", str(p)]
    filt, prev, offset = [], "[0:v]", 0.0
    for i in range(1, len(parts)):
        offset += seconds[i - 1] - t
        label = f"[v{i}]" if i < len(parts) - 1 else "[v]"
        filt.append(f"{prev}[{i}:v]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}{label}")
        prev = label
    args += ["-filter_complex", ";".join(filt), "-map", "[v]", "-an", *video_codec_args(project, encoder), str(out)]
    ffmpeg.run(args)


def render_segment(project: Project, seg: Segment, audio: Path, out: Path, *, encoder: str | None = None,
                   cache_dir: Path | None = None) -> float:
    """All clips of a segment, fitted to the narration, muxed with the voice. Returns seconds."""
    encoder = encoder or pick_encoder(project)
    narration = ffmpeg.duration(audio)
    target = narration + seg.pause_after
    planned = plan_clips(seg, target)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = (cache_dir or out.parent) / f"{out.stem}_parts"
    work.mkdir(parents=True, exist_ok=True)

    t = project.transition if len(planned) > 1 and project.transition > 0 else 0.0
    if t:
        # each clip must be longer by the overlap it loses; keep ends exact
        for i, pc in enumerate(planned):
            if i < len(planned) - 1:
                pc.seconds += t
    parts: list[Path] = []
    for i, pc in enumerate(planned):
        part = work / f"{i:02d}.mp4"
        render_clip(project, pc, part, encoder)
        parts.append(part)

    if len(parts) == 1:
        visual = parts[0]
    else:
        visual = work / "joined.mp4"
        if t:
            _xfade_join(project, parts, [p.seconds for p in planned], visual, encoder)
        else:
            concat(parts, visual)

    overlays = [o for o in seg.overlays if o.image or o.video]
    if overlays:
        visual = apply_overlays(project, overlays, visual, target, work / "overlaid.mp4", encoder)

    norm = "loudnorm=I=-16:TP=-1.5:LRA=11," if project.normalize_audio and not audio_is_silent(audio) else ""
    ffmpeg.run(["-y", "-i", str(visual), "-i", str(audio),
                "-filter_complex", f"[1:a]{norm}apad=pad_dur={seg.pause_after}[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", *AUDIO_ARGS,
                "-t", f"{target:.3f}", "-movflags", "+faststart", str(out)])
    # the container's real length (AAC frames are 21 ms; over 40 segments the planned lengths
    # would drift subtitles by up to a second) — the timeline must use this
    return ffmpeg.duration(out)


def _position_expr(position: str, margin: int) -> tuple[str, str]:
    """overlay x/y expressions (W,H = frame; w,h = layer)."""
    if "," in position:
        fx, fy = (float(v) for v in position.split(","))
        return f"(W-w)*{fx}", f"(H-h)*{fy}"
    col = "left" if "left" in position else "right" if "right" in position else "center"
    row = "top" if "top" in position else "bottom" if "bottom" in position else "center"
    x = {"left": f"{margin}", "right": f"W-w-{margin}", "center": "(W-w)/2"}[col]
    y = {"top": f"{margin}", "bottom": f"H-h-{margin}", "center": "(H-h)/2"}[row]
    return x, y


def apply_overlays(project: Project, overlays: list, visual: Path, total: float, out: Path, encoder: str) -> Path:
    """Composite picture-in-picture layers onto the segment's visual. Layers are muted; a video
    layer shorter than its window loops; `animate` slides the layer in from its nearest edge or
    fades it in; `border` draws a thin light frame."""
    w, h = project.width, project.height
    margin = max(24, round(w * 0.02))
    args: list[str] = ["-y", "-i", str(visual)]
    filters: list[str] = []
    prev = "[0:v]"
    for i, o in enumerate(overlays, start=1):
        dur = o.duration if o.duration is not None else max(0.1, total - o.at)
        dur = min(dur, max(0.1, total - o.at))
        if o.image is not None:
            args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(o.image)]
        else:
            args += ["-stream_loop", "-1"]
            if o.in_:
                args += ["-ss", f"{o.in_:.3f}"]
            slice_len = (o.out - (o.in_ or 0)) if o.out is not None else None
            args += ["-t", f"{min(dur, slice_len) if slice_len else dur:.3f}", "-i", str(o.video)]
        lw = max(16, round(w * o.size))
        chain = f"[{i}:v]scale={lw}:-2:flags=lanczos,fps={project.fps},format=rgba"
        if o.border:
            b = max(2, round(w / 640))
            chain += f",pad=iw+{2 * b}:ih+{2 * b}:{b}:{b}:color=white@0.9"
        if o.animate == "fade":
            chain += ",fade=t=in:st=0:d=0.4:alpha=1"
        chain += f",setpts=PTS+{o.at:.3f}/TB[ov{i}]"
        filters.append(chain)
        x, y = _position_expr(o.position, margin)
        if o.animate == "slide":
            # slide in over 0.45 s from the edge the layer is anchored to (default: from the right)
            direction = "-" if "left" in o.position else "+"
            x = f"({x}){direction}(w*max(0,1-(t-{o.at:.3f})/0.45))"
        label = f"[v{i}]" if i < len(overlays) else "[vout]"
        filters.append(f"{prev}[ov{i}]overlay=x='{x}':y='{y}':enable='between(t,{o.at:.3f},{o.at + dur:.3f})':eof_action=pass{label}")
        prev = label
    args += ["-filter_complex", ";".join(filters), "-map", "[vout]", "-an", "-t", f"{total:.3f}",
             *video_codec_args(project, encoder), str(out)]
    ffmpeg.run(args)
    return out


def audio_is_silent(path: Path, floor_db: float = -60.0) -> bool:
    """loudnorm turns digital silence into NaN and the AAC encoder fails; detect it first."""
    try:
        r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        for line in r.stderr.splitlines():
            if "mean_volume:" in line:
                return float(line.split("mean_volume:")[1].split("dB")[0]) < floor_db
    except Exception:  # noqa: BLE001
        pass
    return False


def concat(clips: list[Path], out: Path) -> None:
    """Lossless concat of clips that share codec parameters (they do — same render call)."""
    list_file = out.with_suffix(".txt")
    list_file.write_text("".join(f"file '{str(c.resolve()).replace(chr(92), '/')}'\n" for c in clips), encoding="utf-8")
    ffmpeg.run(["-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)])


def finalize(project: Project, merged: Path, srt: Path | None, total: float, out: Path) -> None:
    """Mix BGM under the narration (ducked while the voice speaks) and optionally burn
    subtitles. One encode pass; video is stream-copied when nothing is burned."""
    args: list[str] = ["-y", "-i", str(merged)]
    filters: list[str] = []
    maps: list[str] = []

    if srt is not None and project.subtitles.burn:
        st = project.subtitles
        if st.style == "box":       # semi-transparent box behind the text (BorderStyle 3 uses BackColour)
            style = (f"FontName={st.font},FontSize={st.font_size},BorderStyle=4,Outline=2,Shadow=0,"
                     f"MarginV={st.margin_v},PrimaryColour=&H00FFFFFF,OutlineColour=&H99000000,BackColour=&H99000000")
        else:
            style = (f"FontName={st.font},FontSize={st.font_size},Outline=1,Shadow=0,"
                     f"MarginV={st.margin_v},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000")
        filters.append(f"[0:v]subtitles='{ffmpeg.filter_path(srt)}':force_style='{style}'[v]")
        maps += ["-map", "[v]", *video_codec_args(project, "libx264")]
    else:
        maps += ["-map", "0:v", "-c:v", "copy"]

    if project.bgm is not None:
        b = project.bgm
        args += ["-stream_loop", "-1", "-i", str(b.file)]
        fade_start = max(0.0, total - b.fade_out)
        chain = f"[1:a]volume={b.volume_db}dB,afade=t=out:st={fade_start:.3f}:d={b.fade_out}[bg]"
        if b.duck:
            # voice on the sidechain pushes the music down ~10 dB while speaking, recovers in 0.4 s
            filters.append(f"[0:a]asplit=2[voice][sc];{chain};"
                           f"[bg][sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400:makeup=1[bgd];"
                           f"[voice][bgd]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]")
        else:
            filters.append(f"{chain};[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]")
        maps += ["-map", "[a]"]
    else:
        maps += ["-map", "0:a"]
    maps += ["-c:a", "aac", "-b:a", "192k"]

    if filters:
        args += ["-filter_complex", ";".join(filters)]
    tmp = out.with_name(out.stem + ".tmp" + out.suffix)
    args += maps + ["-t", f"{total:.3f}", "-movflags", "+faststart", str(tmp)]
    ffmpeg.run(args)
    replace_with_retry(tmp, out)


def replace_with_retry(src: Path, dst: Path, attempts: int = 10) -> None:
    """os.replace, retried: on Windows the old final.mp4 may still be open in the browser."""
    import os
    import time as _t
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            _t.sleep(0.5 * (i + 1))
