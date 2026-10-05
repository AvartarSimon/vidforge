"""YouTube 热门。

有 `YOUTUBE_API_KEY` 时走官方 `videos?chart=mostPopular`（免费额度够用）。
没有 key 时**这一源为空**，不是退回解析页面：实测
`youtube.com/feed/trending` 现在返回 0 个视频（要 JS/consent），
硬解析只会得到「Try searching to get started」之类的界面文字，比没有更糟。

没有 key 也不是没有 YouTube 数据——`research/` 那边按关键词搜 + 播放量统计是不要 key 的，
只是那是「验证一个选题」，不是「发现今天什么在火」。
"""

from __future__ import annotations

import os

from . import Topic
from ._http import get_json

API = ("https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics"
       "&chart=mostPopular&maxResults=25&regionCode={region}&key={key}")
# AU because that is where the owner is; CN has no YouTube, and US drowns in US-only news
REGION = os.environ.get("VIDFORGE_YT_REGION", "AU")


def fetch(queries: list[str] | None = None) -> list[Topic]:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        return []
    j = get_json(API.format(region=REGION, key=key))
    out: list[Topic] = []
    for row in j.get("items") or []:
        sn, st = row.get("snippet") or {}, row.get("statistics") or {}
        title = (sn.get("title") or "").strip()
        if not title:
            continue
        out.append(Topic(title=title, source="youtube", rank=len(out) + 1,
                         url=f"https://www.youtube.com/watch?v={row.get('id', '')}",
                         heat=int(st.get("viewCount") or 0) or None,
                         when=sn.get("publishedAt", ""),
                         extra={"channel": sn.get("channelTitle", ""),
                                "category": sn.get("categoryId", "")}))
    return out
