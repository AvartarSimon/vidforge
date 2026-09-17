"""Internet Archive — public-domain films, newsreels, photographs (the history channel's B-roll).

Only items that declare a licence we can use (public domain mark, CC0, CC BY/BY-SA) are
returned; the Archive also hosts plenty of uploads with no rights information at all, and
"no information" is not "free". Videos: the item's mp4 (h.264) if present, else ogv/webm
(ffmpeg reads both); the browser preview plays the same file. No key needed."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from . import Candidate, download, http_json, slug

SEARCH = "https://archive.org/advancedsearch.php"
_OK = re.compile(r"publicdomain|creativecommons\.org/licenses/(by|by-sa)/|cc0", re.I)
_BAD = re.compile(r"/by-nc|/by-nd|/by-nc-nd|/by-nc-sa", re.I)


def licence_label(url: str | None) -> str | None:
    if not url or _BAD.search(url) or not _OK.search(url):
        return None
    if "publicdomain/mark" in url:
        return "Public Domain Mark"
    if "zero" in url or "cc0" in url.lower():
        return "CC0"
    m = re.search(r"licenses/(by(?:-sa)?)/([\d.]+)", url)
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else "CC"


class ArchiveProvider:
    name = "archive"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        media = "movies" if kind == "video" else "image"
        q = urllib.parse.urlencode({"q": f"({query}) AND mediatype:({media}) AND licenseurl:*", "fl[]": ["identifier", "title", "date", "licenseurl", "creator", "description", "downloads"],
                                    "rows": per_page, "page": page, "output": "json", "sort[]": "downloads desc"}, doseq=True)
        docs = http_json(f"{SEARCH}?{q}").get("response", {}).get("docs", [])
        out: list[Candidate] = []
        for d in docs:
            lic = licence_label(d.get("licenseurl"))
            if not lic:
                continue
            ident = d["identifier"]
            title = d.get("title") if isinstance(d.get("title"), str) else (d.get("title") or [ident])[0]
            desc = d.get("description") if isinstance(d.get("description"), str) else " ".join(d.get("description") or [])
            creator = d.get("creator") if isinstance(d.get("creator"), str) else ", ".join(d.get("creator") or [])
            cand = Candidate(provider="archive", id=ident[:40], kind=kind, thumb_url=f"https://archive.org/services/img/{ident}",
                             preview_url="", download_url=f"ia:{ident}", width=0, height=0, duration=None,
                             author=creator or "Internet Archive", license=lic, page_url=f"https://archive.org/details/{ident}",
                             title=title or ident, desc=(desc or "")[:200] + (f" ({str(d.get('date'))[:4]})" if d.get("date") else ""))
            if kind == "video":
                if len(out) >= 12:                       # metadata call per item: keep the first dozen
                    break
                if not self._resolve(cand):
                    continue
            out.append(cand)
        return out

    @staticmethod
    def _resolve(cand: Candidate) -> bool:
        """Fill preview/download URL, size and duration from the item's file list."""
        ident = cand.download_url[3:] if cand.download_url.startswith("ia:") else cand.id
        meta = http_json(f"https://archive.org/metadata/{ident}")
        files = meta.get("files", [])
        if cand.kind == "video":
            vids = [f for f in files if f.get("name", "").lower().endswith((".mp4", ".ogv", ".webm", ".m4v"))
                    and not f.get("name", "").lower().endswith(".thumbs")]
            if not vids:
                return False
            vids.sort(key=lambda f: (0 if f["name"].lower().endswith(".mp4") else 1, -int(float(f.get("size") or 0))))
            f = vids[0]
        else:
            imgs = [f for f in files if f.get("name", "").lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))
                    and "thumb" not in f.get("name", "").lower()]
            if not imgs:
                return False
            imgs.sort(key=lambda f: -int(float(f.get("size") or 0)))
            f = imgs[0]
        url = f"https://archive.org/download/{ident}/{urllib.parse.quote(f['name'])}"
        cand.preview_url = url
        cand.download_url = url
        cand.width, cand.height = int(f.get("width") or 0), int(f.get("height") or 0)
        try:
            cand.duration = float(f.get("length")) if f.get("length") else None
        except ValueError:
            cand.duration = None
        cand.ext = Path(f["name"]).suffix.lower()
        return True

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        if cand.download_url.startswith("ia:") and not self._resolve(cand):
            from . import AssetError
            raise AssetError(f"Internet Archive item {cand.id} has no usable file")
        return download(cand.download_url, Path(folder) / f"{slug(cand.title or 'archive')}-{slug(cand.id)}{cand.ext or '.mp4'}")
