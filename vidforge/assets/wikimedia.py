"""Wikimedia Commons — the history channel's archive: paintings, maps, engravings, old photos.
No API key. Only files whose licence is public domain / CC0 / CC BY / CC BY-SA are returned;
CC BY(-SA) requires attribution, which credits.txt supplies. Images only (Commons video is
webm/ogv and rarely stock-like).

Download is the original JPEG/PNG when it is at most 4000 px wide; larger files and TIFF/SVG
scans come as the 1920 px Commons rendition (the widest size Commons serves)."""

from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path

from . import Candidate, download, http_json, slug

API = "https://commons.wikimedia.org/w/api.php"
_ALLOWED = re.compile(r"public domain|\bpd\b|cc0|cc[- ]by(?!.*nc)(?!.*nd)|no restrictions", re.I)
_TAG = re.compile(r"<[^>]+>")
DOWNLOAD_WIDTH = 1920
ORIGINAL_MAX = 4000        # originals up to this width are downloaded as-is (sharper than any thumb)
ALLOWED_WIDTHS = (120, 250, 330, 500, 960, 1280, 1920)   # the only thumb sizes Commons serves (w.wiki/GHai; probed 2026-09)


def allowed_width(max_w: int) -> int:
    """Largest permitted thumbnail width strictly below the original's width."""
    ok = [w for w in ALLOWED_WIDTHS if w < max_w]
    return ok[-1] if ok else ALLOWED_WIDTHS[0]


def licence_ok(short: str) -> bool:
    """Accept PD / CC0 / CC BY / CC BY-SA; reject NC, ND, fair use, unknown."""
    s = (short or "").strip()
    if not s or re.search(r"fair use|non-free|copyright", s, re.I):
        return False
    return bool(_ALLOWED.search(s))


def thumb_at(thumburl: str, width: int) -> str:
    """Commons thumb URLs embed the width: …/thumb/a/ab/X.jpg/640px-X.jpg -> any width."""
    return re.sub(r"/(\d+)px-", f"/{width}px-", thumburl, count=1)


class CommonsProvider:
    name = "commons"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        if kind != "image":
            return []
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "search", "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": "6",
            "gsrlimit": per_page, "gsroffset": (page - 1) * per_page,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 640,
            "iiextmetadatafilter": "LicenseShortName|Artist|ObjectName|ImageDescription",
        })
        data = http_json(f"{API}?{q}")
        out: list[Candidate] = []
        for page_ in (data.get("query") or {}).get("pages", []):
            ii = (page_.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName") or {}).get("value", "")
            if not licence_ok(lic) or not ii.get("thumburl"):
                continue
            w, h = int(ii.get("width", 0)), int(ii.get("height", 0))
            if w < 800:
                continue
            artist = html.unescape(_TAG.sub("", (meta.get("Artist") or {}).get("value", ""))).strip()
            desc = html.unescape(_TAG.sub(" ", (meta.get("ImageDescription") or {}).get("value", ""))).strip()[:300]
            title = page_.get("title", "").replace("File:", "")
            ext = Path(urllib.parse.urlparse(ii.get("url", "")).path).suffix.lower()
            if w <= ORIGINAL_MAX and ext in (".jpg", ".jpeg", ".png"):
                download_url = ii["url"]                          # original: sharpest, and a sane size
            else:
                download_url = thumb_at(ii["thumburl"], allowed_width(min(w, DOWNLOAD_WIDTH + 1)))
            out.append(Candidate(
                provider="commons", id=str(page_.get("pageid")), kind="image",
                thumb_url=ii["thumburl"], preview_url=thumb_at(ii["thumburl"], allowed_width(min(w, 1281))),
                download_url=download_url,
                width=w, height=h, duration=None, author=artist, license=lic,
                page_url=ii.get("descriptionurl", ""), title=title, desc=desc, ext=(ext if ext in (".jpg", ".jpeg", ".png") else Path(ii["thumburl"]).suffix) or ".jpg",
            ))
        return out

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        name = f"{slug(Path(cand.title).stem or 'commons')}-{cand.id}{cand.ext or '.jpg'}"
        return download(cand.download_url, Path(folder) / name)
