"""参考视频：别人做得好的视频，下载到本地看、拆结构。

Two separate things live here and in `frameworks.py`:

  * the **library** (this module): videos found by searching YouTube / B站 by views, or pasted as a
    link (抖音 / TikTok / 快手 / 小红书 / anything yt-dlp knows), or imported from a file the user
    saved themselves. Kept in ~/.vidforge/references/<id>/ — one folder per video, with the video,
    its thumbnail and an info.json. Nothing here is ever cut into a render: these are for watching
    and for learning the shape of a good video, not material.
  * the **framework** extracted from one of them (frameworks.py), which becomes a structure template
    the script step can apply directly.

What each platform allows, measured 2026-11-17 from Melbourne:

    YouTube   search: the results page (views, length, age); download: yt-dlp, capped at 480p —
              a 44-minute talk at 720p was 350 MB, and the shape of a video reads fine at 480p
    B站       search: the web search API, sorted by plays (needs the homepage's buvid3 cookie);
              download: yt-dlp's DASH streams answer HTTP 567 abroad, the html5 player's single mp4
              (playurl platform=html5) downloads at 720p
    抖音 / TikTok / 快手 / 小红书
              no search without request signing (see trends.UNREACHABLE); a pasted link is tried
              with yt-dlp, and when the platform refuses, the answer is to save it in the app and
              import the file
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import ffmpeg

REF_DIR = Path.home() / ".vidforge" / "references"
MAX_HEIGHT = 480
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/130.0 Safari/537.36")
_BV = re.compile(r"(BV[0-9A-Za-z]{10})")


class RefError(RuntimeError):
    pass


def platform_of(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    for key, name in (("bilibili", "bilibili"), ("b23.tv", "bilibili"), ("youtube", "youtube"), ("youtu.be", "youtube"),
                      ("douyin", "douyin"), ("tiktok", "tiktok"), ("kuaishou", "kuaishou"),
                      ("xiaohongshu", "xiaohongshu"), ("xhslink", "xiaohongshu")):
        if key in host:
            return name
    return "web"


PLATFORM_NAMES = {"youtube": "YouTube", "bilibili": "B站", "douyin": "抖音", "tiktok": "TikTok",
                  "kuaishou": "快手", "xiaohongshu": "小红书", "web": "网页", "local": "本地文件"}


# -- search -------------------------------------------------------------------------------------
def search(site: str, query: str, n: int = 12) -> list[dict]:
    """Candidates for a topic, most watched first: {url, title, author, views, seconds, site, thumb}."""
    query = query.strip()
    if not query:
        raise RefError("先写一个主题")
    if site == "youtube":
        from .research import youtube
        try:
            vids = youtube.search(Path.home() / ".vidforge", query, n=n)
        except youtube.ResearchError as e:
            raise RefError(str(e)) from None
        out = [{"url": v.url, "title": v.title, "author": v.channel, "views": v.views, "seconds": v.duration_s,
                "site": "youtube", "thumb": f"https://i.ytimg.com/vi/{v.video_id}/mqdefault.jpg"} for v in vids]
    elif site == "bilibili":
        out = _bilibili_search(query, n)
    else:
        raise RefError(f"{PLATFORM_NAMES.get(site, site)} 没法直接搜索（要请求签名）：在 App 里找到视频后粘贴链接，或者保存下来导入")
    return sorted(out, key=lambda c: -(c.get("views") or 0))


def _opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _bili_session():
    op = _opener()
    head = {"User-Agent": _UA, "Referer": "https://www.bilibili.com/"}
    # the search API answers 412 to a request without the buvid3 cookie the homepage sets
    op.open(urllib.request.Request("https://www.bilibili.com/", headers=head), timeout=15).read(512)
    return op, head


def _bili_json(op, head, url: str) -> dict:
    data = json.loads(op.open(urllib.request.Request(url, headers=head), timeout=20).read())
    if data.get("code") != 0:
        raise RefError(f"B站接口：{data.get('message') or data.get('code')}")
    return data.get("data") or {}


def _bilibili_search(query: str, n: int) -> list[dict]:
    op, head = _bili_session()
    q = urllib.parse.urlencode({"search_type": "video", "keyword": query, "order": "click", "page": 1})
    out = []
    for v in (_bili_json(op, head, "https://api.bilibili.com/x/web-interface/search/type?" + q).get("result") or [])[:n]:
        mins, _, secs = str(v.get("duration", "")).partition(":")
        thumb = v.get("pic") or ""
        out.append({"url": f"https://www.bilibili.com/video/{v.get('bvid')}",
                    "title": re.sub(r"<[^>]+>", "", v.get("title") or ""), "author": v.get("author") or "",
                    "views": int(v.get("play") or 0),
                    "seconds": int(mins) * 60 + int(secs) if mins.isdigit() and secs.isdigit() else None,
                    "site": "bilibili", "thumb": ("https:" + thumb) if thumb.startswith("//") else thumb})
    return out


# -- the library ----------------------------------------------------------------------------------
def _new_id(platform: str, key: str) -> str:
    key = re.sub(r"[^0-9A-Za-z_-]+", "", key)[:40] or time.strftime("%Y%m%d%H%M%S")
    return f"{platform}-{key}"


def _write_info(folder: Path, info: dict) -> dict:
    video = folder / "video.mp4"
    info = {**info, "id": folder.name, "seconds": round(ffmpeg.duration(video), 2), "size": list(ffmpeg.video_size(video)),
            "added": time.strftime("%Y-%m-%d %H:%M")}
    if not (folder / "thumb.jpg").exists():
        ffmpeg.run(["-y", "-ss", str(min(3.0, info["seconds"] / 3)), "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=480:-2", str(folder / "thumb.jpg")])
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return info


def download(url: str, log=print) -> dict:
    """Fetch one video into the library. Returns its info."""
    url = url.strip()
    if not re.match(r"https?://", url):
        raise RefError("要一个以 http 开头的链接")
    plat = platform_of(url)
    REF_DIR.mkdir(parents=True, exist_ok=True)
    if plat == "bilibili":
        return _bilibili_download(url, log)
    return _ytdlp_download(url, plat, log)


def _bilibili_download(url: str, log) -> dict:
    m = _BV.search(url)
    if not m:
        # b23.tv short links: follow the redirect to the real page first
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            m = _BV.search(r.geturl())
    if not m:
        raise RefError("这个 B站链接里找不到 BV 号")
    bv = m.group(1)
    op, head = _bili_session()
    view = _bili_json(op, head, f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")
    q = urllib.parse.urlencode({"bvid": bv, "cid": view["cid"], "qn": 64, "platform": "html5", "high_quality": 1})
    durl = _bili_json(op, head, f"https://api.bilibili.com/x/player/playurl?{q}").get("durl") or []
    if not durl:
        raise RefError("B站没有给出可以下载的地址（会员或充电专属视频下载不了）")
    folder = REF_DIR / _new_id("bilibili", bv)
    folder.mkdir(parents=True, exist_ok=True)
    log(f"下载 B站 {bv}：{view.get('title', '')}")
    with op.open(urllib.request.Request(durl[0]["url"], headers=head), timeout=120) as r, open(folder / "video.mp4", "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    pic = view.get("pic") or ""
    try:
        with op.open(urllib.request.Request(pic, headers=head), timeout=20) as r:
            (folder / "thumb.jpg").write_bytes(r.read())
    except Exception:  # noqa: BLE001  a frame of the video will do instead
        pass
    stat = view.get("stat") or {}
    return _write_info(folder, {"url": f"https://www.bilibili.com/video/{bv}", "platform": "bilibili",
                                "title": view.get("title", ""), "author": (view.get("owner") or {}).get("name", ""),
                                "views": stat.get("view"), "likes": stat.get("like"), "description": (view.get("desc") or "")[:500]})


def _ytdlp_download(url: str, plat: str, log) -> dict:
    try:
        import yt_dlp
    except ImportError:
        raise RefError("下载要 yt-dlp：.venv/bin/pip install yt-dlp（./install-mac.sh 会装好）") from None
    tmp = REF_DIR / f".incoming-{int(time.time())}"
    tmp.mkdir(parents=True, exist_ok=True)
    opts = {"quiet": True, "noprogress": True, "noplaylist": True, "outtmpl": str(tmp / "video.%(ext)s"),
            "format": f"bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]/b", "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg.find_binary("ffmpeg"), "writethumbnail": True, "retries": 3}
    if shutil.which("node"):
        # YouTube now wants a JavaScript runtime for some formats; Node is already on this machine
        opts["js_runtimes"] = {"node": {}}
    log(f"下载 {PLATFORM_NAMES.get(plat, plat)}：{url}")
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
    except Exception as e:  # noqa: BLE001  yt-dlp raises its own types; the message is what matters
        shutil.rmtree(tmp, ignore_errors=True)
        hint = ("这个平台要登录或请求签名，下载不了：在 App 里保存视频（或录屏），再用「导入本地文件」"
                if plat in ("douyin", "kuaishou", "xiaohongshu", "tiktok") else "可以换一个链接，或者保存下来导入")
        raise RefError(f"下载失败：{str(e).splitlines()[0][:160]}。{hint}") from None
    video = next((p for p in tmp.glob("video.*") if p.suffix in (".mp4", ".mkv", ".webm", ".mov")), None)
    if video is None:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RefError("下载完没有找到视频文件")
    if video.suffix != ".mp4":
        ffmpeg.run(["-y", "-i", str(video), "-c", "copy", str(tmp / "video.mp4")])
        video.unlink()
    for t in tmp.glob("video.*"):
        if t.suffix in (".jpg", ".jpeg", ".webp", ".png"):
            ffmpeg.run(["-y", "-i", str(t), str(tmp / "thumb.jpg")])
            t.unlink()
    folder = REF_DIR / _new_id(plat, str(info.get("id") or ""))
    if folder.exists():
        shutil.rmtree(folder)
    tmp.rename(folder)
    return _write_info(folder, {"url": info.get("webpage_url") or url, "platform": plat, "title": info.get("title") or "",
                                "author": info.get("uploader") or info.get("channel") or "", "views": info.get("view_count"),
                                "likes": info.get("like_count"), "description": (info.get("description") or "")[:500]})


def import_file(name: str, data: bytes, title: str = "") -> dict:
    """A video the user saved from an app that does not allow downloading."""
    if not data:
        raise RefError("空文件")
    REF_DIR.mkdir(parents=True, exist_ok=True)
    folder = REF_DIR / _new_id("local", f"{time.strftime('%Y%m%d%H%M%S')}")
    folder.mkdir(parents=True)
    src = folder / ("upload" + (Path(name).suffix.lower() or ".mp4"))
    src.write_bytes(data)
    try:
        if src.suffix == ".mp4":
            src.rename(folder / "video.mp4")
        else:
            ffmpeg.run(["-y", "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
                        str(folder / "video.mp4")])
            src.unlink()
        return _write_info(folder, {"url": "", "platform": "local", "title": title or Path(name).stem, "author": ""})
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(folder, ignore_errors=True)
        raise RefError(f"读不出这个视频：{e}") from None


def listing() -> list[dict]:
    out = []
    for f in sorted(REF_DIR.glob("*/info.json")) if REF_DIR.is_dir() else []:
        try:
            info = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        info["has_framework"] = (f.parent / "framework.json").is_file()
        out.append(info)
    return sorted(out, key=lambda i: i.get("added", ""), reverse=True)


def folder_of(ref_id: str) -> Path:
    folder = (REF_DIR / ref_id).resolve()
    if folder.parent != REF_DIR.resolve() or not (folder / "info.json").is_file():
        raise RefError(f"没有这个参考视频：{ref_id}")
    return folder


def remove(ref_id: str) -> None:
    shutil.rmtree(folder_of(ref_id))
