"""一次成片，多平台导出：抖音 / 快手 / TikTok / 视频号 / 小红书 / 今日头条·西瓜 / B站 / YouTube / Shorts.

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
    ratio: str                    # 9:16 | 3:4 | 16:9
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
    Platform("xiaohongshu", "小红书", "3:4", 1080, 1440, (30, 300), 15 * 60, 10000, 20,
             "标题 20 字以内，正文写清楚要点、带 #话题；3:4 竖图最占屏。AI 生成内容在发布页声明。"),
    Platform("toutiao", "今日头条 / 西瓜", "16:9", 1920, 1080, (60, 900), None, 12000, 30,
             "中视频伙伴计划要求横屏、时长 ≥ 1 分钟、原创；标题 30 字以内；封面要清楚。AI 生成内容需在发布时声明。"),
    Platform("bilibili", "B站", "16:9", 1920, 1080, (120, 1200), None, 12000, 80,
             "标题 80 字以内，简介写清楚出处；分区选对（知识区）；横屏为主。用了 AI 生成内容在投稿页声明。"),
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


def check(p: Platform, seconds: float, size: tuple[int, int] | None = None) -> list[str]:
    """Warnings for a video of `seconds` (and frame `size`) on platform `p` — advice, never a refusal."""
    out = []
    if size and size[0] < size[1] and p.ratio == "16:9":
        # the copy is still made (blurred sides), but an upright picture in a landscape feed is
        # a third of the screen — and 头条's 中视频 programme does not count such videos at all
        out.append(f"成片是竖屏，{p.name} 是横屏平台：导出的横版两侧是虚化填充，画面只占中间三分之一——"
                   "要认真做这个平台，把项目画幅改成 1920×1080 另渲染一条")
    if p.max_seconds and seconds > p.max_seconds:
        out.append(f"{p.name} 目前最长 {p.max_seconds // 60} 分钟，这条 {seconds / 60:.1f} 分钟——要先剪短（或做成切片）")
    elif seconds < p.best[0] or seconds > p.best[1] * 2:
        out.append(f"{p.name} 上常见的长度是 {p.best[0]}–{p.best[1]} 秒，这条 {seconds:.0f} 秒")
    if p.id == "toutiao" and seconds < 60:
        out.append("头条/西瓜中视频计划要求 ≥ 1 分钟")
    return out


def post_text(project, p: Platform, credits: str = "") -> str:
    """What to paste into the upload form: title, description, tags, the AI-content line, and the
    credits the pictures' licences ask for (`credits` = the build's credits.txt)."""
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
    if credits.strip():
        # CC BY / CC BY-SA pictures may only be used with their author named, on every platform the
        # video goes to — not only in the YouTube description, which was the one place that had them
        lines += ["", "素材署名（授权要求署名，贴在简介末尾；放不下就贴在置顶评论）：", credits.strip()]
    lines += ["", "提示：", p.tips]
    return "\n".join(lines) + "\n"


# 抖音 / 快手 / 视频号 show a creator's videos as a grid of 3:4 tiles; the 9:16 cover is the one the
# feed shows. Landscape apps take a 16:9 picture (YouTube's custom thumbnail is 1280x720).
GRID = ("douyin", "kuaishou", "shipinhao")
# 小红书's tile and player are 3:4 already; its cover is the one picture


def make_covers(project, p: Platform, source: Path, video: Path, out_dir: Path) -> list[Path]:
    """The cover pictures this platform asks for, drawn from the build's cover picture (or a
    frame of the export when there is none) with the cover text on top."""
    from . import thumbnail
    src = source.parent / "cover_src.jpg"
    if not src.is_file():
        src = out_dir / f"{p.id}_frame.jpg"
        ffmpeg.run(["-y", "-ss", "1", "-i", str(video), "-frames:v", "1", str(src)])
    text = (project.thumbnail_text or project.youtube.title or project.title or "").strip()
    if p.ratio == "9:16":
        sizes = [(1080, 1920)] + ([(1080, 1440)] if p.id in GRID else [])
    elif p.height > p.width:
        sizes = [(p.width, p.height)]
    else:
        sizes = [(1280, 720)]
    out = []
    for w, h in sizes:
        f = out_dir / f"{p.id}_cover_{w}x{h}.jpg"
        thumbnail.make(src, text, f, size=(w, h))
        out.append(f)
    return out


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
    elif p.height > p.width and sw > sh:
        # landscape -> upright: the vertical cutter already knows how (and re-burns big captions)
        vertical.make(source, out, vertical.Cut(0.0, total), mode=mode, ratio=p.ratio, srt=srt,
                      font=project.subtitles.font, subtitles=srt is not None, log=log)
    else:
        chain = vertical.reframe_filter(mode, p.width, p.height)
        ffmpeg.run(["-y", "-i", str(source), "-filter_complex", f"[0:v]{chain}[v]", "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", *rate, "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    seconds = ffmpeg.duration(out)
    covers = make_covers(project, p, source, out, out_dir)
    text = out_dir / f"{pid}.txt"
    credits = source.parent / "credits.txt"      # written by the build, beside the finished video
    text.write_text(post_text(project, p, credits.read_text(encoding="utf-8") if credits.is_file() else ""),
                    encoding="utf-8")
    warnings = check(p, seconds, (sw, sh))
    for w in warnings:
        log(f"  ⚠ {w}")
    mb = out.stat().st_size / 1e6
    log(f"  {p.name}: {p.width}x{p.height} · {seconds:.1f}s · {mb:.1f} MB -> {out.name}")
    result = {"id": pid, "name": p.name, "path": str(out), "text": str(text), "seconds": seconds,
              "mb": round(mb, 1), "warnings": warnings, "covers": [str(c) for c in covers]}
    (out_dir / f"{pid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


# -- 标题 / 简介 / 话题, written by the local model ---------------------------------------------------
# The upload form is where a finished video stalls: five apps, each wanting a title that fits its
# length, a description and hashtags. A small local model drafts them from the script; the user
# picks. Nothing it writes is used unseen, and a title that carries a number the script does not
# is dropped — a headline is exactly where an invented figure would do the most harm.
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_CN_BIG = {"万": 10_000, "亿": 100_000_000}


def cn_number(s: str) -> int | None:
    """「六十一」→ 61, 「一九九零」→ 1990, 「八十五万」→ 850000; None when it is not a plain number."""
    if not s:
        return None
    if all(ch in _CN_DIGITS for ch in s):                    # digit by digit, as years are said
        return int("".join(str(_CN_DIGITS[ch]) for ch in s)) if len(s) > 1 else _CN_DIGITS[s]
    total, section, digit = 0, 0, None
    for ch in s:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            section += (1 if digit is None else digit) * _CN_UNITS[ch]
            digit = None
        elif ch in _CN_BIG:
            total += (section + (digit or 0)) * _CN_BIG[ch]
            section, digit = 0, None
        else:
            return None
    return total + section + (digit or 0)


def script_numbers(text: str) -> set[str]:
    """Every number the script states, as digits: the only ones a title may use."""
    import re
    out = {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
    for run in re.findall(r"[零〇一二两三四五六七八九十百千万亿]+", text):
        n = cn_number(run)
        if n is not None and (n >= 10 or len(run) == 1):
            out.add(str(n))
            if n >= 10_000:                                   # 八十五万 may be written 85万
                for unit, k in (("万", 10_000), ("亿", 100_000_000)):
                    if n % k == 0:
                        out.add(str(n // k))
    return out


def _clean_line(v: object, limit: int) -> str:
    import re
    s = re.sub(r"[\U0001F000-\U0001FFFF☀-➿#《》\"“”]", "", str(v or "")).strip(" 。.,，:：")
    return s[:limit]


def suggest_text(project, *, n: int = 5) -> dict:
    """Draft titles, a description and topic tags from the narration. Raises llm.LlmError when no
    local model is running."""
    import re
    from . import llm
    script = "\n".join(s.text for s in project.segments).strip()
    if not script:
        raise PlatformError("还没有脚本——先在第 1 步写好旁白，标题要从旁白里来")
    zh = (project.language or "zh").startswith("zh")
    if zh:
        prompt = (f"下面是一条短视频的旁白稿：\n\n{script[:2500]}\n\n"
                  f"为它写 {n} 个标题：每个 12 到 28 个字，口语，有悬念或反差，让人想点开；"
                  "只能用稿子里出现过的数字，不要编数字；不要书名号、引号和表情符号。"
                  "再写一段 60 到 120 字的简介，第一句说清这条视频回答什么问题。"
                  "再给 5 个话题词，每个 2 到 6 个字，不带 # 号。"
                  '只返回 JSON：{"titles": [...], "description": "...", "tags": [...]}')
        system = "你是中文短视频平台的运营编辑，只用中文回答。"
    else:
        prompt = (f"Narration of a short explainer video:\n\n{script[:2500]}\n\n"
                  f"Write {n} titles (40-80 characters each, curiosity or contrast, plain words; use only "
                  "numbers that appear in the narration, never invent one; no emoji, no quotes), a 2-3 "
                  "sentence description whose first sentence says what question the video answers, and "
                  "5 topic tags (one or two words, no #). "
                  'Return JSON only: {"titles": [...], "description": "...", "tags": [...]}')
        system = "You are a video editor writing upload text for YouTube and TikTok."
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True, timeout=180))
    except json.JSONDecodeError:
        raise llm.LlmError("本地模型没有返回能读的结果，再点一次试试") from None
    if not isinstance(data, dict):
        data = {}
    allowed = script_numbers(script)
    titles, dropped = [], []
    for t in data.get("titles") or []:
        t = _clean_line(t, 100)
        if not t or t in titles:
            continue
        nums = {m.replace(",", "") for m in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}
        nums |= {str(cn_number(r)) for r in re.findall(r"[零〇一二两三四五六七八九十百千万亿]{2,}", t) if cn_number(r) is not None}
        if nums - allowed:
            dropped.append(t)
            continue
        titles.append(t)
    tags = []
    for t in data.get("tags") or []:
        t = _clean_line(t, 200).replace(" ", "" if zh else " ")
        # too long to be a hashtag: left out rather than cut mid-word
        if t and t not in tags and len(t) <= (8 if zh else 30):
            tags.append(t)
    desc = str(data.get("description") or "").strip()
    return {"titles": titles, "description": desc, "tags": tags[:8], "dropped": dropped,
            "lengths": {p.id: p.title_max for p in PLATFORMS}}
