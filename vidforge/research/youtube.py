"""Similar videos on YouTube for a topic: title, channel, views, age, length.

Two paths, same output shape:
  * Data API v3 (`YOUTUBE_API_KEY`, free 10k units/day; a search costs 100 units) — exact
    statistics incl. likes/comments.
  * No key: the public results page embeds `ytInitialData`; we read titles, channels, view
    counts ("1.2M views"), age ("2 years ago") and length from it. Approximate, no likes.
Results cached 24 h under <project>/assets/.search-cache/.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class ResearchError(RuntimeError):
    pass


@dataclass
class Video:
    video_id: str
    title: str
    channel: str
    views: int
    published: str            # ISO date or "" when unknown
    age_days: int | None
    duration_s: int | None
    likes: int | None = None
    comments: int | None = None
    source: str = "api"       # api | page

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def views_per_day(self) -> float | None:
        return round(self.views / max(1, self.age_days), 1) if self.age_days else None


# -- helpers -------------------------------------------------------------------------------------
_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "万": 1e4, "亿": 1e8}


def parse_views(text: str) -> int:
    m = re.search(r"([\d.,]+)\s*([KMB万亿])?", text or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * _MULT.get(m.group(2) or "", 1))


def parse_age_days(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)", text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {"second": 0, "minute": 0, "hour": 0, "day": n, "week": n * 7, "month": n * 30, "year": n * 365}[unit]


def parse_duration(text: str) -> int | None:
    parts = [p for p in re.split(r"[:：]", (text or "").strip()) if p.isdigit()]
    if not parts:
        return None
    s = 0
    for p in parts:
        s = s * 60 + int(p)
    return s


def iso8601_duration(s: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se


def _get(url: str, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 Safari/537.36",
                                               "Accept-Language": "en-US,en;q=0.9", **(headers or {})})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


# -- Data API ------------------------------------------------------------------------------------
def search_api(query: str, key: str, n: int = 20, order: str = "relevance") -> list[Video]:
    q = urllib.parse.urlencode({"part": "snippet", "type": "video", "maxResults": min(n, 50), "q": query, "order": order, "key": key,
                                "relevanceLanguage": "en" if not re.search(r"[一-鿿]", query) else "zh"})
    data = json.loads(_get(f"https://www.googleapis.com/youtube/v3/search?{q}"))
    ids = [it["id"]["videoId"] for it in data.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []
    q2 = urllib.parse.urlencode({"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "key": key})
    det = json.loads(_get(f"https://www.googleapis.com/youtube/v3/videos?{q2}"))
    out = []
    now = datetime.now(timezone.utc)
    for it in det.get("items", []):
        sn, st, cd = it["snippet"], it.get("statistics", {}), it.get("contentDetails", {})
        pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        out.append(Video(video_id=it["id"], title=sn["title"], channel=sn["channelTitle"], views=int(st.get("viewCount", 0)),
                         published=pub.date().isoformat(), age_days=(now - pub).days, duration_s=iso8601_duration(cd.get("duration", "")),
                         likes=int(st["likeCount"]) if "likeCount" in st else None,
                         comments=int(st["commentCount"]) if "commentCount" in st else None, source="api"))
    return out


# -- public page ---------------------------------------------------------------------------------
def search_page(query: str, n: int = 20) -> list[Video]:
    html = _get("https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query, "hl": "en", "gl": "US"}),
                headers={"Cookie": "CONSENT=YES+1; SOCS=CAI"})
    m = re.search(r"var ytInitialData = ({.*?});</script>", html, re.S)
    if not m:
        raise ResearchError("YouTube 搜索页没有返回结果数据（可能是同意页/验证页）；请设置 YOUTUBE_API_KEY 走官方接口")
    data = json.loads(m.group(1))
    out: list[Video] = []

    def walk(node):
        if isinstance(node, dict):
            if "videoRenderer" in node:
                yield node["videoRenderer"]
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)

    def text(o) -> str:
        if not o:
            return ""
        if "simpleText" in o:
            return o["simpleText"]
        return "".join(r.get("text", "") for r in o.get("runs", []))

    for vr in walk(data):
        if len(out) >= n:
            break
        vid = vr.get("videoId")
        if not vid:
            continue
        out.append(Video(video_id=vid, title=text(vr.get("title")), channel=text(vr.get("ownerText")) or text(vr.get("longBylineText")),
                         views=parse_views(text(vr.get("viewCountText"))), published="",
                         age_days=parse_age_days(text(vr.get("publishedTimeText"))),
                         duration_s=parse_duration(text(vr.get("lengthText"))), source="page"))
    return out


def search(root: Path, query: str, n: int = 20) -> list[Video]:
    from ..assets import cached_search
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    how = "api" if key else "page"
    raw = cached_search(root, f"yt|{how}|{n}|{query}", lambda: [asdict(v) for v in (search_api(query, key, n) if key else search_page(query, n))])
    return [Video(**v) for v in raw]


def summarize(videos: list[Video]) -> dict:
    """Numbers the LLM (and the page) reason about."""
    if not videos:
        return {"count": 0}
    views = sorted(v.views for v in videos)
    recent = [v for v in videos if v.age_days is not None and v.age_days <= 365]
    long_form = [v for v in videos if (v.duration_s or 0) >= 480]
    return {
        "count": len(videos),
        "median_views": views[len(views) // 2],
        "max_views": views[-1],
        "recent_12m": len(recent),
        "recent_median_views": sorted(v.views for v in recent)[len(recent) // 2] if recent else 0,
        "long_form_share": round(len(long_form) / len(videos), 2),
        "median_duration_min": round(sorted(v.duration_s or 0 for v in videos)[len(videos) // 2] / 60, 1),
        "channels": len({v.channel for v in videos}),
        "top_titles": [v.title for v in sorted(videos, key=lambda v: -v.views)[:8]],
    }
