"""Pixabay photos and videos. Free API (5000 req/hour), key: PIXABAY_API_KEY.
Licence: Pixabay Content License (free commercial use, no attribution required).
Note: without special approval the largest photo Pixabay serves via API is 1280 px wide
(`largeImageURL`); fine at 1080p with the 2x zoompan supersampling, soft at 4K."""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from .. import env
from . import Candidate, download, http_json, slug

API = "https://pixabay.com/api/"
LICENSE = "Pixabay Content License"


class PixabayProvider:
    name = "pixabay"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        key = env.require("PIXABAY_API_KEY")
        if kind == "video":
            q = urllib.parse.urlencode({"key": key, "q": query, "per_page": per_page, "page": page, "safesearch": "true"})
            data = http_json(f"{API}videos/?{q}")
            return [c for c in (self._video(h) for h in data.get("hits", [])) if c]
        q = urllib.parse.urlencode({"key": key, "q": query, "image_type": "photo", "orientation": "horizontal",
                                    "per_page": per_page, "page": page, "safesearch": "true", "min_width": 1280})
        data = http_json(f"{API}?{q}")
        return [self._photo(h) for h in data.get("hits", [])]

    @staticmethod
    def _photo(h: dict) -> Candidate:
        big = h.get("fullHDURL") or h.get("largeImageURL") or h["webformatURL"]
        return Candidate(
            provider="pixabay", id=str(h["id"]), kind="image",
            thumb_url=h.get("webformatURL", big), preview_url=big, download_url=big,
            width=h.get("imageWidth", 0), height=h.get("imageHeight", 0), duration=None,
            author=h.get("user", ""), license=LICENSE, page_url=h.get("pageURL", ""),
            title=(h.get("tags") or "").split(",")[0].strip(), desc=h.get("tags") or "", ext=".jpg",
        )

    @staticmethod
    def _video(h: dict) -> Candidate | None:
        vids = h.get("videos") or {}
        big = vids.get("large") or vids.get("medium")
        small = vids.get("small") or vids.get("medium") or big
        if not big or not big.get("url"):
            return None
        return Candidate(
            provider="pixabay", id=str(h["id"]), kind="video",
            thumb_url=(small or big).get("thumbnail", ""), preview_url=small["url"], download_url=big["url"],
            width=big.get("width", 0), height=big.get("height", 0), duration=float(h.get("duration") or 0),
            author=h.get("user", ""), license=LICENSE, page_url=h.get("pageURL", ""),
            title=(h.get("tags") or "").split(",")[0].strip(), desc=h.get("tags") or "", ext=".mp4",
        )

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        name = f"{slug(cand.title or 'pixabay')}-{cand.id}{cand.ext or '.jpg'}"
        return download(cand.download_url, Path(folder) / name)
