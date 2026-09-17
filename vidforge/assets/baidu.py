"""百度图片 — the `acjson` endpoint the image search page itself calls (no browser, no key).

Every result is labelled 版权未知: Baidu carries no licence information, so the picker asks
for confirmation before adding one and the source page goes into credits.txt. `objURL` (the
original file) is lightly obfuscated with a fixed substitution table; `middleURL` is the
fallback when the original host refuses.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import AssetError, Candidate, download, slug

UNKNOWN_LABEL = "版权未知（百度网页图片，使用前请到来源页确认）"
_TABLE = str.maketrans("wkv1ju2it3hs4g5rq6fp7eo8dn9cm0bla", "abcdefghijklmnopqrstuvw1234567890")


def decode_url(s: str) -> str:
    s = s.replace("_z2C$q", ":").replace("_z&e3B", ".").replace("AzdH3F", "/")
    return s.translate(_TABLE)


class BaiduImagesProvider:
    name = "baidu"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        if kind != "image":
            return []
        q = urllib.parse.urlencode({"tn": "resultjson_com", "ipn": "rj", "ct": 201326592, "fp": "result",
                                    "word": query, "queryWord": query, "cl": 2, "lm": -1, "ie": "utf-8", "oe": "utf-8",
                                    "pn": (page - 1) * per_page, "rn": per_page, "gsm": "1e"})
        req = urllib.request.Request(f"https://image.baidu.com/search/acjson?{q}", headers={
            "Referer": "https://image.baidu.com/", "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36 Edg/128"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            raise AssetError(f"百度图片请求失败：{e}") from None
        # Baidu emits invalid JSON escapes (\' and stray backslashes); repair before parsing
        text = re.sub(r"\\(?![\\/\"bfnrtu])", "", text.replace("\\'", "'"))
        try:
            data = json.loads(text, strict=False)
        except json.JSONDecodeError:
            data = {}
        out: list[Candidate] = []
        for d in data.get("data", []):
            if not d or not d.get("thumbURL"):
                continue
            full = decode_url(d["objURL"]) if d.get("objURL") else (d.get("middleURL") or d["thumbURL"])
            ref = decode_url(d["fromURL"]) if d.get("fromURL") else ""
            title = re.sub(r"<[^>]+>", "", d.get("fromPageTitleEnc") or d.get("fromPageTitle") or "")
            out.append(Candidate(
                provider="baidu", id=hashlib.sha1(full.encode()).hexdigest()[:12], kind="image",
                thumb_url=d["thumbURL"], preview_url=d.get("middleURL") or d.get("hoverURL") or d["thumbURL"],
                download_url=full, width=int(d.get("width") or 0), height=int(d.get("height") or 0), duration=None,
                author=urllib.parse.urlparse(ref or full).netloc, license=UNKNOWN_LABEL, page_url=ref or full,
                title=title or query, desc=title, ext=".jpg",
            ))
        return out

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        dest = Path(folder) / f"{slug(cand.title or 'baidu')}-{cand.id}.jpg"
        try:
            return download(cand.download_url, dest, referer=cand.page_url)
        except Exception:  # noqa: BLE001 — original host refused: take Baidu's cached medium copy
            if cand.preview_url and cand.preview_url != cand.download_url:
                return download(cand.preview_url, dest, referer="https://image.baidu.com/")
            raise
