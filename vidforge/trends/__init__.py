"""热点发现：现在什么在被讨论，以及其中哪些适合这个频道。

This is the upstream half that was missing. `research/` could already answer "is this topic worth
making?" — it could not answer "which topic should I look at today". So:

    fetch(root, sources) -> list[Topic]     what is on the public hot lists right now
    score.rank(topics, ...)                 which of those fit 「用数据看热点，用历史看今天」

**What is reachable, measured on 2026-10-05** (every source below was tried, not assumed):

    ✅ 今日头条热榜      50 条，官方 JSON，无 key
    ✅ 百度热搜          52 条
    ✅ Google News RSS   每个关键词 100 条（深度文章）
    ✅ B 站排行榜        100 条，干净 JSON
    ✅ Hacker News       官方 Firebase API
    🟡 YouTube          要 YOUTUBE_API_KEY 走 chart=mostPopular；**无 key 的 trending 页实测 0 条**
                        （页面现在要 JS/consent），所以没有 key 时这一源为空
    ❌ 抖音              热点榜 API 返回 200 但 0 字节 —— 要 a-bogus 签名
    ❌ TikTok           页面里的 rehydration JSON 不含视频列表，列表走签名 XHR
    ❌ 快手              TLS 握手超时 / GraphQL 400
    ❌ 微博热搜          200 但是登录墙，解析出 0 条；知乎热榜 401；Reddit .json 403

那三个短视频平台（抖音 / TikTok / 快手）是锁得最死的，而且它们榜上热的多是娱乐和剧情，
和这个频道的形态本来就不匹配。真正该参考的长视频/资讯平台（YouTube、B 站、头条）恰好都拿得到。
抖音的正规途径是巨量算数（trendinsight.oceanengine.com），要注册和登录，没有开放端点。

礼貌约定：带正常 UA、串行请求、热榜缓存 15 分钟。这是读公开页面，不是爬站——
一个人一天看几次热榜，不应该比用浏览器打开它们产生更多请求。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

CACHE_SECONDS = 900          # 15 minutes: a hot list does not move faster than that
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class TrendsError(RuntimeError):
    pass


@dataclass
class Topic:
    title: str
    source: str                      # which hot list it came from
    rank: int                        # 1-based position on that list
    url: str = ""
    heat: int | None = None          # the platform's own number, when it gives one
    when: str = ""                   # ISO date for article-like sources
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """For de-duplicating the same story across lists."""
        import re
        return re.sub(r"[\s\W_]+", "", self.title.lower())[:40]


# Each entry: (module, label, weight, kind). The weight is the platform's say in the final score;
# the owner's stated priority is YouTube / 抖音 / TikTok / 今日头条 / 快手, so the reachable members
# of that list lead, and 抖音/TikTok/快手 keep their weights for the day an official route appears
# rather than being silently dropped.
#
# `kind` matters because the two groups answer different questions, and mixing them in one table
# lets the larger one bury the other:
#   hot   大家在看什么          —— attention, measured by the platform
#   news  我的领域今天发生了什么  —— relevance, queried by keyword
SOURCES: dict[str, tuple[str, str, float, str]] = {
    "youtube": ("youtube", "YouTube 热门", 1.0, "hot"),
    "toutiao": ("toutiao", "今日头条热榜", 1.0, "hot"),
    "bilibili": ("bilibili", "B 站排行榜", 0.8, "hot"),
    "baidu": ("baidu", "百度热搜", 0.6, "hot"),
    "googlenews": ("googlenews", "Google News", 0.7, "news"),
    "hn": ("hn", "Hacker News", 0.4, "news"),
}
KINDS = {"hot": "热榜：大家在看什么", "news": "领域新闻：我关心的方向今天发生了什么"}

# Named but not implemented: kept visible so the gap is a documented fact rather than an omission.
UNREACHABLE = {
    "douyin": "抖音热点榜 API 需要 a-bogus 签名（实测返回 200 但 0 字节）；正规途径是巨量算数，要登录",
    "tiktok": "探索/标签页的 JSON 不含视频列表，列表走签名 XHR",
    "kuaishou": "TLS 握手超时 / GraphQL 400",
    "weibo": "s.weibo.com/top/summary 是登录墙，解析出 0 条",
}


def available() -> list[dict]:
    out = [{"id": k, "label": v[1], "weight": v[2], "kind": v[3], "ok": True}
           for k, v in SOURCES.items()]
    out += [{"id": k, "label": k, "weight": 0.0, "kind": "hot", "ok": False, "why": why}
            for k, why in UNREACHABLE.items()]
    return out


def kind_of(source: str) -> str:
    return SOURCES.get(source, (None, None, None, "hot"))[3]


def fetch_one(root: Path, source: str, *, queries: list[str] | None = None,
              log=None) -> list[Topic]:
    """One hot list, cached. Never raises: a source that is down must not take the page down."""
    if source not in SOURCES:
        raise TrendsError(f"未知的热点源 '{source}'（可选：{', '.join(SOURCES)}）")
    from ..assets import cached_search
    mod_name = SOURCES[source][0]
    mod = __import__(f"vidforge.trends.{mod_name}", fromlist=["x"])
    stamp = int(time.time() // CACHE_SECONDS)       # the cache key *is* the 15-minute bucket
    key = f"trend|{source}|{stamp}|{'|'.join(queries or [])}"
    try:
        raw = cached_search(root, key, lambda: [t.__dict__ for t in mod.fetch(queries=queries)])
    except Exception as e:                           # noqa: BLE001 — any network/parse failure
        if log:
            log(f"  {source}: 取不到（{type(e).__name__}: {str(e)[:80]}）")
        return []
    return [Topic(**r) for r in raw]


def fetch(root: Path, sources: list[str] | None = None, *, queries: list[str] | None = None,
          log=None) -> list[Topic]:
    """Every requested hot list, in series — see the politeness note in the module docstring."""
    out: list[Topic] = []
    for s in (sources or list(SOURCES)):
        got = fetch_one(root, s, queries=queries, log=log)
        if log:
            log(f"  {s}: {len(got)} 条")
        out.extend(got)
    return out
