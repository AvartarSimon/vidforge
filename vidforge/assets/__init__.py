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

    def set_check(self, rel: str, result: dict) -> None:
        """Vision verdict for a downloaded file: {"ok": bool, "reason": str, "model": str}."""
        rec = self.data["files"].setdefault(rel, {})
        rec["check"] = result

    def warning(self, rel: str) -> str | None:
        rec = self.data["files"].get(rel) or {}
        chk = rec.get("check")
        return None if not chk or chk.get("ok", True) else (chk.get("reason") or "视觉模型判定不可用")

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


def download(url: str, dest: Path, referer: str | None = None, retries: int = 3) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) vidforge/0.3"}
    if referer:
        headers["Referer"] = referer
    try:
        req = urllib.request.Request(url, headers=headers)
    except ValueError as e:                       # "unknown url type" — a candidate without a real URL
        raise AssetError(f"download failed: {e}") from None
    # Commons (and CDNs) answer 429/503 when several files are fetched back to back — the
    # storyboard autofill does exactly that — so back off and retry before giving up.
    for attempt, wait in enumerate((0, 3, 8, 15)[:retries + 1]):
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            break
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code in (429, 503) and attempt < retries:
                continue
            raise AssetError(f"download failed: {e}") from None
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
    if name == "openverse":
        from .openverse import OpenverseProvider
        return OpenverseProvider()
    if name == "archive":
        from .archive import ArchiveProvider
        return ArchiveProvider()
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


# Hosts whose pictures are watermarked previews or paid stock: never usable in a video, whatever
# Google/Baidu says about them. Matched as a suffix of the URL host.
BLOCKED_HOSTS = (
    "shutterstock.com", "gettyimages.com", "gettyimages.co.uk", "istockphoto.com", "alamy.com", "alamyimages.fr",
    "dreamstime.com", "123rf.com", "depositphotos.com", "stock.adobe.com", "fotolia.com", "bigstockphoto.com",
    "canstockphoto.com", "agefotostock.com", "superstock.com", "bridgemanimages.com", "sciencephoto.com",
    "vcg.com", "quanjing.com", "nipic.com", "699pic.com", "58pic.com", "veer.com", "huitu.com", "tuchong.com",
    "zcool.com.cn", "photophoto.cn", "sucai.com", "16pic.com", "ooopic.com", "51yuansu.com", "pngtree.com",
    "freepik.com", "vectorstock.com", "colourbox.com", "pixtastock.com", "photoac.com", "storyblocks.com",
)


def blocked_host(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    return any(host == h or host.endswith("." + h) for h in BLOCKED_HOSTS)


_WORD = re.compile(r"[A-Za-z0-9一-鿿]+")
_NOISE = {"ship", "city", "town", "photo", "picture", "painting", "map", "image", "view", "scene", "concept"}


def relevant(c: Candidate, query: str) -> bool:
    """Strict text check for unattended picks: the query's proper nouns / numbers must actually
    appear in the file's title or description (a 'Mayflower' hit on a *plant* named mayflower
    still passes here — the vision check catches that). Rule: every capitalised word or number
    of the query is found, or at least 60 % of all content words are. Titles like "IMG_1234"
    with no match fail — better an empty slot than a wrong picture."""
    from ..keywords import _STOP
    words = [w for w in _WORD.findall(query) if len(w) > 1 and w.lower() not in _NOISE and w.lower() not in _STOP]
    if not words:
        return False
    hay = f"{c.title} {c.desc}".lower()
    key = [w for w in words if w[0].isupper() or w.isdigit() or any("一" <= ch <= "鿿" for ch in w)]
    hits = [w for w in words if w.lower() in hay]
    if key and all(w.lower() in hay for w in key):
        return True
    need = max(1, round(0.6 * len(words)))
    return len(hits) >= need and (not key or any(w in key for w in hits))


def fetch(root: Path, cand: Candidate, library: Library | None = None) -> Path:
    prov = get_provider(cand.provider)
    lib = library or Library(root)
    dest = prov.fetch(cand, root / "assets" / prov.name)
    lib.remember(cand, dest)
    lib.save()
    return dest


def preview_file(root: Path, cand: Candidate) -> Path:
    """Small copy of a candidate (its thumbnail) for the vision check: watermarks and captions are
    obvious at thumbnail size, the download is tens of KB, and nothing enters the library if the
    picture gets rejected."""
    url = cand.thumb_url or cand.preview_url
    if cand.kind == "video" or not url:
        raise AssetError("no preview to check")
    folder = root / "assets" / ".check"
    dest = folder / f"{cand.provider}-{slug(cand.id)}{Path(urllib.parse.urlparse(url).path).suffix or '.jpg'}"
    return download(url, dest, referer=cand.page_url or None, retries=1)


def check_file(root: Path, rel: str, lib: Library | None = None) -> dict | None:
    """Vision-check an already downloaded picture (a hand-picked one) and record the verdict in
    the library; None when there is no vision model. The picture stays — the UI shows a warning
    and the user swaps it — because on a CPU-only machine the check takes about a minute, too
    long to make someone wait on every click."""
    from .. import llm
    from PIL import Image
    if not llm.vision_model():
        return None
    lib = lib or Library(root)
    src = root / rel
    small = root / "assets" / ".check" / f"local-{slug(Path(rel).stem)}.jpg"
    small.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as im:
            im.thumbnail((640, 640))
            im.convert("RGB").save(small, "JPEG", quality=85)
        v = llm.vision_check(str(small), "")
    except (OSError, llm.LlmError) as e:
        result = {"ok": True, "reason": f"未能核对：{e}", "model": llm.vision_model(), "skipped": True}
    else:
        why = "水印/版权标记" if v["watermark"] else "带文字标注" if v["text"] else None
        result = {"ok": why is None, "reason": f"{why}（{v['reason']}）" if why else v["reason"], "model": v["model"]}
    lib.set_check(rel, result)
    lib.save()
    return result


def vision_verdict(root: Path, cand: Candidate, subject: str | None, log=None) -> str | None:
    """None = fine; else a short reason to reject (watermark / text overlay / does not depict).
    Silently None when no local vision model is pulled: the text filters are then all we have."""
    from .. import llm
    if not llm.vision_model():
        return None
    try:
        v = llm.vision_check(str(preview_file(root, cand)), subject or "")
    except (llm.LlmError, AssetError) as e:
        if log:
            log(f"    vision check skipped: {e}")
        return None
    if v["watermark"]:
        return f"水印/版权标记（{v['reason']}）"
    if v["text"]:
        return f"带文字标注（{v['reason']}）"
    if subject and v["depicts"] is False:
        return f"内容不符（{v['reason']}）"
    return None


def pick_for_spec(root: Path, lib: Library, prov_name: str, kind: str, query: str, need: float = 0.0,
                  strict: bool = False, log=None, tries: int = 4, vision: bool = True) -> Path:
    """Resolve one "provider:query" spec to a downloaded file: remembered pick, else the best
    unused landscape result (long enough for `need` seconds when it is a video). Shared by the
    build-time resolver and the storyboard's one-click autofill so both pick the same file.

    strict (autofill): only candidates whose title/description really names the query, and — when
    a local vision model exists — no watermark, no burned-in text, and the picture must depict the
    query. Up to `tries` candidates are examined; none passing raises, leaving the slot empty."""
    prov_name = {"wikimedia": "commons"}.get(prov_name, prov_name)
    spec = f"{prov_name}:{kind}:{query}"
    dest = lib.pick(spec)
    if dest is not None:
        return dest
    cands = [c for c in rank(search(root, prov_name, query, kind), query)
             if (c.landscape or kind == "image") and not blocked_host(c.download_url)]
    used = lib.used_ids(prov_name)
    fresh = [c for c in cands if c.id not in used]
    pool = fresh or cands
    if kind == "video":
        long_enough = [c for c in pool if (c.duration or 0) >= need]
        pool = long_enough or pool
    if not pool:
        raise AssetError(f"no {kind} found on {prov_name} for {query!r}")
    if not strict:
        chosen = pool[0]
    else:
        chosen = None
        rejected: list[str] = []
        for c in pool[:tries]:
            if not relevant(c, query):
                rejected.append(f"'{c.title[:40]}' 标题/描述不含 {query!r}")
                continue
            why = vision_verdict(root, c, query, log) if (kind == "image" and vision) else None
            if why:
                rejected.append(f"'{c.title[:40]}' {why}")
                continue
            chosen = c
            break
        if chosen is None:
            raise AssetError(f"no accurate {kind} for {query!r}: " + "; ".join(rejected[:tries]))
    dest = fetch(root, chosen, lib)
    lib.remember_pick(spec, dest.resolve().relative_to(root.resolve()).as_posix())
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
        need = (needed_seconds or {}).get(seg.id, 0.0)
        if clip.slice_length:
            need = clip.slice_length
        try:
            dest = pick_for_spec(project.root, lib, prov_name, clip.source_kind, query, need)
        except AssetError as e:
            raise AssetError(f"segment {seg.id}: {e}") from None
        if clip.source_kind == "video":
            clip.video = dest
        else:
            clip.image = dest
        log(f"  asset {seg.id:<12} {clip.source_kind} <- {clip.source!r} -> {dest.name}")
