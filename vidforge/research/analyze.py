"""Turn the competitor table into a decision: worth it? which angle? which title/hook?

The prompt goes through the browser-chat bridge (or the clipboard). The answer is JSON; we
extract the first {...} block and fall back to the raw text if it does not parse.
"""

from __future__ import annotations

import json
import re

from .youtube import Video, summarize

SCHEMA = {
    "verdict": "do | do_with_angle | skip",
    "saturation": "low | medium | high",
    "why": "2-3 sentences",
    "angles": [{"title": "differentiated angle", "why": "what it adds that the top videos lack"}],
    "titles": ["5 title options, <= 60 chars, YouTube style"],
    "hooks": ["3 opening lines for the first 15 seconds"],
    "strengths_of_top": ["what the best-performing videos do well (structure, title formula, thumbnail idea)"],
    "gaps": ["what none of them cover"],
    "thumbnail_text": ["3 options, <= 4 words each"],
    "risks": ["policy / accuracy / saturation risks"],
}


def build_prompt(topic: str, videos: list[Video], positioning: str = "", lang: str = "zh") -> str:
    s = summarize(videos)
    rows = "\n".join(
        f"- {v.views:,} views · {v.age_days or '?'} days old · {round((v.duration_s or 0) / 60)} min · {v.channel} · {v.title}"
        for v in sorted(videos, key=lambda v: -v.views)[:20]
    )
    zh = lang.startswith("zh")
    intro = (f"我在做一个讲解类视频频道{('（定位：' + positioning + '）') if positioning else ''}，正在评估选题「{topic}」。"
             if zh else f"I run an explainer video channel{(' (positioning: ' + positioning + ')') if positioning else ''} and am evaluating the topic \"{topic}\".")
    task = ("请根据下面 YouTube 上同类视频的数据判断：这个选题值不值得做、怎么做才有差异化。"
            if zh else "Judge from the YouTube data below whether this topic is worth making and how to differentiate.")
    stats = (f"统计：{s.get('count')} 条结果，中位播放 {s.get('median_views'):,}，最高 {s.get('max_views'):,}，近 12 个月新发 {s.get('recent_12m')} 条"
             f"（中位播放 {s.get('recent_median_views'):,}），≥8 分钟长视频占 {int(s.get('long_form_share', 0) * 100)}%，中位时长 {s.get('median_duration_min')} 分钟，{s.get('channels')} 个频道。"
             if zh else f"Stats: {s.get('count')} results, median views {s.get('median_views'):,}, max {s.get('max_views'):,}, {s.get('recent_12m')} published in the last 12 months"
             f" (median {s.get('recent_median_views'):,}), {int(s.get('long_form_share', 0) * 100)}% long-form (>= 8 min), median length {s.get('median_duration_min')} min, {s.get('channels')} channels.")
    fmt = ("只输出一个 JSON 对象（不要 markdown 代码块以外的文字），字段如下，值用" + ("中文" if zh else "英文") + "：\n"
           if zh else "Output exactly one JSON object (no text outside a code block), with these fields, values in English:\n")
    return f"{intro}\n{task}\n\n{stats}\n\n同类视频（按播放排序）：\n{rows}\n\n{fmt}{json.dumps(SCHEMA, ensure_ascii=False, indent=1)}"


def parse_answer(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"verdict": "unknown", "why": text.strip()[:2000], "raw": True}
