"""Hacker News — official Firebase API, free, no key. 科技选题用。"""

from __future__ import annotations

from . import Topic
from ._http import get_json

TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
LIMIT = 25        # the front page, not the whole index


def fetch(queries: list[str] | None = None) -> list[Topic]:
    ids = get_json(TOP)
    out: list[Topic] = []
    for sid in (ids[:LIMIT] if isinstance(ids, list) else []):
        row = get_json(ITEM.format(sid))
        title = (row.get("title") or "").strip()
        if not title:
            continue
        out.append(Topic(title=title, source="hn", rank=len(out) + 1,
                         url=row.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                         heat=row.get("score")))
    return out
