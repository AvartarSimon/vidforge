"""B 站排行榜 — 100 条，干净 JSON。实测 2026-10-05。

为什么留着它：抖音/TikTok/快手 拿不到，而 B 站是中文里**长视频**的那个平台，
形态和这个频道最接近——那里排得上的选题，在 YouTube 上通常也成立。
"""

from __future__ import annotations

from . import Topic, TrendsError
from ._http import get_json

URL = "https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all"


def fetch(queries: list[str] | None = None) -> list[Topic]:
    j = get_json(URL, headers={"Referer": "https://www.bilibili.com/"})
    # B 站 answers risk control with code -352 and an empty data block. Without this check the
    # caller just sees zero items and cannot tell "nothing today" from "you were throttled".
    if j.get("code") not in (0, None):
        raise TrendsError(f"B 站返回 code={j.get('code')}（{j.get('message') or '被风控了'}），稍后再试")
    rows = (j.get("data") or {}).get("list") or []
    out: list[Topic] = []
    for row in rows:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        stat = row.get("stat") or {}
        out.append(Topic(title=title, source="bilibili", rank=len(out) + 1,
                         url=row.get("short_link_v2") or f"https://www.bilibili.com/video/{row.get('bvid', '')}",
                         heat=int(stat.get("view") or 0) or None,
                         extra={"owner": (row.get("owner") or {}).get("name", ""),
                                "duration": row.get("duration")}))
    return out
