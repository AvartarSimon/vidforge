"""One place for the HTTP both of the hot-list fetchers need."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import USER_AGENT, TrendsError


def get(url: str, *, headers: dict | None = None, timeout: float = 20.0) -> str:
    h = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise TrendsError(f"{url} 取不到：{e}") from None


def get_json(url: str, **kw) -> dict:
    body = get(url, **kw)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise TrendsError(f"{url} 返回的不是 JSON（{len(body)} 字符）") from None
