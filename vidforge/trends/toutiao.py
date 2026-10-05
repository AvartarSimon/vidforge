"""今日头条热榜 — 50 条，官方 JSON，不要 key。实测 2026-10-05。"""

from __future__ import annotations

from . import Topic
from ._http import get_json

URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"


def fetch(queries: list[str] | None = None) -> list[Topic]:
    data = get_json(URL).get("data") or []
    out: list[Topic] = []
    for row in data:
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        heat = row.get("HotValue")
        # rank counts the items we kept, not the position in the raw payload: a blank entry is a
        # parse artifact, not a place on the list, and every source has to mean the same thing
        # here because the score decays with rank
        out.append(Topic(title=title, source="toutiao", rank=len(out) + 1,
                         url=row.get("Url") or "",
                         heat=int(heat) if str(heat).isdigit() else None))
    return out
