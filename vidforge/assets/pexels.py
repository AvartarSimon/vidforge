"""Pexels stock photos and videos. Free API (200 req/hour, 20k/month), key: PEXELS_API_KEY.

License: free for commercial use, no attribution required — but we record photographer and
URL per file in `assets/pexels/index.json` (`credits()` formats them for the description).

Selection rules
    photo : first landscape result not already used in this project; `src.large2x` (1880 px)
            or `src.original` when the frame is wider than that.
    video : prefer clips at least `min_duration` long; among those pick the file whose width is
            the smallest >= frame width (else the widest); mp4 only.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import env

API = "https://api.pexels.com"


class PexelsError(RuntimeError):
    pass


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "query"


class Pexels:
    def __init__(self, folder: Path, per_page: int = 15):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.index_path = self.folder / "index.json"
        self.index: dict = {"by_spec": {}, "used_ids": []}
        if self.index_path.exists():
            try:
                self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.per_page = per_page

    # -- HTTP -------------------------------------------------------------------
    def _get(self, path: str, query: dict) -> dict:
        url = f"{API}{path}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"Authorization": env.require("PEXELS_API_KEY")})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            hint = {401: "invalid API key", 429: "rate limited (200/h)"}.get(e.code, "")
            raise PexelsError(f"Pexels {path} -> HTTP {e.code} {hint}") from None
        except urllib.error.URLError as e:
            raise PexelsError(f"Pexels unreachable: {e.reason}") from None

    def _download(self, url: str, dest: Path) -> Path:
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "vidforge"})
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.replace(dest)
        return dest

    # -- selection (pure, unit-tested) --------------------------------------------
    @staticmethod
    def pick_photo(photos: list[dict], used: set[int], width: int) -> tuple[dict, str] | None:
        for p in photos:
            if p["id"] in used or p["width"] < p["height"]:
                continue
            src = p["src"]
            url = src.get("original") if width > 1880 and src.get("original") else src.get("large2x") or src["original"]
            return p, url
        return None

    @staticmethod
    def pick_video(videos: list[dict], used: set[int], width: int, min_duration: float) -> tuple[dict, dict] | None:
        def files(v: dict) -> list[dict]:
            return [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]

        def best_file(v: dict) -> dict | None:
            fs = files(v)
            if not fs:
                return None
            wide = [f for f in fs if f["width"] >= width]
            return min(wide, key=lambda f: f["width"]) if wide else max(fs, key=lambda f: f["width"])

        candidates = [v for v in videos if v["id"] not in used and v.get("width", 0) >= v.get("height", 0)]
        long_enough = [v for v in candidates if v.get("duration", 0) >= min_duration]
        for pool in (long_enough, candidates):
            for v in pool:
                f = best_file(v)
                if f:
                    return v, f
        return None

    # -- public -------------------------------------------------------------------
    def photo(self, query: str, width: int = 1920) -> Path:
        spec = f"photo:{query}"
        hit = self.index["by_spec"].get(spec)
        if hit and (self.folder / hit["file"]).exists():
            return self.folder / hit["file"]
        data = self._get("/v1/search", {"query": query, "orientation": "landscape", "size": "large",
                                        "per_page": self.per_page})
        picked = self.pick_photo(data.get("photos", []), set(self.index["used_ids"]), width)
        if not picked:
            raise PexelsError(f"Pexels: no unused landscape photo for {query!r}")
        p, url = picked
        ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
        dest = self._download(url, self.folder / f"{_slug(query)}-{p['id']}{ext}")
        self._remember(spec, p["id"], dest, p.get("photographer", ""), p.get("url", ""), p.get("alt", ""))
        return dest

    def video(self, query: str, min_duration: float = 0.0, width: int = 1920) -> Path:
        spec = f"video:{query}"
        hit = self.index["by_spec"].get(spec)
        if hit and (self.folder / hit["file"]).exists():
            return self.folder / hit["file"]
        data = self._get("/videos/search", {"query": query, "orientation": "landscape",
                                            "per_page": self.per_page})
        picked = self.pick_video(data.get("videos", []), set(self.index["used_ids"]), width, min_duration)
        if not picked:
            raise PexelsError(f"Pexels: no unused landscape video for {query!r}")
        v, f = picked
        dest = self._download(f["link"], self.folder / f"{_slug(query)}-{v['id']}-{f['width']}p.mp4")
        user = v.get("user") or {}
        self._remember(spec, v["id"], dest, user.get("name", ""), v.get("url", ""),
                       f"{v.get('duration', 0)}s {f['width']}x{f['height']}")
        return dest

    def _remember(self, spec: str, pid: int, dest: Path, author: str, url: str, note: str) -> None:
        self.index["by_spec"][spec] = {"id": pid, "file": dest.name, "author": author, "url": url, "note": note}
        if pid not in self.index["used_ids"]:
            self.index["used_ids"].append(pid)

    def save(self) -> None:
        self.index_path.write_text(json.dumps(self.index, indent=1, ensure_ascii=False), encoding="utf-8")

    def credits(self) -> str:
        lines = [f"{e['author']} — {e['url']}" for e in self.index["by_spec"].values() if e.get("url")]
        return "Stock footage/photos via Pexels:\n" + "\n".join(dict.fromkeys(lines)) if lines else ""
