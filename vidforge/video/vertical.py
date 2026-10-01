"""Cut a vertical clip out of a finished video — the 竖版 that feeds 小红书 / 抖音 / Shorts.

One topic should not be researched twice. The long video is already made, its subtitles already
carry word-accurate timings, and `timeline.json` already says where each segment starts; a short
is therefore a trim plus a reframe, not another render.

    vidforge short my-video --segments seg3,seg4            # by chapter
    vidforge short my-video --at 90 --seconds 55            # by the clock

Reframing 16:9 into 9:16 destroys something either way, so the choice is explicit:

    blur  the whole frame is kept, centred, over a blurred enlargement of itself.
          Charts, maps and text survive. This is the default, because this channel's
          pictures usually *are* the information.
    crop  centre-crop to fill. Nothing is letterboxed and faces look right, but the sides are
          gone — fine for a photograph, wrong for a chart with an axis on the left.

Subtitles are rebuilt larger and higher (a phone thumb sits over the bottom sixth of the screen),
re-timed to the cut, and burned in: a short is watched without sound more often than with it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .. import ffmpeg
from . import VideoToolError

SIZE = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


@dataclass
class Cut:
    start: float
    end: float

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


def _parse_time(value: str | float) -> float:
    """Seconds from 90, "90", "1:30" or "00:01:30.5"."""
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise VideoToolError(f"看不懂的时间：{value!r}（用 90 或 1:30 或 00:01:30）") from None
    out = 0.0
    for n in nums:
        out = out * 60 + n
    return out


def range_from_segments(timeline: list[dict], ids: list[str]) -> Cut:
    """The span covering the named segments, in timeline order."""
    wanted = [t for t in timeline if t.get("id") in set(ids)]
    if not wanted:
        have = ", ".join(t.get("id", "?") for t in timeline if not str(t.get("id", "")).startswith("__"))
        raise VideoToolError(f"时间轴里没有这些段落：{', '.join(ids)}（有：{have}）")
    return Cut(min(t["start"] for t in wanted), max(t["end"] for t in wanted))


def read_timeline(build_dir: Path) -> list[dict]:
    f = Path(build_dir) / "timeline.json"
    if not f.is_file():
        raise VideoToolError(f"没有 {f}——先完整渲染一次长视频")
    return json.loads(f.read_text(encoding="utf-8"))


_SRT = re.compile(r"(\d+)\s*\n(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)", re.S)


def _srt_seconds(stamp: str) -> float:
    h, m, rest = stamp.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def subtitles_for(srt: Path, cut: Cut) -> list[tuple[float, float, str]]:
    """Cues overlapping the cut, re-timed so the clip starts at zero."""
    if not Path(srt).is_file():
        return []
    out = []
    for _, a, b, text in _SRT.findall(Path(srt).read_text(encoding="utf-8")):
        start, end = _srt_seconds(a), _srt_seconds(b)
        if end <= cut.start or start >= cut.end:
            continue
        out.append((max(0.0, start - cut.start), min(cut.seconds, end - cut.start),
                    " ".join(text.strip().splitlines())))
    return out


def _ass(cues, path: Path, width: int, height: int, font: str, colour: str = "#FFFFFF") -> Path:
    """Big, centred, lifted off the bottom — a thumb covers the bottom sixth of a phone."""
    from ..subtitles import _ass_time, _bgr
    size = round(height * 0.034)
    head = [
        # WrapStyle 0 wraps long lines; 2 (what the landscape burner uses, where lines are already
        # short) would let a sentence run off both edges of a 1080-wide phone frame.
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 0", "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}", f"PlayResY: {height}", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Main,{font},{size},{_bgr(colour)},&H00FFFFFF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,"
        f"3,{max(2, size // 12)},0,2,{round(width * 0.07)},{round(width * 0.07)},{round(height * 0.17)},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    body = [f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Main,,0,0,0,,{t.replace('{', '(').replace('}', ')')}"
            for a, b, t in cues]
    Path(path).write_text("\n".join(head + body) + "\n", encoding="utf-8")
    return path


def reframe_filter(mode: str, w: int, h: int) -> str:
    """The video filter that turns a landscape frame into a `w`x`h` one."""
    if mode == "crop":
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h},setsar=1")
    if mode == "blur":
        return (f"split=2[bg][fg];"
                f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},"
                f"boxblur=luma_radius={max(10, w // 24)}:luma_power=2,eq=brightness=-0.12[bgb];"
                f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
                f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1")
    raise VideoToolError(f"未知的画面模式 '{mode}'（可选：blur | crop）")


def pick_source(build_dir: Path, project_burns_subtitles: bool) -> Path:
    """Which rendered file to cut from.

    `final.mp4` is the deliverable, but when the project burns its own subtitles that file already
    has small, bottom-aligned captions baked in — burning the big vertical ones on top gives two
    sets of text. `merged.mp4` is the same picture without them, so it is the better source in
    that case; it lacks the background music, which a short rarely needs anyway."""
    build_dir = Path(build_dir)
    merged, final = build_dir / "merged.mp4", build_dir / "final.mp4"
    if project_burns_subtitles and merged.is_file():
        return merged
    if final.is_file():
        return final
    if merged.is_file():
        return merged
    raise VideoToolError(f"{build_dir} 里没有渲染好的视频——先完整渲染一次长视频")


def make(source: Path, out: Path, cut: Cut, *, mode: str = "blur", ratio: str = "9:16",
         srt: Path | None = None, font: str = "Arial", subtitles: bool = True,
         log=print) -> dict:
    """Trim `source` to `cut`, reframe it, burn the re-timed subtitles, write `out`."""
    source, out = Path(source), Path(out)
    if not source.is_file():
        raise VideoToolError(f"找不到视频：{source}")
    if cut.seconds <= 0:
        raise VideoToolError("这一段长度是 0——检查一下起止点")
    if ratio not in SIZE:
        raise VideoToolError(f"未知的比例 '{ratio}'（可选：{', '.join(SIZE)}）")
    w, h = SIZE[ratio]
    out.parent.mkdir(parents=True, exist_ok=True)

    chain = reframe_filter(mode, w, h)
    cues = subtitles_for(srt, cut) if (subtitles and srt) else []
    if cues:
        ass = out.with_suffix(".ass")
        _ass(cues, ass, w, h, font)
        chain += f",subtitles='{ffmpeg.filter_path(ass)}'"
    # -ss before -i seeks fast; -t after it keeps the length exact
    ffmpeg.run(["-y", "-ss", f"{cut.start:.3f}", "-i", str(source), "-t", f"{cut.seconds:.3f}",
                "-filter_complex", f"[0:v]{chain}[v]", "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    made = ffmpeg.duration(out)
    log(f"  竖版 {ratio} {mode} · {made:.1f}s · {len(cues)} 条字幕 -> {out.name}")
    return {"path": str(out), "seconds": made, "cues": len(cues), "ratio": ratio, "mode": mode}


def suggest(timeline: list[dict], seconds: float = 55.0) -> list[dict]:
    """Candidate cuts: each real segment, and each neighbouring pair that still fits.

    A short wants one complete idea, and a segment *is* one idea here — that is what the script
    was split on — so the segments are the natural candidates rather than a fixed window."""
    segs = [t for t in timeline if not str(t.get("id", "")).startswith("__")]
    out = []
    for i, t in enumerate(segs):
        span = t["end"] - t["start"]
        if 8 <= span <= seconds:
            out.append({"ids": [t["id"]], "label": t.get("label") or t["id"],
                        "start": t["start"], "seconds": round(span, 2)})
        if i + 1 < len(segs):
            pair = segs[i + 1]["end"] - t["start"]
            if span < seconds and pair <= seconds:
                out.append({"ids": [t["id"], segs[i + 1]["id"]],
                            "label": f"{t.get('label') or t['id']} + {segs[i + 1].get('label') or segs[i + 1]['id']}",
                            "start": t["start"], "seconds": round(pair, 2)})
    return out
