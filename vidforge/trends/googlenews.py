"""Google News RSS — 每个关键词 100 条，不要 key。实测 2026-10-05。

和热榜不同，这一源是**按关键词查**的：热榜告诉你大家在看什么，Google News 告诉你
你关心的那几个领域今天发生了什么。关键词默认来自项目分类的领域词。
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote

from . import Topic
from ._http import get

RSS = ("https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
DEFAULT_QUERIES = ["经济", "房地产", "人口", "金融", "科技", "能源", "政策"]
PER_QUERY = 12          # the top of each list; 100 per keyword x 7 keywords is nobody's reading list

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)


def _field(block: str, tag: str) -> str:
    """One RSS field, CDATA or not."""
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def fetch(queries: list[str] | None = None) -> list[Topic]:
    out: list[Topic] = []
    for q in (queries or DEFAULT_QUERIES):
        body = get(RSS.format(q=quote(q.strip())))
        kept = 0
        for block in _ITEM.findall(body)[:PER_QUERY]:
            title = _field(block, "title")
            if not title:
                continue
            kept += 1
            # Google News appends " - <媒体名>"; the outlet is useful, just not part of the title
            outlet = ""
            if " - " in title:
                title, outlet = title.rsplit(" - ", 1)
            out.append(Topic(title=title.strip(), source="googlenews", rank=kept,
                             url=_field(block, "link"), when=_field(block, "pubDate"),
                             extra={"query": q, "outlet": outlet}))
    return out
