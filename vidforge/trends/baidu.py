"""百度热搜 — 52 条。页面里嵌着 JSON，取 "query" 字段。实测 2026-10-05。"""

from __future__ import annotations

import html
import re
from urllib.parse import quote

from . import Topic
from ._http import get

URL = "https://top.baidu.com/board?tab=realtime"
_QUERY = re.compile(r'"query":"(.*?)"')
_HEAT = re.compile(r'"hotScore":"?(\d+)"?')


def fetch(queries: list[str] | None = None) -> list[Topic]:
    page = get(URL)
    heats = _HEAT.findall(page)
    out: list[Topic] = []
    seen: set[str] = set()
    for i, raw in enumerate(_QUERY.findall(page)):
        # the embedded JSON comes through as readable UTF-8, not escape sequences (checked against
        # the live page), so unescaping HTML entities is the whole job
        title = html.unescape(raw).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(Topic(title=title, source="baidu", rank=len(out) + 1,
                         url=f"https://www.baidu.com/s?wd={quote(title)}",
                         heat=int(heats[i]) if i < len(heats) else None))
    return out
