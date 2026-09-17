"""Google Images through the user's browser (Playwright, the dedicated logged-in profile).

Default is **Creative-Commons only** (`tbs=sur:cl` — the new `udm=2` image UI ignores the old
`il:cl`; probed 2026-09-17). `google_all:` drops the filter and labels every result "版权未知";
the picker asks for confirmation before adding such a picture.

How: the new UI has no `/imgres` links, but clicking a tile opens a viewer whose big image
(`img[jsname="kn3ccd"]`) is loaded straight from the original host — that `src` is the
full-size URL with real dimensions. We click the first N tiles (~0.6 s each), record URL,
size, title and the viewer's source-page link, and download later with the user's session
(source hosts such as picryl block plain clients; the CDN file itself is fine).
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path

from . import AssetError, Candidate, download, slug

CC_LABEL = "Creative Commons（Google 筛选，请到来源页核对具体许可）"
UNKNOWN_LABEL = "版权未知（网页图片，使用前请到来源页确认）"
TILE_LIMIT = 20
_VIEWER_JS = """(prev) => {
  const imgs = [...document.querySelectorAll('img[jsname="kn3ccd"], img.sFlh5c')]
    .filter(i => /^https?:/.test(i.src) && !i.src.includes('gstatic.com') && i.src !== prev && i.naturalWidth > 200);
  if (!imgs.length) return null;
  const img = imgs[imgs.length - 1];
  const box = img.closest('c-wiz') || img.closest('div[jsaction]') || document;
  const a = [...box.querySelectorAll('a[href^="http"]')].find(a => !a.href.includes('google.'));
  return { src: img.src, w: img.naturalWidth, h: img.naturalHeight, ref: a ? a.href : '' };
}"""


class GoogleImagesProvider:
    def __init__(self, cc_only: bool = True):
        self.cc_only = cc_only
        self.name = "google" if cc_only else "google_all"

    def search(self, query: str, kind: str, page: int = 1, per_page: int = TILE_LIMIT) -> list[Candidate]:
        if kind != "image":
            return []
        from ..browser import _lock, _playwright, launch
        sync_playwright = _playwright()
        params = {"q": query, "hl": "en", "udm": "2", "safe": "active"}
        if self.cc_only:
            params["tbs"] = "sur:cl"
        url = "https://www.google.com/search?" + urllib.parse.urlencode(params)
        rows: list[dict] = []
        with _lock, sync_playwright() as pw:
            ctx, pg = launch(pw, headless=False)
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(2000)
                if pg.locator("text=unusual traffic").count() or "/sorry/" in pg.url:
                    raise AssetError("Google 要求验证（unusual traffic）：请在打开的窗口里完成验证后重试")
                for _ in range(page - 1):
                    pg.mouse.wheel(0, 3000); pg.wait_for_timeout(800)
                tiles = pg.locator("div[data-docid]")
                seen: set[str] = set()
                prev_src = ""
                for i in range(tiles.count()):
                    t = tiles.nth(i)
                    try:
                        docid = t.get_attribute("data-docid") or ""
                        if not docid or docid in seen:
                            continue
                        seen.add(docid)
                        meta = t.evaluate("""el => { const img = el.querySelector('img');
                            const lines = el.innerText.split(String.fromCharCode(10)).map(s => s.trim()).filter(s => s && !/^(Licensable|Product|Recipe|Video)$/i.test(s));
                            return { thumb: img ? (img.currentSrc || img.src) : '', title: lines[0] || '', site: lines[1] || '' }; }""")
                        t.scroll_into_view_if_needed(); t.click(timeout=5000)
                        view = None
                        for _ in range(10):                     # wait for the viewer's big image (<= 4 s)
                            pg.wait_for_timeout(400)
                            view = pg.evaluate(_VIEWER_JS, prev_src)
                            if view:
                                break
                        if not view:
                            continue
                        prev_src = view["src"]
                        rows.append({"docid": docid, **meta, **view})
                        if len(rows) >= per_page:
                            break
                    except Exception:  # noqa: BLE001 — a tile that would not click; move on
                        continue
            finally:
                ctx.close()
        out: list[Candidate] = []
        for r in rows:
            src = r["src"]
            host = urllib.parse.urlparse(r["ref"] or src).netloc
            ext = Path(urllib.parse.urlparse(src).path).suffix.lower()
            out.append(Candidate(
                provider=self.name, id=r["docid"][:16], kind="image",
                thumb_url=r["thumb"] or src, preview_url=src, download_url=src,
                width=r["w"], height=r["h"], duration=None, author=host,
                license=CC_LABEL if self.cc_only else UNKNOWN_LABEL, page_url=r["ref"] or src,
                title=r["title"] or query, desc=f"{r['title']} {r['site']}",
                ext=ext if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg",
            ))
        return out

    def fetch(self, cand: Candidate, folder: Path) -> Path:
        dest = Path(folder) / f"{slug(cand.title or 'google')}-{cand.id}{cand.ext or '.jpg'}"
        try:
            return download(cand.download_url, dest, referer="https://www.google.com/")
        except Exception:  # noqa: BLE001 — host refuses plain clients: fetch inside the browser session
            from ..browser import _lock, _playwright, launch
            sync_playwright = _playwright()
            with _lock, sync_playwright() as pw:
                ctx, pg = launch(pw, headless=False)
                try:
                    resp = pg.request.get(cand.download_url, headers={"Referer": "https://www.google.com/"}, timeout=60000)
                    if not resp.ok:
                        raise AssetError(f"下载失败 HTTP {resp.status}：{cand.download_url}")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(resp.body())
                finally:
                    ctx.close()
            return dest
