"""Pexels photos and videos. Free API (200 req/hour, 20k/month), key: PEXELS_API_KEY.
Licence: free for commercial use, no attribution required (credited anyway)."""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from .. import env
from . import Candidate, download, http_json, slug

API = "https://api.pexels.com"
LICENSE = "Pexels License"


class PexelsProvider:
    name = "pexels"

    def _get(self, path: str, query: dict) -> dict:
        url = f"{API}{path}?{urllib.parse.urlencode(query)}"
        return http_json(url, headers={"Authorization": env.require("PEXELS_API_KEY")})

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        if kind == "video":
            data = self._get("/videos/search", {"query": query, "orientation": "landscape", "per_page": per_page, "page": page})
            return [c for c in (self._video(v) for v in data.get("videos", [])) if c]
        data = self._get("/v1/search", {"query": query, "orientation": "landscape", "size": "large",
                                        "per_page": per_page, "page": page})
        return [self._photo(p) for p in data.get("photos", [])]

    @staticmethod
    def _photo(p: dict) -> Candidate:
        src = p["src"]
        return Candidate(
            provider="pexels", id=str(p["id"]), kind="image",
            thumb_url=src.get("medium") or src.get("small") or src["original"],
            preview_url=src.get("large2x") or src["original"],
            download_url=src.get("original") if p["width"] > 1880 else (src.get("large2x") or src["original"]),
            width=p["width"], height=p["height"], duration=None,
            author=p.get("photographer", ""), license=LICENSE, page_url=p.get("url", ""),
            title=p.get("alt", "") or "", desc=p.get("alt", "") or "", ext=".jpg",
        )

    @staticmethod
    def best_file(files: list[dict], min_width: int = 1920) -> dict | None:
        """Smallest mp4 at least `min_width` wide, else the widest."""
        fs = [f for f in files if f.get("file_type") == "video/mp4" and f.get("width")]
        if not fs:
            return None
        wide = [f for f in fs if f["width"] >= min_width]
        return min(wide, key=lambda f: f["width"]) if wide else max(fs, key=lambda f: f["width"])

    @classmethod
    def _video(cls, v: dict) -> Candidate | None:
        f = cls.best_file(v.get("video_files", []))
        if not f:
            return None
        # a small file for the in-browser preview so scrubbing is quick
        small = min((x for x in v.get("video_files", []) if x.get("file_type") == "video/mp4" and x.get("width")),
                    key=lambda x: abs(x["width"] - 960), default=f)
        user = v.get("user") or {}
        return Candidate(
            provider="pexels", id=str(v["id"]), kind="video",
            thumb_url=v.get("image", ""), preview_url=small["link"], download_url=f["link"],
            width=f["width"], height=f["height"], duration=float(v.get("duration") or 0),
            author=user.get("name", ""), license=LICENSE, page_url=v.get("url", ""), ext=".mp4",
        )

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        name = f"{slug(cand.title or 'pexels')}-{cand.id}{'-' + str(cand.width) + 'p' if cand.kind == 'video' else ''}{cand.ext or '.jpg'}"
        return download(cand.download_url, Path(folder) / name)
