"""智能剪口播：剪掉说话中间的停顿和气口，像剪映的「智能剪口播」。

A talking-head take is mostly speech with gaps: the breath before a sentence, the second spent
finding the next line on the prompter, the "嗯" that never came out. Cutting those by hand is the
dull half of editing; cutting them by level is what every editor's "remove silence" does, and it
needs no model — `silencedetect` already knows where the room was quiet.

Three numbers decide the cut, and the defaults are tuned for narration rather than for a podcast:

    threshold  -38 dB   quieter than this is "not speaking". A noisy room needs it higher (-32).
    min_gap    0.45 s   only gaps at least this long are cut: shorter ones are the rhythm of
                        speech, and cutting them makes a person sound like a machine gun.
    pad        0.12 s   kept on each side of every cut, so a word's soft start and its tail
                        (the consonant you hear but the meter barely sees) survive.

Picture and sound are cut by the same ranges in one pass, so the lips stay on the words. The
result is a new file; the original is never touched.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .. import ffmpeg
from . import VideoToolError

THRESHOLD_DB = -38.0
MIN_GAP = 0.45
PAD = 0.12


def silences(path: Path, *, threshold_db: float = THRESHOLD_DB, min_gap: float = MIN_GAP) -> list[tuple[float, float]]:
    """Quiet stretches of at least `min_gap` seconds, as (start, end)."""
    total = ffmpeg.duration(path)
    r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(path), "-vn",
                        "-af", f"silencedetect=noise={threshold_db}dB:d={min_gap}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise VideoToolError(f"读不出声音：{r.stderr.strip()[-300:]}")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total          # silence running to the end of the file
        out.append((max(0.0, s), min(total, e)))
    return out


def keep_ranges(total: float, quiet: list[tuple[float, float]], *, pad: float = PAD) -> list[tuple[float, float]]:
    """The spoken parts, each widened by `pad`, overlaps merged."""
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in quiet:
        if s > cursor:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < total:
        keep.append((cursor, total))
    padded = [(round(max(0.0, a - pad), 3), round(min(total, b + pad), 3)) for a, b in keep if b - a > 0.05]
    merged: list[tuple[float, float]] = []
    for a, b in padded:
        if merged and a <= merged[-1][1] + 0.02:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def plan(path: Path, *, threshold_db: float = THRESHOLD_DB, min_gap: float = MIN_GAP, pad: float = PAD) -> dict:
    """What a cut would do, without doing it: for the UI's before/after bar."""
    total = ffmpeg.duration(path)
    keep = keep_ranges(total, silences(path, threshold_db=threshold_db, min_gap=min_gap), pad=pad)
    kept = sum(b - a for a, b in keep)
    return {"total": round(total, 3), "kept": round(kept, 3), "removed": round(total - kept, 3),
            "cuts": max(0, len(keep) - 1) + (1 if keep and keep[0][0] > 0.01 else 0)
                    + (1 if keep and keep[-1][1] < total - 0.01 else 0),
            "keep": [[round(a, 3), round(b, 3)] for a, b in keep]}


def cut(src: Path, out: Path, *, threshold_db: float = THRESHOLD_DB, min_gap: float = MIN_GAP,
        pad: float = PAD, fps: int = 30, log=print) -> dict:
    """Write `out` with the gaps removed. Returns the plan that was applied."""
    src, out = Path(src), Path(out)
    p = plan(src, threshold_db=threshold_db, min_gap=min_gap, pad=pad)
    keep = p["keep"]
    if not keep:
        raise VideoToolError("整条都是静音——阈值是不是设得太高了？")
    has_video = True
    try:
        ffmpeg.video_size(src)
    except ffmpeg.FfmpegError:
        has_video = False
    # trim+concat per range is exact to the frame; a select expression over hundreds of ranges is
    # not, and drifts the audio against the picture on a long take
    parts, labels = [], []
    for i, (a, b) in enumerate(keep):
        if has_video:
            parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]" if has_video else f"[a{i}]")
    n = len(keep)
    graph = ";".join(parts) + ";" + "".join(labels) + (f"concat=n={n}:v=1:a=1[v][a]" if has_video else f"concat=n={n}:v=0:a=1[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    tail: list[str] = []
    if has_video:
        tail += ["-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps)]
    tail += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    if len(graph) < 20000:          # Windows caps a command line at 32k characters
        ffmpeg.run(["-y", "-i", str(src), "-filter_complex", graph, *tail])
    else:
        # a long take has a long graph: read it from a file. ffmpeg 7.1 spells that `-/filter_complex`,
        # older builds `-filter_complex_script` (removed in 8)
        script = out.with_suffix(".filter.txt")
        script.write_text(graph, encoding="utf-8")
        try:
            try:
                ffmpeg.run(["-y", "-i", str(src), "-/filter_complex", str(script), *tail])
            except ffmpeg.FfmpegError:
                ffmpeg.run(["-y", "-i", str(src), "-filter_complex_script", str(script), *tail])
        finally:
            script.unlink(missing_ok=True)
    log(f"剪口播：{p['total']:.1f}s → {p['kept']:.1f}s，剪掉 {p['removed']:.1f}s（{p['cuts']} 处）")
    return {**p, "out": str(out)}
