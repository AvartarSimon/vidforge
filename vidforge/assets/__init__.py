"""Asset providers: search licence-safe stock/public-domain media, fetch what the user picked.

    Candidate  — one search result (thumbnail + preview URLs, size, duration, licence, author)
    Provider   — search(query, kind, page) -> [Candidate];  fetch(candidate, folder) -> Path
    Library    — per-project index of downloaded files with licence/attribution (assets/index.json)

Sources and why only these: Pexels and Pixabay (free licence, no attribution required but we
credit anyway) and Wikimedia Commons filtered to public-domain / CC0 / CC-BY / CC-BY-SA (the
history channel's archive: paintings, maps, old photographs; CC-BY requires attribution, which
credits.txt provides). Anything without a clear licence is rejected — a copyright strike costs
the channel more than any picture is worth.

A clip spec "pexels:volcano" (or "pixabay:", "commons:") is auto-resolved at build time to the
first unused landscape result; the UI's picker lets the user choose instead.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import env
from ..project import Clip, Project

SEARCH_CACHE_TTL = 24 * 3600


class AssetError(RuntimeError):
    pass


@dataclass
class Candidate:
    provider: str            # pexels | pixabay | commons
    id: str
    kind: str                # image | video
    thumb_url: str           # small preview for the picker grid
    preview_url: str         # image: large; video: playable mp4 (CDN direct link)
    download_url: str        # what fetch() saves
    width: int
    height: int
    duration: float | None   # video seconds
    author: str
    license: str             # e.g. "Pexels License", "CC BY-SA 4.0", "Public domain"
    page_url: str
    title: str = ""
    ext: str = ""            # file extension incl. dot; derived from download_url when empty
    desc: str = ""           # caption / tags / Commons description — used for relevance ranking

    @property
    def landscape(self) -> bool:
        return self.width >= self.height

    def credit_line(self) -> str:
        who = self.author or "unknown"
        return f"{who} — {self.license} — {self.page_url}"


class Library:
    """assets/index.json: one record per downloaded file + the auto-pick memory per query."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.folder = self.root / "assets"
        self.path = self.folder / "index.json"
        self.data: dict = {"files": {}, "picks": {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and "files" in loaded:
                    self.data = loaded
            except json.JSONDecodeError:
                pass

    def used_ids(self, provider: str) -> set[str]:
        return {r["id"] for r in self.data["files"].values() if r.get("provider") == provider}

    def remember(self, cand: Candidate, dest: Path) -> None:
        rel = dest.resolve().relative_to(self.root.resolve()).as_posix()
        self.data["files"][rel] = {
            "provider": cand.provider, "id": cand.id, "kind": cand.kind, "author": cand.author,
            "license": cand.license, "page_url": cand.page_url, "title": cand.title,
            "width": cand.width, "height": cand.height, "duration": cand.duration,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def record(self, rel: str) -> dict | None:
        return self.data["files"].get(rel)

    def remember_pick(self, spec: str, rel: str) -> None:
        self.data["picks"][spec] = rel

    def pick(self, spec: str) -> Path | None:
        rel = self.data["picks"].get(spec)
        p = self.root / rel if rel else None
        return p if p and p.exists() else None

    def forget_pick(self, spec: str) -> None:
        self.data["picks"].pop(spec, None)

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")

    def credits(self, used: set[str] | None = None) -> str:
        """Attribution block for the description. `used` = relative paths actually referenced."""
        lines: list[str] = []
        by_provider: dict[str, list[str]] = {}
        for rel, r in self.data["files"].items():
            if used is not None and rel not in used:
                continue
            line = f"{r.get('author') or 'unknown'} — {r.get('license', '')} — {r.get('page_url', '')}"
            by_provider.setdefault(r.get("provider", "other"), []).append(line)
        names = {"pexels": "Pexels", "pixabay": "Pixabay", "commons": "Wikimedia Commons"}
        for prov, ls in by_provider.items():
            lines.append(f"{names.get(prov, prov)}:")
            lines += [f"  {x}" for x in dict.fromkeys(ls)]
        return "Media credits\n" + "\n".join(lines) if lines else ""


# -- shared HTTP helpers -------------------------------------------------------------------
def http_json(url: str, headers: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "vidforge/0.2 (local tool)", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hint = {401: "invalid API key", 403: "forbidden (key/quota?)", 429: "rate limited"}.get(e.code, "")
        raise AssetError(f"{url.split('?')[0]} -> HTTP {e.code} {hint}") from None
    except urllib.error.URLError as e:
        raise AssetError(f"{url.split('/')[2]} unreachable: {e.reason}") from None


def download(url: str, dest: Path, referer: str | None = None) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) vidforge/0.3"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
    except urllib.error.URLError as e:
        tmp.unlink(missing_ok=True)
        raise AssetError(f"download failed: {e}") from None
    tmp.replace(dest)
    return dest


def cached_search(root: Path, key: str, fn) -> list[dict]:
    """24 h on-disk cache for search responses (Pexels allows 200 requests/hour)."""
    folder = root / "assets" / ".search-cache"
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < SEARCH_CACHE_TTL:
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    result = fn()
    f.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "query"


# -- provider registry -----------------------------------------------------------------------
def get_provider(name: str):
    name = {"wikimedia": "commons"}.get(name, name)
    if name == "pexels":
        from .pexels import PexelsProvider
        return PexelsProvider()
    if name == "pixabay":
        from .pixabay import PixabayProvider
        return PixabayProvider()
    if name == "commons":
        from .wikimedia import CommonsProvider
        return CommonsProvider()
    if name in ("google", "google_all"):
        from .google_images import GoogleImagesProvider
        return GoogleImagesProvider(cc_only=(name == "google"))
    if name == "baidu":
        from .baidu import BaiduImagesProvider
        return BaiduImagesProvider()
    raise AssetError(f"unknown asset provider '{name}' (pexels | pixabay | commons | google | google_all | baidu)")


def search(root: Path, provider: str, query: str, kind: str, page: int = 1, relax: bool = True) -> list[Candidate]:
    """Search one provider. With `relax`, a multi-word query that finds nothing is retried with
    its last word dropped, down to one word (Commons needs every word to match; stock sites
    get noisy but never empty)."""
    prov = get_provider(provider)
    if kind not in ("image", "video"):
        raise AssetError("kind must be image or video")
    words = query.split()
    attempts = [" ".join(words[:k]) for k in range(len(words), 0, -1)] if relax else [query]
    for q in attempts:
        raw = cached_search(root, f"{prov.name}|{kind}|{page}|{q}", lambda q=q: [asdict(c) for c in prov.search(q, kind, page)])
        if raw:
            return [Candidate(**c) for c in raw]
    return []


def rank(cands: list[Candidate], query: str) -> list[Candidate]:
    """Relevance order: query words present in the title (Commons search order is weak),
    landscape, then resolution; stable so provider order breaks ties."""
    word_re = re.compile(r"[A-Za-z0-9一-鿿]+")
    words = [w.lower() for w in word_re.findall(query) if len(w) > 2]

    def score(c: Candidate) -> float:
        title = (c.title or "").lower()
        title_words = [w for w in word_re.findall(title) if len(w) > 2 and not w.isdigit()]
        desc = (c.desc or "").lower()
        hits = sum(1 for w in words if w in title)
        desc_hits = sum(1 for w in words if w not in title and w in desc)
        extra = max(0, len(title_words) - hits)          # "Pangu.jpg" beats "IBM Beijing, Pangu Plaza.jpg"
        # portrait video is useless in a 16:9 frame; a portrait painting is fine (blur-filled)
        shape = (2 if c.landscape else (0 if c.kind == "image" else -20))
        return hits * 10 + desc_hits * 6 - min(extra, 6) + shape + min(c.width / 2000.0, 1.0)
    return sorted(cands, key=score, reverse=True)


def fetch(root: Path, cand: Candidate, library: Library | None = None) -> Path:
    prov = get_provider(cand.provider)
    lib = library or Library(root)
    dest = prov.fetch(cand, root / "assets" / prov.name)
    lib.remember(cand, dest)
    lib.save()
    return dest


def resolve_all(project: Project, needed_seconds: dict[str, float] | None = None, log=print) -> None:
    """Fill image/video for every clip that only has a `source` spec (auto-pick)."""
    pending = [(s, c) for s in project.segments for c in s.clips if c.needs_asset]
    if not pending:
        return
    lib = Library(project.root)
    for seg, clip in pending:
        assert clip.source is not None
        prov_name, _, query = clip.source.partition(":")
        prov_name = {"wikimedia": "commons"}.get(prov_name, prov_name)
        need = (needed_seconds or {}).get(seg.id, 0.0)
        if clip.slice_length:
            need = clip.slice_length
        spec = f"{prov_name}:{clip.source_kind}:{query}"
        dest = lib.pick(spec)
        if dest is None:
            cands = [c for c in rank(search(project.root, prov_name, query, clip.source_kind), query)
                     if c.landscape or clip.source_kind == "image"]
            used = lib.used_ids(prov_name)
            fresh = [c for c in cands if c.id not in used]
            pool = fresh or cands
            if clip.source_kind == "video":
                long_enough = [c for c in pool if (c.duration or 0) >= need]
                pool = long_enough or pool
            if not pool:
                raise AssetError(f"segment {seg.id}: no {clip.source_kind} found on {prov_name} for {query!r}")
            dest = fetch(project.root, pool[0], lib)
            lib.remember_pick(spec, dest.resolve().relative_to(project.root.resolve()).as_posix())
            lib.save()
        if clip.source_kind == "video":
            clip.video = dest
        else:
            clip.image = dest
        log(f"  asset {seg.id:<12} {clip.source_kind} <- {clip.source!r} -> {dest.name}")
