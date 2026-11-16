"""一次成片，多平台导出：抖音 / 快手 / TikTok / 视频号 / 今日头条·西瓜 / YouTube / Shorts.

The long video is rendered once; each platform then gets a re-framed, re-encoded copy cut to its
shape plus a text file with the title, description, tags and the AI-content line it needs — the
part people forget at 11 pm when uploading to five apps.

Reframing reuses `video/vertical.py` (blur keeps the whole frame; crop fills it), so a 16:9 project
becomes a 9:16 one without another render and a 9:16 project gets a 16:9 copy the same way.

The limits here are guidance, written down on 2026-11-16, and every platform changes them without
notice — so an over-long export is a warning, never a refusal. What does not change is the shape:
抖音/快手/TikTok/视频号/Shorts are watched upright, 头条·西瓜's creator programme and YouTube's
main feed are landscape.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import ffmpeg


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    ratio: str                    # 9:16 | 16:9
    width: int
    height: int
    best: tuple[int, int]         # the length that tends to do well, seconds
    max_seconds: int | None       # longest upload the platform takes (None = effectively unlimited)
    video_kbps: int
    title_max: int
    tips: str


PLATFORMS: tuple[Platform, ...] = (
    Platform("douyin", "抖音", "9:16", 1080, 1920, (30, 180), 15 * 60, 10000, 55,
             "标题 + 3–5 个 #话题；前 3 秒要有钩子。发布时在「高级设置 → 作者声明」里勾选内容由 AI 生成（如果用了 AI 配音/画面）。"),
    Platform("kuaishou", "快手", "9:16", 1080, 1920, (30, 180), 15 * 60, 10000, 50,
             "快手偏生活化、口语化的标题；作品描述里带 #话题。用了 AI 生成内容要在发布页打 AI 标识。"),
    Platform("shipinhao", "视频号", "9:16", 1080, 1920, (30, 180), 60 * 60, 10000, 30,
             "标题短（16 字以内最好），可以挂公众号文章；AI 生成内容在发布页声明。"),
    Platform("tiktok", "TikTok", "9:16", 1080, 1920, (21, 180), 60 * 60, 10000, 150,
             "Caption + 3–5 hashtags. Turn on “AI-generated content” in More options if narration or visuals are AI."),
    Platform("toutiao", "今日头条 / 西瓜", "16:9", 1920, 1080, (60, 900), None, 12000, 30,
             "中视频伙伴计划要求横屏、时长 ≥ 1 分钟、原创；标题 30 字以内；封面要清楚。AI 生成内容需在发布时声明。"),
    Platform("youtube", "YouTube", "16:9", 1920, 1080, (60, 1500), None, 16000, 100,
             "标题 ≤ 100 字符，简介前两行最重要；章节在简介里（vidforge 自动生成）。合成的写实人物/场景要勾选「改动或合成内容」。"),
    Platform("shorts", "YouTube Shorts", "9:16", 1080, 1920, (20, 60), 180, 10000, 100,
             "Shorts 最长 3 分钟；标题里带 #Shorts 不是必须的。竖版、开头一秒抓人。"),
)

_BY_ID = {p.id: p for p in PLATFORMS}


class PlatformError(RuntimeError):
    pass


def get(pid: str) -> Platform:
    if pid not in _BY_ID:
        raise PlatformError(f"未知平台 '{pid}'（可选：{', '.join(_BY_ID)}）")
    return _BY_ID[pid]


def listing() -> list[dict]:
    return [{**asdict(p), "best": list(p.best)} for p in PLATFORMS]


def check(p: Platform, seconds: float) -> list[str]:
    """Warnings for a video of `seconds` on platform `p` — advice, never a refusal."""
    out = []
    if p.max_seconds and seconds > p.max_seconds:
        out.append(f"{p.name} 目前最长 {p.max_seconds // 60} 分钟，这条 {seconds / 60:.1f} 分钟——要先剪短（或做成切片）")
    elif seconds < p.best[0] or seconds > p.best[1] * 2:
        out.append(f"{p.name} 上常见的长度是 {p.best[0]}–{p.best[1]} 秒，这条 {seconds:.0f} 秒")
    if p.id == "toutiao" and seconds < 60:
        out.append("头条/西瓜中视频计划要求 ≥ 1 分钟")
    return out


def post_text(project, p: Platform) -> str:
    """What to paste into the upload form: title, description, tags, the AI-content line."""
    yt = project.youtube
    title = (yt.title or project.title or "").strip()
    lang = project.language or "zh"
    lines = [f"【{p.name}】", "", "标题：", title[: p.title_max]]
    if len(title) > p.title_max:
        lines.append(f"（原标题 {len(title)} 字，超过 {p.name} 的 {p.title_max} 字，已截断——最好重写一个短的）")
    desc = (yt.description or "").strip()
    if desc:
        lines += ["", "简介：", desc]
    if yt.tags:
        hashtags = " ".join("#" + t.strip().lstrip("#").replace(" ", "") for t in yt.tags[:5] if t.strip())
        lines += ["", "话题：", hashtags]
    ai = yt.disclosure.lines(lang)
    if ai:
        lines += ["", "AI 内容声明（贴在简介末尾，并在发布页勾选平台的 AI 标识）：", *ai]
    lines += ["", "提示：", p.tips]
    return "\n".join(lines) + "\n"


def export(project, source: Path, out_dir: Path, pid: str, *, mode: str = "blur", srt: Path | None = None,
           log=print) -> dict:
    """One platform's copy of `source` in `out_dir`, plus its upload text."""
    from .video import vertical
    p = get(pid)
    source, out_dir = Path(source), Path(out_dir)
    if not source.is_file():
        raise PlatformError(f"找不到成片 {source}——先在第 4 步渲染")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{pid}.mp4"
    sw, sh = ffmpeg.video_size(source)
    total = ffmpeg.duration(source)
    same_shape = abs(sw / sh - p.width / p.height) < 0.02
    rate = ["-maxrate", f"{p.video_kbps}k", "-bufsize", f"{p.video_kbps * 2}k"]
    if same_shape:
        ffmpeg.run(["-y", "-i", str(source), "-vf", f"scale={p.width}:{p.height}:flags=lanczos,setsar=1",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", *rate, "-pix_fmt", "yuv420p",
                    "-r", str(project.fps or 30), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    elif p.ratio == "9:16" and sw > sh:
        # landscape -> upright: the vertical cutter already knows how (and re-burns big captions)
        vertical.make(source, out, vertical.Cut(0.0, total), mode=mode, ratio="9:16", srt=srt,
                      font=project.subtitles.font, subtitles=srt is not None, log=log)
    else:
        chain = vertical.reframe_filter(mode, p.width, p.height)
        ffmpeg.run(["-y", "-i", str(source), "-filter_complex", f"[0:v]{chain}[v]", "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", *rate, "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    seconds = ffmpeg.duration(out)
    text = out_dir / f"{pid}.txt"
    text.write_text(post_text(project, p), encoding="utf-8")
    warnings = check(p, seconds)
    for w in warnings:
        log(f"  ⚠ {w}")
    mb = out.stat().st_size / 1e6
    log(f"  {p.name}: {p.width}x{p.height} · {seconds:.1f}s · {mb:.1f} MB -> {out.name}")
    result = {"id": pid, "name": p.name, "path": str(out), "text": str(text), "seconds": seconds,
              "mb": round(mb, 1), "warnings": warnings}
    (out_dir / f"{pid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
