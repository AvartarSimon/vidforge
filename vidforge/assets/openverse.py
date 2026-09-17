"""Openverse — WordPress's CC-licensed media search across Flickr, Wikimedia, museums (800 M+).

Official API, anonymous use is rate-limited (register at api.openverse.org for more; set
OPENVERSE_CLIENT_ID / OPENVERSE_CLIENT_SECRET to use a token). We request only
cc0 / pdm / by / by-sa: BY-ND forbids derivatives and a crop-and-zoom edit is arguably one.
Images only (Openverse audio is not what a video needs)."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import Candidate, download, http_json, slug

API = "https://api.openverse.org/v1"
LICENSES = "cc0,pdm,by,by-sa"
_token: dict = {"value": None, "exp": 0}


def _auth_header() -> dict:
    cid, sec = os.environ.get("OPENVERSE_CLIENT_ID", ""), os.environ.get("OPENVERSE_CLIENT_SECRET", "")
    if not cid or not sec:
        return {}
    if _token["value"] and time.time() < _token["exp"] - 60:
        return {"Authorization": f"Bearer {_token['value']}"}
    data = urllib.parse.urlencode({"client_id": cid, "client_secret": sec, "grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(f"{API}/auth_tokens/token/", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read())
    _token.update(value=tok["access_token"], exp=time.time() + int(tok.get("expires_in", 3600)))
    return {"Authorization": f"Bearer {_token['value']}"}


class OpenverseProvider:
    name = "openverse"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = 30) -> list[Candidate]:
        if kind != "image":
            return []
        q = urllib.parse.urlencode({"q": query, "license": LICENSES, "page_size": min(per_page, 20 if not _auth_header() else per_page), "page": page, "mature": "false"})
        data = http_json(f"{API}/images/?{q}", headers=_auth_header())
        out = []
        for r in data.get("results", []):
            w, h = int(r.get("width") or 0), int(r.get("height") or 0)
            if w and w < 800:
                continue
            lic = f"CC {r.get('license', '').upper()} {r.get('license_version', '')}".replace("CC PDM", "Public Domain Mark").replace("CC CC0", "CC0").strip()
            out.append(Candidate(
                provider="openverse", id=str(r["id"])[:16], kind="image",
                thumb_url=r.get("thumbnail") or r["url"], preview_url=r["url"], download_url=r["url"],
                width=w, height=h, duration=None, author=r.get("creator") or r.get("source") or "",
                license=lic, page_url=r.get("foreign_landing_url") or r.get("url"),
                title=r.get("title") or "", desc=" ".join(t.get("name", "") for t in (r.get("tags") or [])[:12]),
                ext=Path(urllib.parse.urlparse(r["url"]).path).suffix.lower() or ".jpg",
            ))
        return out

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        ext = cand.ext if cand.ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"
        return download(cand.download_url, Path(folder) / f"{slug(cand.title or 'openverse')}-{cand.id}{ext}", referer=cand.page_url)
