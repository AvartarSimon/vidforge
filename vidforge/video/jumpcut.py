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

`fillers=True` also cuts the 嗯 / 呃 / um / uh between sentences (Descript's "remove filler words").
The level meter cannot tell a 嗯 from a word, so Whisper says *which* sounds are fillers — but its
word boundaries are a few hundred ms loose, too loose to cut on. The cut is therefore made on the
stretch of sound the level meter finds around the filler, and only when that stretch holds the
filler and nothing else; anything less certain is left in and counted. A stray 嗯 costs nothing,
a clipped word costs the take. 那个 / 就是 / 然后 are left alone: as often as not they carry meaning.
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

FILLERS = {"嗯", "嗯嗯", "呃", "呃呃", "额", "唔", "um", "umm", "uh", "uhh", "uhm", "er", "erm", "hmm", "mm"}
# Whisper tidies speech up unless shown that the transcript keeps the hesitations
_PROMPT = {"zh": "嗯，那个，呃，就是说，嗯……然后呃，我们来看。", "en": "Um, so, uh, I mean, like, hmm, okay."}
_FILLER_STRIP = "，,。.!！?？…、 "
# the UI re-plans on every slider move; Whisper's answer depends only on the file, the level
# analysis on the sliders — so only the cheap half runs again
_heard: dict[tuple, list[tuple[str, float, float]]] = {}


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


def is_filler(word: str) -> bool:
    return word.strip(_FILLER_STRIP).lower() in FILLERS


def find_fillers(path: Path, *, lang: str | None = None, threshold_db: float = THRESHOLD_DB,
                 words: list[tuple[str, float, float]] | None = None) -> tuple[list[tuple[float, float, str]], int]:
    """(start, end, word) of every filler that can be cut cleanly, and how many were heard but left in."""
    from .. import align
    if words is None:
        if not align.available():
            raise VideoToolError("剪「嗯」「呃」要先装 faster-whisper（pip install faster-whisper），用来听出哪些声音是语气词")
        lang = (lang or "")[:2] or None
        st = Path(path).stat()
        key = (str(Path(path).resolve()), st.st_mtime_ns, st.st_size, lang)
        if key not in _heard:
            _heard[key] = align.transcribe(path, lang, prompt=_PROMPT.get(lang or ""))
        words = _heard[key]
    total = ffmpeg.duration(path)
    # voiced stretches at a short gap: a filler is usually a little island between two pauses
    islands = keep_ranges(total, silences(path, threshold_db=threshold_db, min_gap=0.12), pad=0)
    spoken = [(a + b) / 2 for w, a, b in words if not is_filler(w)]
    cuts: list[tuple[float, float, str]] = []
    unsure = 0
    for w, a, b in words:
        if not is_filler(w):
            continue
        overlap = [(min(b, y) - max(a, x), (x, y)) for x, y in islands]
        best = max(overlap, default=(0.0, None))
        isl = best[1]
        if best[0] <= 0 or isl is None or isl[1] - isl[0] > 1.2 or any(isl[0] < m < isl[1] for m in spoken):
            unsure += 1
            continue
        cuts.append((round(max(0.0, isl[0] - 0.02), 3), round(min(total, isl[1] + 0.02), 3), w.strip(_FILLER_STRIP)))
    return cuts, unsure


def _subtract(keep: list[tuple[float, float]], cuts: list[tuple[float, float, str]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in keep:
        pieces = [(a, b)]
        for c, d, _ in cuts:
            nxt = []
            for x, y in pieces:
                if d <= x or c >= y:
                    nxt.append((x, y))
                    continue
                if c > x:
                    nxt.append((x, c))
                if d < y:
                    nxt.append((d, y))
            pieces = nxt
        out += [(round(x, 3), round(y, 3)) for x, y in pieces if y - x > 0.08]
    return out


def plan(path: Path, *, threshold_db: float = THRESHOLD_DB, min_gap: float = MIN_GAP, pad: float = PAD,
         fillers: bool = False, lang: str | None = None) -> dict:
    """What a cut would do, without doing it: for the UI's before/after bar."""
    total = ffmpeg.duration(path)
    keep = keep_ranges(total, silences(path, threshold_db=threshold_db, min_gap=min_gap), pad=pad)
    extra: dict = {}
    if fillers:
        cuts, unsure = find_fillers(path, lang=lang, threshold_db=threshold_db)
        keep = _subtract(keep, cuts)
        extra = {"fillers": [{"word": w, "start": a, "end": b} for a, b, w in cuts], "fillers_unsure": unsure}
    kept = sum(b - a for a, b in keep)
    return {"total": round(total, 3), "kept": round(kept, 3), "removed": round(total - kept, 3),
            "cuts": max(0, len(keep) - 1) + (1 if keep and keep[0][0] > 0.01 else 0)
                    + (1 if keep and keep[-1][1] < total - 0.01 else 0),
            "keep": [[round(a, 3), round(b, 3)] for a, b in keep], **extra}


def cut(src: Path, out: Path, *, threshold_db: float = THRESHOLD_DB, min_gap: float = MIN_GAP,
        pad: float = PAD, fps: int = 30, fillers: bool = False, lang: str | None = None, log=print) -> dict:
    """Write `out` with the gaps (and, with `fillers`, the 嗯/呃) removed. Returns the plan that was applied."""
    src, out = Path(src), Path(out)
    p = plan(src, threshold_db=threshold_db, min_gap=min_gap, pad=pad, fillers=fillers, lang=lang)
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
    note = ""
    if fillers:
        note = f"，其中语气词 {len(p['fillers'])} 个" + (f"（另有 {p['fillers_unsure']} 个贴着别的字，没剪）" if p["fillers_unsure"] else "")
    log(f"剪口播：{p['total']:.1f}s → {p['kept']:.1f}s，剪掉 {p['removed']:.1f}s（{p['cuts']} 处）{note}")
    return {**p, "out": str(out)}
