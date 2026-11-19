"""要点: a segment's script as the few points to make, for speaking in your own words.

Reading a script out sounds read. Speaking from points sounds like talking — which is the point
of recording yourself at all. So in free mode the teleprompter shows these instead of the text:
short, a glance each, the numbers kept exact (a figure is the one thing not to improvise).

The local model condenses when it is running; otherwise the script's own sentences are the
points. Either way nothing is added: a point carrying a number the script does not state is
dropped, the same rule as the drafted titles.
"""

from __future__ import annotations

import json
import re

MAX_POINTS = 6
MAX_CHARS = 24       # a glance, not a sentence to read


def sentences(text: str) -> list[str]:
    """The script's own sentences, as the points when there is no model to condense them."""
    parts = [p.strip(" ，,、") for p in re.split(r"(?<=[。！？!?；;])\s*", text.strip())]
    return [p for p in parts if p][: MAX_POINTS * 2]


def _honest(point: str, script: str) -> bool:
    from .platforms import script_numbers
    return script_numbers(point) <= script_numbers(script)


def _with_figures(kept: list[str], text: str) -> list[str]:
    """Every figure of the script in some point. A small model drops them first, and a number is
    the one thing speaking from memory gets wrong: a sentence carrying a missing one is added
    after the points, shortened to a glance."""
    from .platforms import script_numbers
    have = set().union(*(script_numbers(p) for p in kept)) if kept else set()
    out = list(kept)
    for sent in sentences(text):
        # 一 / 三 alone are words more often than figures (一种, 三个); a real figure has two digits.
        # One figure has several forms (六百八十万 is 6800000 and 680): any of them is enough.
        figures = {n for n in script_numbers(sent) if len(n) > 1}
        if figures and not figures & have:
            out.append(sent[:MAX_CHARS].rstrip("，,、。") + ("…" if len(sent) > MAX_CHARS else ""))
            have |= script_numbers(sent)
    return out[: MAX_POINTS + 2]


def condense(text: str, *, log=None) -> tuple[list[str], str]:
    """-> (points, how): how is "llm" when the local model wrote them, else "sentences"."""
    text = (text or "").strip()
    if not text:
        return [], "sentences"
    from . import llm
    if llm.available():
        prompt = (f"把下面这段口播稿提炼成 4 到 {MAX_POINTS} 条要点，给录视频的人看一眼就能用自己的话讲出来。\n"
                  "按原文的顺序，从开头一直覆盖到最后一句（结尾那句最重要，不能漏）。\n"
                  f"每条 6 到 {MAX_CHARS // 2} 个字，只写关键词；原文里的数字、时间、天数都要写进去，一个字都不能改；"
                  "不要加原文没有的内容。\n"
                  "只输出 JSON：{\"points\": [\"…\", \"…\"]}\n\n" + text)
        try:
            out = json.loads(llm.chat(prompt, json_mode=True, timeout=60)).get("points") or []
            points = [str(p).strip() for p in out if str(p).strip()]
            kept = [p[:MAX_CHARS] for p in points if _honest(p, text)][:MAX_POINTS]
            if len(kept) < len(points) and log:
                log(f"  要点：去掉了 {len(points) - len(kept)} 条带原文没有的数字的")
            if kept:
                return _with_figures(kept, text), "llm"
        except (llm.LlmError, ValueError, AttributeError, TypeError):
            pass
    return sentences(text), "sentences"
