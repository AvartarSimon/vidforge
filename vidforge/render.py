"""ffmpeg rendering: Ken Burns clip per segment, concat, BGM mix, subtitle burn."""

from __future__ import annotations

from pathlib import Path

from . import ffmpeg
from .project import Project, Segment


def _zoompan_exprs(motion: str, amount: float, frames: int) -> tuple[str, str, str]:
    """Return (zoom, x, y) expressions for ffmpeg's zoompan.

    `on` is the output frame index in [0, d); progress p = on/d runs 0 -> 1.
    """
    p = f"(on/{frames})"
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    z_max = 1 + amount
    if motion == "zoom_in":
        return f"1+{amount}*{p}", center_x, center_y
    if motion == "zoom_out":
        return f"{z_max}-{amount}*{p}", center_x, center_y
    if motion == "pan_right":          # camera moves right: visible window slides left -> right
        return f"{z_max}", f"(iw-iw/zoom)*{p}", center_y
    if motion == "pan_left":
        return f"{z_max}", f"(iw-iw/zoom)*(1-{p})", center_y
    return "1", "0", "0"               # none


def render_segment(project: Project, seg: Segment, audio: Path, out: Path) -> float:
    """Render one segment: still image + camera move, narration + trailing pause.

    Returns the clip duration in seconds.
    """
    narration = ffmpeg.duration(audio)
    dur = narration + seg.pause_after
    frames = max(1, round(dur * project.fps))
    sw, sh = project.width * project.supersample, project.height * project.supersample
    z, x, y = _zoompan_exprs(seg.motion, project.motion_amount, frames)

    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={project.width}x{project.height}:fps={project.fps},"
        f"format=yuv420p"
    )
    af = f"apad=pad_dur={seg.pause_after}"

    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run([
        "-y",
        "-i", str(seg.image),
        "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(project.fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(out),
    ])
    return dur


def concat(clips: list[Path], out: Path) -> None:
    """Lossless concat of clips that share codec parameters (they do — same render call)."""
    list_file = out.with_suffix(".txt")
    list_file.write_text(
        "".join(f"file '{str(c.resolve()).replace(chr(92), '/')}'\n" for c in clips),
        encoding="utf-8",
    )
    ffmpeg.run(["-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)])


def finalize(project: Project, merged: Path, srt: Path | None, total: float, out: Path) -> None:
    """Mix BGM under the narration and optionally burn subtitles. One encode pass."""
    args: list[str] = ["-y", "-i", str(merged)]
    filters: list[str] = []
    maps: list[str] = []

    # video
    if srt is not None and project.subtitles.burn:
        st = project.subtitles
        style = (f"FontName={st.font},FontSize={st.font_size},Outline=1,Shadow=0,"
                 f"MarginV={st.margin_v},PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000")
        filters.append(f"[0:v]subtitles='{ffmpeg.filter_path(srt)}':force_style='{style}'[v]")
        maps += ["-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "19"]
    else:
        maps += ["-map", "0:v", "-c:v", "copy"]

    # audio
    if project.bgm is not None:
        b = project.bgm
        args += ["-stream_loop", "-1", "-i", str(b.file)]
        fade_start = max(0.0, total - b.fade_out)
        filters.append(
            f"[1:a]volume={b.volume_db}dB,afade=t=out:st={fade_start:.3f}:d={b.fade_out}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
        maps += ["-map", "[a]"]
    else:
        maps += ["-map", "0:a"]
    maps += ["-c:a", "aac", "-b:a", "192k"]

    if filters:
        args += ["-filter_complex", ";".join(filters)]
    args += maps + ["-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    ffmpeg.run(args)
