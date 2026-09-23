"""Local web UI: a 5-step wizard (script -> voice -> visuals -> render -> publish) over one
project.json, served by the standard library on 127.0.0.1.

    vidforge ui my-video            # http://127.0.0.1:8765, opens the browser

project.json on disk is the single source of truth — every edit is validated and saved there,
so the CLI and the UI never disagree. Builds run in a background thread; the page polls
/api/build/status for log lines and the finished files.

API (all JSON):
    GET  /api/project?lang=          project + per-segment resolved view (clips, audio, timing)
    POST /api/project {raw}          validate + save
    POST /api/tts?lang= {id}         synthesize one segment (proof-listen)
    GET  /api/search?q=&kind=&source=&page=   candidates from pexels | pixabay | commons
    POST /api/assets/fetch {candidate}        download a chosen candidate -> {path, credit}
    POST /api/assets/upload {name, data_b64}  local file -> assets/
    GET  /api/keywords?id=&lang=     search-term suggestions from the narration
    POST /api/build?lang=&burn=      start;  GET /api/build/status;  POST /api/build/cancel
    GET  /api/poster/<seg>/<clip>?lang=       still frame of a video clip (at its `in`)
    GET  /api/health                 ffmpeg / node / keys
    GET  /files/<rel>                any file under the project (range requests for media)
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import env, ffmpeg, keywords, pipeline, project as proj, script_parser
from ..tts.silent import estimate_seconds

STATIC = Path(__file__).resolve().parent / "static"


CONFIG_DIR = Path.home() / ".vidforge"
RECENT = CONFIG_DIR / "recent.json"
HISTORY_KEEP = 30
HISTORY_MIN_GAP = 60          # seconds between automatic snapshots (an explicit Save always snapshots)


def recent_projects() -> list[dict]:
    try:
        items = json.loads(RECENT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        items = []
    out = []
    for it in items:
        p = Path(it.get("path", ""))
        if (p / "project.json").is_file():
            try:
                title = json.loads((p / "project.json").read_text(encoding="utf-8")).get("title", p.name)
            except Exception:  # noqa: BLE001
                title = p.name
            out.append({"path": str(p), "title": title, "opened": it.get("opened", 0), "final": (p / "build" / "final.mp4").exists()})
    return sorted(out, key=lambda x: -x["opened"])


def remember_project(root: Path) -> None:
    CONFIG_DIR.mkdir(exist_ok=True)
    items = [it for it in recent_projects() if Path(it["path"]) != root.resolve()]
    items.insert(0, {"path": str(root.resolve()), "opened": time.time()})
    RECENT.write_text(json.dumps(items[:20], ensure_ascii=False, indent=1), encoding="utf-8")


def workspace_dir() -> Path:
    ws = Path(os.environ.get("VIDFORGE_WORKSPACE", "") or (Path.home() / "vidforge-projects"))
    ws.mkdir(parents=True, exist_ok=True)
    return ws


class State:
    def __init__(self, project_path: Path | None):
        self.project_path: Path | None = None
        self.root: Path = workspace_dir()
        self.lock = threading.Lock()
        self.build = {"state": "idle", "lines": [], "lang": None, "started": None, "finished": None, "error": None}
        self.autofill = {"state": "idle", "done": 0, "total": 0, "lines": [], "result": None}
        self.checks: list[str] = []          # hand-picked files waiting for the (slow) vision check
        self.check_current: str | None = None
        self._check_worker: threading.Thread | None = None
        self._last_snapshot = 0.0
        if project_path is not None:
            self.open(project_path)

    def open(self, project_path: Path) -> None:
        project_path = Path(project_path).resolve()
        if project_path.is_dir():
            project_path = project_path / "project.json"
        if not project_path.is_file():
            raise FileNotFoundError(f"project file not found: {project_path}")
        self.project_path = project_path
        self.root = project_path.parent
        remember_project(self.root)

    @property
    def has_project(self) -> bool:
        return self.project_path is not None

    def enqueue_check(self, rel: str) -> None:
        """Vision-check a downloaded picture in the background; the verdict lands in assets/index.json
        and project_view() surfaces it as clip["warning"]."""
        from ..assets import check_file
        root = self.root
        self.checks.append(rel)
        if self._check_worker and self._check_worker.is_alive():
            return

        def work():
            while self.checks:
                r = self.check_current = self.checks.pop(0)
                try:
                    check_file(root, r)
                except Exception as e:  # noqa: BLE001  never let the worker die on one bad file
                    print(f"[vidforge] check {r}: {e}")
                finally:
                    self.check_current = None
        self._check_worker = threading.Thread(target=work, daemon=True)
        self._check_worker.start()

    def read_raw(self) -> dict:
        if self.project_path is None:
            raise proj.ProjectError("no project open")
        return json.loads(self.project_path.read_text(encoding="utf-8"))

    def write_raw(self, data: dict, *, snapshot: bool = False) -> None:
        if self.project_path is None:
            raise proj.ProjectError("no project open")
        new_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if self.project_path.exists():
            old = self.project_path.read_text(encoding="utf-8")
            if old != new_text and (snapshot or time.time() - self._last_snapshot > HISTORY_MIN_GAP):
                hist = self.root / ".history"
                hist.mkdir(exist_ok=True)
                (hist / f"project-{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(old, encoding="utf-8")
                self._last_snapshot = time.time()
                for stale in sorted(hist.glob("project-*.json"))[:-HISTORY_KEEP]:
                    stale.unlink(missing_ok=True)
        self._snapshot_segments(data)
        tmp = self.project_path.with_suffix(".json.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        tmp.replace(self.project_path)

    def _snapshot_segments(self, data: dict) -> None:
        """Every segment whose content changed gets a version file: .history/segments/<id>/<ts>.json.
        Reverting one segment never touches the others."""
        base = self.root / ".history" / "segments"
        for s in data.get("segments") or []:
            sid = pipeline._safe(str(s.get("id", "")))
            if not sid:
                continue
            folder = base / sid
            folder.mkdir(parents=True, exist_ok=True)
            body = json.dumps(s, ensure_ascii=False, sort_keys=True)
            versions = sorted(folder.glob("*.json"))
            if versions:
                try:
                    last = json.loads(versions[-1].read_text(encoding="utf-8"))
                    if json.dumps(last.get("segment"), ensure_ascii=False, sort_keys=True) == body:
                        continue
                except json.JSONDecodeError:
                    pass
            ts = time.strftime("%Y%m%d-%H%M%S")
            name = f"{ts}.json"
            if (folder / name).exists():
                name = f"{ts}-{int(time.time() * 1000) % 1000:03d}.json"
            (folder / name).write_text(json.dumps({"time": ts, "segment": s}, ensure_ascii=False, indent=1), encoding="utf-8")
            for stale in sorted(folder.glob("*.json"))[:-HISTORY_KEEP]:
                stale.unlink(missing_ok=True)

    def segment_history(self, seg_id: str) -> list[dict]:
        folder = self.root / ".history" / "segments" / pipeline._safe(seg_id)
        out = []
        for f in sorted(folder.glob("*.json"), reverse=True) if folder.exists() else []:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            seg = d.get("segment", {})
            text = seg.get("text", "")
            clips = seg.get("clips") or [k for k in ("image", "video", "remotion") if k in seg]
            out.append({"name": f.name, "time": d.get("time", f.stem), "preview": text[:60], "clips": len(clips),
                        "label": seg.get("label")})
        return out

    def history(self) -> list[dict]:
        hist = self.root / ".history"
        return [{"name": f.name, "time": f.stem.replace("project-", ""), "size": f.stat().st_size}
                for f in sorted(hist.glob("project-*.json"), reverse=True)] if hist.exists() else []

    def load(self, lang: str | None) -> proj.Project:
        return proj.load(self.project_path, lang=lang or None)

    def build_dir(self, lang: str | None) -> Path:
        raw = self.read_raw()
        base = raw.get("language", "en")
        if not lang or lang == base:
            return self.root / raw.get("out_dir", "build")
        v = (raw.get("variants") or {}).get(lang) or {}
        return self.root / v.get("out_dir", f"build_{lang}")

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root.resolve()).as_posix()

    def start_build(self, lang: str | None, burn: bool | None) -> bool:
        with self.lock:
            if self.build["state"] == "running":
                return False
            self.build = {"state": "running", "lines": [], "lang": lang, "started": time.time(), "finished": None, "error": None}
        threading.Thread(target=self._run_build, args=(lang, burn), daemon=True).start()
        return True

    def _run_build(self, lang: str | None, burn: bool | None) -> None:
        pipeline.set_log(lambda line: self.build["lines"].append(line))
        try:
            p = self.load(lang)
            pipeline.build(p, burn=burn)
            self.build["state"] = "done"
        except pipeline.BuildCancelled:
            self.build["lines"].append("cancelled")
            self.build["state"] = "cancelled"
        except Exception as e:  # noqa: BLE001 — shown to the user in the log panel
            self.build["lines"].append(f"ERROR: {e}")
            self.build["error"] = str(e)
            self.build["state"] = "error"
            traceback.print_exc()
        finally:
            self.build["finished"] = time.time()
            pipeline.set_log(None)


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        server_version = "vidforge-ui"

        def log_message(self, fmt, *args):
            pass

        # -- helpers --------------------------------------------------------------
        def _json(self, obj, status=HTTPStatus.OK):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, msg, status=HTTPStatus.BAD_REQUEST, **extra):
            self._json({"error": msg, **extra}, status)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

        def _file(self, path: Path):
            if not path.is_file():
                return self._error("not found", HTTPStatus.NOT_FOUND)
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            size = path.stat().st_size
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a or 0)
                end = min(int(b) if b else size - 1, size - 1)
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store" if path.suffix in (".json", ".html", ".js", ".css") else "max-age=3600")
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (ConnectionAbortedError, BrokenPipeError):
                        return
                    remaining -= len(chunk)

        def _safe_path(self, rel: str) -> Path | None:
            p = (state.root / urllib.parse.unquote(rel)).resolve()
            try:
                p.relative_to(state.root.resolve())
            except ValueError:
                return None
            return p

        # -- routing ----------------------------------------------------------------
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(url.query))
            path = url.path
            try:
                if path in ("/", "/index.html"):
                    return self._file(STATIC / "index.html")
                if path.startswith("/static/"):
                    p = (STATIC / path[len("/static/"):]).resolve()
                    return self._file(p) if str(p).startswith(str(STATIC)) else self._error("forbidden", HTTPStatus.FORBIDDEN)
                if path.startswith("/files/"):
                    p = self._safe_path(path[len("/files/"):])
                    return self._file(p) if p else self._error("forbidden", HTTPStatus.FORBIDDEN)
                if path == "/api/project":
                    if not state.has_project:
                        return self._json({"home": True, "projects": recent_projects(), "workspace": str(workspace_dir())})
                    return self._json(self.project_view(q.get("lang")))
                if path == "/api/projects":
                    return self._json({"projects": recent_projects(), "workspace": str(workspace_dir())})
                if path == "/api/categories":
                    from .. import categories as cat_mod
                    return self._json({"categories": cat_mod.list_categories()})
                if path == "/api/categories/export":
                    from .. import categories as cat_mod
                    return self._json(cat_mod.export_all())
                if path == "/api/history":
                    return self._json({"history": state.history()})
                if path == "/api/segment/history":
                    return self._json({"versions": state.segment_history(q.get("id", ""))})
                if path == "/api/me":
                    from .. import me
                    lib = me.MeLibrary(me.library_dir(state.root))
                    items = lib.scan() if q.get("scan") or not lib.items() else lib.items()
                    return self._json({"folder": str(lib.folder), "items": items,
                                       "tags": sorted({t for i in items for t in i.get("tags", [])})})
                if path.startswith("/api/me/poster/"):
                    from .. import me
                    lib = me.MeLibrary(me.library_dir(state.root))
                    f = lib.folder / Path(urllib.parse.unquote(path[len("/api/me/poster/"):])).name
                    if not f.is_file():
                        return self._error("not found", HTTPStatus.NOT_FOUND)
                    out = state.build_dir(None) / "ui" / f"me_{f.stem}_{f.stat().st_size}.jpg"
                    if not out.exists():
                        out.parent.mkdir(parents=True, exist_ok=True)
                        ffmpeg.run(["-y", "-ss", "1", "-i", str(f), "-frames:v", "1", "-vf", "scale=480:-2", str(out)])
                    return self._file(out)
                if path == "/api/llm/status":
                    from .. import llm
                    return self._json({"available": llm.available()})
                if path == "/api/build/status":
                    return self._json(self.status_view())
                if path == "/api/health":
                    return self._json(self.health())
                if path == "/api/env/keys":
                    return self._json({"keys": env.KEYS})
                if path == "/api/voices":
                    return self._json(self.voices(q.get("provider", "edge"), q.get("lang")))
                if path == "/api/search":
                    return self.search(q)
                if path == "/api/research/youtube":
                    from ..research import youtube as yt
                    env.load_dotenv(state.root)
                    try:
                        vids = yt.search(state.root, (q.get("q") or "").strip(), int(q.get("n", 20)))
                    except Exception as e:  # noqa: BLE001
                        return self._error(str(e))
                    return self._json({"videos": [{**asdict(v), "url": v.url, "views_per_day": v.views_per_day} for v in vids],
                                       "summary": yt.summarize(vids), "source": vids[0].source if vids else None})
                if path == "/api/chat/sites":
                    from ..browser.chat import SITES
                    from ..browser import PROFILE_DIR
                    return self._json({"sites": [{"id": k, "label": v["label"], "url": v["url"]} for k, v in SITES.items()],
                                       "profile": str(PROFILE_DIR), "logged_in_profile": PROFILE_DIR.exists()})
                if path == "/api/chat/login/status":
                    from .. import browser
                    return self._json({"status": browser.LAST_LOGIN_STATUS, "running": browser._lock.locked()})
                if path == "/api/autofill":
                    return self._json(state.autofill)
                if path == "/api/keywords":
                    p = state.load(q.get("lang"))
                    seg = next((s for s in p.segments if s.id == q.get("id")), None)
                    return self._json({"keywords": keywords.suggest(seg.text) if seg else []})
                if path.startswith("/api/poster/"):
                    parts = path[len("/api/poster/"):].split("/")
                    return self.poster(urllib.parse.unquote(parts[0]), int(parts[1]) if len(parts) > 1 else 0, q.get("lang"))
                return self._error("not found", HTTPStatus.NOT_FOUND)
            except proj.ProjectError as e:
                return self._error(f"project.json: {e}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(url.query))
            path = url.path
            try:
                body = self._body()
                if path == "/api/project":
                    return self.save_project(body, snapshot=bool(body.get("snapshot")))
                if path == "/api/env":
                    if not state.has_project:
                        return self._error("先打开一个项目")
                    key, value = body.get("key", ""), body.get("value", "")
                    if key not in env.KEYS:
                        return self._error(f"未知的 key：{key}")
                    if not value.strip():
                        return self._error("value 不能为空")
                    f = env.save(state.root, key, value.strip())
                    return self._json({"saved": str(f)})
                if path == "/api/open":
                    try:
                        state.open(Path(body["path"]))
                    except (FileNotFoundError, KeyError) as e:
                        return self._error(f"打不开：{e}")
                    return self._json({"opened": str(state.project_path)})
                if path == "/api/instances/spawn":
                    proj_path = Path(body.get("path", ""))
                    if not proj_path.is_file() and not (proj_path / "project.json").is_file():
                        return self._error("项目不存在")
                    try:
                        url = spawn_instance(proj_path)
                    except RuntimeError as e:
                        return self._error(str(e))
                    return self._json({"url": url})
                if path == "/api/new":
                    name = re.sub(r"[^\w\-\u4e00-\u9fff ]+", "", body.get("name", "")).strip() or time.strftime("video-%Y%m%d-%H%M")
                    root = Path(body.get("dir") or workspace_dir()) / name
                    if (root / "project.json").exists():
                        return self._error("同名项目已存在")
                    (root / "assets").mkdir(parents=True, exist_ok=True)
                    tpl = json.loads(json.dumps(proj.TEMPLATE, ensure_ascii=False))
                    tpl["title"] = body.get("title") or name
                    tpl["language"] = body.get("language", "en")
                    tpl["segments"] = []
                    if body.get("category"):
                        from .. import categories as cat_mod
                        cat = cat_mod.load(body["category"])
                        if cat:
                            tpl["category"] = cat["id"]
                            for k, v in (cat.get("defaults") or {}).items():
                                if k in ("voice", "rate", "language", "lipsync", "outro_vocab"):
                                    tpl[k] = v
                                elif k == "tts_provider":
                                    tpl.setdefault("tts", {})["provider"] = v
                                elif k == "subtitles_bilingual":
                                    tpl.setdefault("subtitles", {})["bilingual"] = v
                    (root / "project.json").write_text(json.dumps(tpl, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    state.open(root)
                    return self._json({"opened": str(state.project_path)})
                if path == "/api/categories":
                    from .. import categories as cat_mod
                    try:
                        return self._json({"category": cat_mod.save(body)})
                    except cat_mod.CategoryError as e:
                        return self._error(str(e))
                if path == "/api/categories/delete":
                    from .. import categories as cat_mod
                    cat_mod.delete(body.get("id", ""))
                    return self._json({"categories": cat_mod.list_categories()})
                if path == "/api/categories/import":
                    from .. import categories as cat_mod
                    try:
                        saved = cat_mod.import_bundle(body.get("data") or {}, merge=body.get("merge", True))
                    except cat_mod.CategoryError as e:
                        return self._error(str(e))
                    return self._json({"imported": len(saved), "categories": cat_mod.list_categories()})
                if path == "/api/segment/restore":
                    sid, name = body.get("id", ""), Path(body.get("name", "")).name
                    f = state.root / ".history" / "segments" / pipeline._safe(sid) / name
                    if not f.is_file():
                        return self._error("版本不存在")
                    seg = json.loads(f.read_text(encoding="utf-8"))["segment"]
                    raw = state.read_raw()
                    for i, s in enumerate(raw["segments"]):
                        if s.get("id") == sid:
                            seg["id"] = sid
                            raw["segments"][i] = seg
                            break
                    else:
                        return self._error("段不存在")
                    state.write_raw(raw, snapshot=True)
                    return self._json({"restored": name})
                if path == "/api/history/restore":
                    f = state.root / ".history" / Path(body.get("name", "")).name
                    if not f.is_file():
                        return self._error("历史版本不存在")
                    data = json.loads(f.read_text(encoding="utf-8"))
                    state.write_raw(data, snapshot=True)
                    return self._json({"restored": f.name})
                if path == "/api/llm":
                    from .. import llm
                    try:
                        if body.get("task") == "keywords":
                            return self._json({"keywords": llm.keywords(body.get("text", ""))})
                        if body.get("task") == "translate":
                            return self._json({"text": llm.translate_query(body.get("text", ""))})
                        if body.get("task") == "label":
                            return self._json({"text": llm.chapter_label(body.get("text", ""), q.get("lang") or "en")})
                        return self._json({"text": llm.chat(body.get("prompt", ""), system=body.get("system", ""))})
                    except llm.LlmError as e:
                        return self._error(str(e))
                if path == "/api/tts":
                    return self.tts(body.get("id"), q.get("lang"))
                if path == "/api/research/analyze":
                    from ..research import analyze, youtube as yt
                    env.load_dotenv(state.root)
                    topic = (body.get("q") or "").strip()
                    vids = yt.search(state.root, topic, 20)
                    prompt = analyze.build_prompt(topic, vids, body.get("positioning", ""), lang=q.get("lang") or "zh")
                    if body.get("prompt_only"):
                        return self._json({"prompt": prompt})
                    from ..browser import BrowserError, chat
                    lines: list[str] = []
                    try:
                        text = chat.ask(body.get("site", "deepseek"), prompt, timeout=240, log=lines.append)
                    except BrowserError as e:
                        return self._error(str(e), lines=lines, prompt=prompt)
                    return self._json({"result": analyze.parse_answer(text), "raw": text, "lines": lines})
                if path == "/api/chat":
                    from ..browser import BrowserError, chat, login_session
                    if body.get("login"):
                        threading.Thread(target=login_session, args=(body.get("sites"),), daemon=True).start()
                        return self._json({"started": True})
                    lines: list[str] = []
                    try:
                        text = chat.ask(body.get("site", "deepseek"), body.get("prompt", ""), timeout=float(body.get("timeout", 240)), log=lines.append)
                    except BrowserError as e:
                        return self._error(str(e), lines=lines)
                    return self._json({"text": text, "lines": lines})
                if path == "/api/voice/design":
                    from ..tts import voice_design, voxcpm
                    is_voxcpm = body.get("provider") == "voxcpm"
                    mod = voxcpm if is_voxcpm else voice_design
                    env.load_dotenv(state.root)
                    out_dir = state.build_dir(q.get("lang")) / "ui" / "voice_design"
                    try:
                        # voxcpm has no fast "preview" mode — every candidate is a full, slow local
                        # generation (minutes on CPU), so default to 1 instead of ElevenLabs' 3.
                        kwargs = {"n": int(body["n"])} if is_voxcpm and body.get("n") else ({"n": 1} if is_voxcpm else {})
                        previews = mod.design(body.get("desc", ""), body.get("text"), out_dir, **kwargs)
                    except RuntimeError as e:
                        return self._error(str(e))
                    return self._json({"previews": [{"id": p["generated_voice_id"], "audio": state.rel(p["audio"])} for p in previews]})
                if path == "/api/voice/keep":
                    from ..tts import voice_design, voxcpm
                    mod = voxcpm if body.get("provider") == "voxcpm" else voice_design
                    env.load_dotenv(state.root)
                    try:
                        vid = mod.keep(body["id"], body.get("name") or "vidforge narrator", body.get("desc", ""))
                    except RuntimeError as e:
                        return self._error(str(e))
                    return self._json({"voice_id": vid})
                if path == "/api/voices/preview":
                    return self.voice_preview(body.get("voice"), body.get("text"), body.get("provider", "edge"), q.get("lang"))
                if path == "/api/script/split":
                    segs = script_parser.parse(body.get("text", ""))
                    lang = body.get("lang") or (state.read_raw().get("language", "en") if state.has_project else "en")
                    return self._json({"segments": segs, "issues": script_parser.language_issues(segs, lang)})
                if path == "/api/assets/fetch":
                    return self.fetch_candidate(body.get("candidate"), bool(body.get("force")))
                if path == "/api/assets/upload":
                    return self.upload_asset(body)
                if path == "/api/me/upload":
                    from .. import me
                    lib = me.MeLibrary(me.library_dir(state.root))
                    name = re.sub(r"[^\w\-. \u4e00-\u9fff]+", "_", body.get("name", "take.mp4"))
                    data = base64.b64decode(body.get("data_b64", ""))
                    if not data:
                        return self._error("empty file")
                    dest = lib.folder / name
                    lib.folder.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    try:
                        ffmpeg.duration(dest)
                    except ffmpeg.FfmpegError as e:
                        dest.unlink(missing_ok=True)
                        return self._error(f"不是可读的视频：{e}")
                    lib.scan()
                    if body.get("tags") is not None:
                        lib.set_tags(dest.name, [t.strip() for t in str(body["tags"]).replace("，", ",").split(",") if t.strip()], body.get("talking"))
                    return self._json({"name": dest.name, "items": lib.items()})
                if path == "/api/me/tags":
                    from .. import me
                    lib = me.MeLibrary(me.library_dir(state.root))
                    lib.set_tags(body["name"], body.get("tags", []), body.get("talking"))
                    return self._json({"items": lib.items()})
                if path == "/api/build":
                    burn = {"1": True, "0": False}.get(q.get("burn", ""), None)
                    ok = state.start_build(q.get("lang") or None, burn)
                    return self._json({"started": ok}) if ok else self._error("a build is already running", HTTPStatus.CONFLICT)
                if path == "/api/preview":
                    p = state.load(q.get("lang"))
                    out, dur = pipeline.preview_segment(p, body.get("id"))
                    return self._json({"video": state.rel(out), "duration": dur, "stamp": time.time()})
                if path == "/api/autofill":
                    return self.autofill(q.get("lang"), body)
                if path == "/api/shutdown":              # a newer launcher replacing this (older) copy
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return self._json({"bye": True})
                if path == "/api/build/cancel":
                    pipeline.cancel()
                    return self._json({"cancelling": state.build["state"] == "running"})
                if path == "/api/upload":
                    from ..upload import youtube
                    lines: list[str] = []
                    p = state.load(q.get("lang"))
                    env.load_dotenv(state.root)
                    try:
                        st = youtube.upload(p, log=lines.append)
                    except youtube.YouTubeError as e:
                        return self._error(str(e), lines=lines)
                    return self._json({"lines": lines, **st})
                return self._error("not found", HTTPStatus.NOT_FOUND)
            except proj.ProjectError as e:
                return self._error(f"project.json: {e}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

        # -- views --------------------------------------------------------------------
        def project_view(self, lang: str | None) -> dict:
            raw = state.read_raw()
            base = raw.get("language", "en")
            langs = [base] + sorted((raw.get("variants") or {}).keys())
            lang = lang or base
            bd = state.build_dir(lang)
            issues = None
            resolved: dict[str, dict] = {}
            try:
                try:
                    p = state.load(lang)
                except proj.ProjectError as e:
                    issues = str(e)
                    p = state.load(base)
                from ..tts import get_provider
                from ..assets import Library
                prov = get_provider(p.tts.provider, rate=p.rate, config=p.tts.__dict__)
                lib = Library(state.root)
                for s in p.segments:
                    audio = bd / "audio" / f"{pipeline._safe(s.id)}.mp3"
                    meta = audio.with_suffix(".json")
                    fresh, dur = False, None
                    if audio.exists() and meta.exists():
                        try:
                            key = f"{prov.name}:{prov.cache_key(s.text, s.voice or p.voice)}"
                            fresh = json.loads(meta.read_text(encoding="utf-8")).get("key") == key
                            dur = ffmpeg.duration(audio)
                        except Exception:  # noqa: BLE001
                            pass
                    need = (dur if dur else estimate_seconds(s.text)) + s.pause_after
                    clips = []
                    fixed_total = 0.0
                    for i, c in enumerate(s.clips):
                        if c.needs_asset and c.source:            # auto-picked on an earlier build? show it
                            prov_name, _, query = c.source.partition(":")
                            prov_name = {"wikimedia": "commons"}.get(prov_name, prov_name)
                            picked = lib.pick(f"{prov_name}:{c.source_kind}:{query}")
                            if picked is not None:
                                if c.source_kind == "video":
                                    c.video = picked
                                else:
                                    c.image = picked
                        nat = None
                        if c.video is not None and c.remotion is None:
                            nat = c.slice_length or None
                        elif c.image is not None:
                            nat = c.duration
                        if nat:
                            fixed_total += nat
                        rel_path = state.rel(c.video or c.image) if (c.video or c.image) else None
                        clips.append({
                            "kind": "me" if c.me else ("remotion" if c.remotion else ("video" if c.is_video else "image")),
                            "me": c.me,
                            "path": rel_path,
                            "warning": lib.warning(rel_path) if rel_path else None,
                            "checking": bool(rel_path) and (rel_path in state.checks or rel_path == state.check_current),
                            "source": c.source, "in": c.in_, "out": c.out, "duration": c.duration, "motion": c.motion,
                            "remotion": c.remotion.composition if c.remotion else None,
                            "natural": nat, "index": i,
                        })
                    overlays = [{"kind": "avatar" if o.avatar else ("video" if o.video else "image"),
                                 "path": state.rel(o.video or o.image) if (o.video or o.image) else None,
                                 "at": o.at, "duration": o.duration, "position": o.position, "size": o.size, "animate": o.animate} for o in s.overlays]
                    resolved[s.id] = {
                        "text": s.text, "label": s.label, "clips": clips, "overlays": overlays,
                        "audio": state.rel(audio) if audio.exists() else None, "audio_fresh": fresh,
                        "duration": dur, "need": round(need, 2), "fixed_total": round(fixed_total, 2),
                        "keywords": keywords.suggest(s.text),
                    }
            except proj.ProjectError as e:
                issues = str(e)
            final = bd / "final.mp4"
            return {
                "raw": raw, "lang": lang, "base_lang": base, "langs": langs, "issues": issues, "resolved": resolved,
                "build_dir": state.rel(bd) if bd.exists() else bd.name, "root": str(state.root),
                "outputs": {
                    "final": state.rel(final) if final.exists() else None,
                    "final_mtime": final.stat().st_mtime if final.exists() else None,
                    "srt": state.rel(bd / "final.srt") if (bd / "final.srt").exists() else None,
                    "thumbnail": state.rel(bd / "thumbnail.jpg") if (bd / "thumbnail.jpg").exists() else None,
                    "credits": (bd / "credits.txt").read_text(encoding="utf-8") if (bd / "credits.txt").exists() else None,
                    "timeline": json.loads((bd / "timeline.json").read_text(encoding="utf-8")) if (bd / "timeline.json").exists() else None,
                    "youtube": json.loads((bd / "youtube.json").read_text(encoding="utf-8")) if (bd / "youtube.json").exists() else None,
                },
            }

        def status_view(self) -> dict:
            b = state.build
            elapsed = (b["finished"] or time.time()) - b["started"] if b["started"] else 0
            pr = pipeline.progress() if b["state"] == "running" else {"percent": 100 if b["state"] == "done" else 0, "phase": b["state"], "done": 0, "total": 0}
            pct = pr["percent"]
            eta = (elapsed / pct * (100 - pct)) if b["state"] == "running" and 5 < pct < 100 else None
            return {**b, "elapsed": elapsed, "progress": pct, "phase": pr["phase"], "eta": round(eta) if eta else None,
                    "segments_done": pr["done"] if pr["phase"] == "render" else None, "segments_total": pr["total"] if pr["phase"] == "render" else None}

        def health(self) -> dict:
            env.load_dotenv(state.root)
            from ..remotion import APP_DIR
            from ..render import pick_encoder
            try:
                ff = ffmpeg.find_binary("ffmpeg"); ff_ok = True
            except ffmpeg.FfmpegError as e:
                ff, ff_ok = str(e), False
            try:
                p = state.load(None); enc = pick_encoder(p)
            except Exception:  # noqa: BLE001
                enc = "?"
            from ..render import available_encoders
            hw = [e for e in ("h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox") if e in available_encoders()]
            return {
                "ffmpeg": {"ok": ff_ok, "path": ff}, "encoder": enc, "encoders": ["libx264", *hw],
                "node": bool(shutil.which("node")), "remotion": (APP_DIR / "node_modules").exists(),
                "stamp": STAMP,
                "keys": {k: bool(os.environ.get(k)) for k in env.KEYS},
                "youtube_secret": (Path.home() / ".vidforge" / "client_secret.json").exists()
                                  or bool(os.environ.get("YOUTUBE_CLIENT_SECRET")),
                "cpus": os.cpu_count(),
                "llm": __import__("vidforge.llm", fromlist=["available"]).available(),
            }

        def autofill(self, lang: str | None, body: dict):
            """Give segments a first picture (or video clip) right now, not at render time.

            body: source (any provider the search tab offers), kind (image|video), overwrite (redo
            segments that already have a real file too), resolve (default True: search + download so
            the storyboard shows a real thumbnail), vision (look at each candidate), sync (tests).

            A segment counts as needing a picture when it has no clips at all *or* only unresolved
            "provider:query" specs — earlier versions wrote those specs without downloading anything,
            so a project full of them looked "done" while autofill reported 0 segments to fill and
            the build would later fail on every one of them.
            """
            if state.autofill["state"] == "running":
                return self._error("自动配图正在进行中")
            env.load_dotenv(state.root)
            from ..assets import Library
            has_stock = os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY")
            kind = "video" if body.get("kind") == "video" else "image"
            default_source = ("archive" if kind == "video" and not has_stock else
                              "pexels" if os.environ.get("PEXELS_API_KEY") else
                              "pixabay" if os.environ.get("PIXABAY_API_KEY") else "commons")
            source = body.get("source") or (default_source if kind == "video" or has_stock else "commons")
            overwrite = bool(body.get("overwrite"))
            resolve = body.get("resolve", True)
            vision = body.get("vision", True)          # ~1 min per picture on a CPU-only machine: can be turned off
            site = (body.get("site") or "").strip()    # browser AI for the search phrases; "" = local model
            topic_fallback = body.get("topic_fallback", True)
            raw = state.read_raw()
            base = raw.get("language", "en")
            lib = Library(state.root)

            def unresolved(seg: dict) -> bool:
                """Only "provider:query" specs, none of which has a downloaded file yet."""
                clips = seg.get("clips") or []
                if not clips:
                    return True
                for c in clips:
                    for k in ("image", "video"):
                        v = c.get(k)
                        if not isinstance(v, str):
                            continue
                        if not v.startswith(proj.ASSET_PREFIXES):
                            return False                     # a real file (or me/remotion clip)
                        prov, _, query = v.partition(":")
                        if lib.pick(f"{'commons' if prov == 'wikimedia' else prov}:{k}:{query}"):
                            return False                     # spec already resolved to a file
                return True

            pending = []
            for seg in raw["segments"]:
                if seg.get("remotion") or any(k in seg for k in ("image", "video")):
                    continue
                if not overwrite and not unresolved(seg):
                    continue
                text = seg.get("text" if not lang or lang == base else f"text_{lang}") or seg.get("text") or ""
                if text.strip():
                    pending.append((seg, text))
            state.autofill = {"state": "running", "done": 0, "total": len(pending), "lines": [], "result": None}
            log = state.autofill["lines"].append

            def run():
                from .. import llm
                from ..assets import AssetError, pick_for_spec
                phrases: dict[str, str] = {}
                used_llm = False
                title = raw.get("title", "")
                items = {s["id"]: t for s, t in pending}
                if pending and site:
                    # a full-size model in the user's browser writes far better phrases than a 3B
                    # local one, which starts echoing the narration on abstract paragraphs
                    from ..browser import BrowserError, chat
                    try:
                        log(f"正在 {site} 里生成搜索词（一次提问，通常 30–120 秒）…")
                        answer = chat.ask(site, llm.keywords_prompt(items, topic=title), timeout=300, log=log)
                        phrases = llm.parse_keywords_answer(answer, items)
                        used_llm = bool(phrases)
                        log(f"{site} 给出 {len(phrases)} 段搜索词")
                    except BrowserError as e:
                        log(f"浏览器 AI 不可用，改用本地模型：{e}")
                if pending and not phrases and llm.available():
                    try:
                        phrases = llm.keywords_batch(items, topic=title)
                        used_llm = bool(phrases)
                        log(f"本地模型给出 {len(phrases)} 段搜索词")
                    except llm.LlmError as e:
                        log(f"本地模型不可用，改用启发式关键词：{e}")
                # Abstract narration ("这里有一个容易被误解的问题") has no picture of its own. Rather
                # than leave every such segment empty, fall back to the video's own subject — generic
                # but never wrong — and report which segments got one so they can be reviewed.
                topic_pool: list[str] = []
                if topic_fallback and title and llm.available():
                    sample = pending[0][1] if pending else ""
                    topic_pool = llm.topic_queries(title, sample)
                    if topic_pool:
                        log("没有具体画面的段落将回退到主题素材：" + "、".join(topic_pool))
                # if the chosen source has nothing, try the other key-less ones of the same kind
                # before giving up (a Commons miss is often an Openverse/Archive hit)
                backups = (["archive", "pexels" if os.environ.get("PEXELS_API_KEY") else None,
                            "pixabay" if os.environ.get("PIXABAY_API_KEY") else None] if kind == "video" else
                           ["commons", "openverse", "archive",
                            "pexels" if os.environ.get("PEXELS_API_KEY") else None,
                            "pixabay" if os.environ.get("PIXABAY_API_KEY") else None])
                # browser/unknown-licence sources are only used when explicitly chosen, never as a fallback
                providers = list(dict.fromkeys([p for p in [source] + backups if p]))
                failed: list[dict] = []
                resolved = 0
                generic: list[str] = []
                seen_queries: set[str] = set()
                for seg, text in pending:
                    query = phrases.get(seg["id"]) or ""
                    if not query:
                        heuristic = " ".join(keywords.suggest(text, 2))
                        if heuristic and any("一" <= ch <= "鿿" for ch in heuristic) and llm.available():
                            try:                                   # archives answer English, not 中文
                                heuristic = llm.translate_query(heuristic) or ""
                            except llm.LlmError:
                                heuristic = ""
                        query = llm._clean_phrase(heuristic) or ""
                    if not query and topic_pool:
                        query = topic_pool[len(generic) % len(topic_pool)]   # rotate: not the same picture每段
                        generic.append(seg["id"])
                    if not query:
                        failed.append({"id": seg["id"], "query": "(没有可搜索的关键词)"})
                        seg["clips"] = []
                        state.autofill["done"] += 1
                        continue
                    # several segments often land on one query ("Qin State"); without a per-segment
                    # slot in the pick memory they would all show the identical file
                    repeat = query in seen_queries
                    seen_queries.add(query)
                    clip = {kind: f"{source}:{query}", "motion": "zoom_in"} if kind == "image" else {kind: f"{source}:{query}"}
                    if resolve:
                        need = estimate_seconds(text) if kind == "video" else 0.0
                        for prov in providers:
                            try:
                                dest = pick_for_spec(state.root, lib, prov, kind, query, need=need,
                                                     strict=True, log=log, vision=vision,
                                                     unique_key=seg["id"] if (repeat or seg["id"] in generic) else None)
                                clip[kind] = f"{prov}:{query}"
                                resolved += 1
                                log(f"{seg['id']}: {prov} '{query}' -> {dest.name}")
                                break
                            except AssetError as e:
                                log(f"{seg['id']}: {e}")
                            except Exception as e:  # noqa: BLE001  (network, provider quirks) — keep going
                                log(f"{seg['id']}: {prov} 出错 {e}")
                        else:
                            failed.append({"id": seg["id"], "query": query})
                            clip = None                      # nothing accurate: leave the slot empty, no spec either
                    seg["clips"] = [clip] if clip else []
                    for k in ("image", "video"):
                        seg.pop(k, None)
                    state.autofill["done"] += 1
                # the user may have edited text meanwhile: re-read and apply only our clip changes
                cur = state.read_raw()
                by_id = {s["id"]: s for s, _ in pending}
                for seg in cur["segments"]:
                    if seg["id"] in by_id:
                        seg["clips"] = by_id[seg["id"]]["clips"]
                        for k in ("image", "video"):
                            seg.pop(k, None)
                state.write_raw(cur, snapshot=True)
                state.autofill["result"] = {"filled": len(pending), "resolved": resolved, "failed": failed,
                                            "source": source, "kind": kind, "llm": used_llm, "site": site,
                                            "generic": generic, "topic_pool": topic_pool,
                                            "vision": llm.vision_model() if vision else None}
                state.autofill["state"] = "done"

            if body.get("sync"):
                run()
                return self._json({"started": True, **state.autofill["result"]})
            threading.Thread(target=run, daemon=True).start()
            return self._json({"started": True, "total": len(pending)})

        def save_project(self, body: dict, snapshot: bool = False):
            data = body.get("raw")
            if not isinstance(data, dict):
                return self._error("raw must be an object")
            tmp = state.project_path.with_suffix(".validate.json")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            try:
                proj.load(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            state.write_raw(data, snapshot=snapshot)
            return self._json({"saved": True, "at": time.time()})

        def voices(self, provider: str, lang: str | None) -> list[dict]:
            """Structured voice list; edge gives locale/gender/personality, others only names."""
            env.load_dotenv(state.root)
            if provider == "edge":
                import asyncio
                import edge_tts
                vs = asyncio.run(edge_tts.list_voices())
                out = []
                for v in vs:
                    loc = v["Locale"]
                    if lang and not loc.lower().startswith(lang.lower()):
                        continue
                    out.append({"name": v["ShortName"], "locale": loc, "gender": v["Gender"],
                                "personalities": (v.get("VoiceTag") or {}).get("VoicePersonalities", []),
                                "friendly": v.get("FriendlyName", "")})
                return sorted(out, key=lambda x: (x["locale"], x["gender"], x["name"]))
            from ..tts import get_provider
            prov = get_provider(provider)
            return [{"name": n.split(" ")[0], "locale": "", "gender": "", "personalities": [d], "friendly": n} for n, d in prov.list_voices(lang)]

        def voice_preview(self, voice: str | None, text: str | None, provider: str, lang: str | None):
            """3-second sample of a voice (cached under build/ui/voices/)."""
            if not voice:
                return self._error("voice required")
            from ..tts import get_provider, synthesize_cached
            p = state.load(lang)
            sample = (text or "").strip() or (p.segments[0].text[:160] if p.segments else "Hello, this is a short sample of my voice.")
            prov = get_provider(provider, rate=p.rate, config={**p.tts.__dict__, "provider": provider})
            out = state.build_dir(lang) / "ui" / "voices" / f"{re.sub(r'[^A-Za-z0-9_-]+', '_', voice)}_{abs(hash(sample)) % 10**8}.mp3"
            out.parent.mkdir(parents=True, exist_ok=True)
            synthesize_cached(prov, sample, voice, out)
            return self._json({"audio": state.rel(out), "duration": ffmpeg.duration(out)})

        def tts(self, seg_id: str | None, lang: str | None):
            if not seg_id:
                return self._error("id required")
            p = state.load(lang)
            audio, dur = pipeline.synthesize_segment(p, seg_id)
            return self._json({"audio": state.rel(audio), "duration": dur, "stamp": time.time()})

        def search(self, q: dict):
            from .. import assets
            env.load_dotenv(state.root)
            source = q.get("source", "pexels")
            kind = q.get("kind", "image")
            query = (q.get("q") or "").strip()
            if not query:
                return self._json({"candidates": []})
            try:
                cands = assets.rank(assets.search(state.root, source, query, kind, int(q.get("page", 1))), query)
            except RuntimeError as e:      # missing key / provider error
                key = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}.get(source)
                return self._error(str(e), needs_key=key if key and not os.environ.get(key) else None)
            return self._json({"candidates": [asdict(c) for c in cands]})

        def fetch_candidate(self, cand: dict | None, force: bool = False):
            """Download a picked search result. Paid-stock / watermark hosts are refused outright (409,
            `force` overrides); with a local vision model the file is then checked in the background
            (~1 min on CPU) and the storyboard shows a warning if it has a watermark or burned-in text."""
            from .. import assets
            if not cand:
                return self._error("candidate required")
            c = assets.Candidate(**{k: v for k, v in cand.items() if k in assets.Candidate.__dataclass_fields__})
            if c.kind == "image" and assets.blocked_host(c.download_url) and not force:
                return self._error("这是付费图库/带水印的预览图，不能用在视频里", HTTPStatus.CONFLICT, rejected="付费图库预览")
            dest = assets.fetch(state.root, c)
            from .. import llm
            checking = c.kind == "image" and bool(llm.vision_model())
            if checking:
                state.enqueue_check(state.rel(dest))
            return self._json({"path": state.rel(dest), "credit": c.credit_line(), "duration": c.duration,
                               "kind": c.kind, "checking": checking})

        def upload_asset(self, body: dict):
            name = re.sub(r"[^A-Za-z0-9_.\-一-鿿]+", "_", body.get("name", "upload"))
            data = base64.b64decode(body.get("data_b64", ""))
            if not data:
                return self._error("empty file")
            dest = state.root / "assets" / "local" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            i = 1
            while dest.exists():
                dest = dest.with_name(f"{Path(name).stem}-{i}{Path(name).suffix}")
                i += 1
            dest.write_bytes(data)
            kind = "video" if dest.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".m4v") else "image"
            try:
                if kind == "video":
                    dur = ffmpeg.duration(dest)
                else:
                    from PIL import Image
                    with Image.open(dest) as im:
                        im.verify()
                    dur = None
            except Exception as e:  # noqa: BLE001 — HEIC, truncated download, wrong extension …
                dest.unlink(missing_ok=True)
                return self._error(f"无法读取 {name}：{e}。支持 JPG/PNG/WebP 和 MP4/MOV；iPhone 的 HEIC 请先转成 JPG。")
            return self._json({"path": state.rel(dest), "kind": kind, "duration": dur})

        def poster(self, seg_id: str, idx: int, lang: str | None):
            p = state.load(lang)
            seg = next((s for s in p.segments if s.id == seg_id), None)
            if seg is None or idx >= len(seg.clips) or seg.clips[idx].video is None:
                return self._error("no video", HTTPStatus.NOT_FOUND)
            c = seg.clips[idx]
            at = c.in_ or 0.0
            out = state.build_dir(lang) / "ui" / f"poster_{pipeline._safe(seg_id)}_{idx}_{c.video.stat().st_size}_{int(at * 10)}.jpg"
            if not out.exists():
                out.parent.mkdir(parents=True, exist_ok=True)
                ffmpeg.run(["-y", "-ss", f"{at + 0.5:.2f}", "-i", str(c.video), "-frames:v", "1", "-vf", "scale=480:-2", str(out)])
            return self._file(out)

    return Handler


class _Server(ThreadingHTTPServer):
    # HTTPServer sets allow_reuse_address = True; on Windows that lets a second process bind the
    # *same* address:port without erroring — so two `vidforge start` launches (e.g. the desktop
    # icon double-clicked twice, or a stale process from hours earlier that never exited) can end
    # up both "LISTENING" on 8765 at once, with requests routed unpredictably between an old
    # process serving stale code and the new one. Disabling it makes a real conflict fail loudly
    # (a normal, expected OSError we handle right below) instead of silently double-binding.
    allow_reuse_address = False


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_spawned: list[subprocess.Popen] = []   # keep Popen handles alive — letting one get garbage
                                         # collected while its process is still running emits a
                                         # ResourceWarning on every spawn; we deliberately never
                                         # wait() on these (they're meant to outlive this call)


def spawn_instance(project_path: Path, timeout: float = 20.0) -> str:
    """Launch a second, independent `vidforge ui` process for `project_path` on a free port, so
    it can render/edit fully in parallel with whatever this instance is doing — the single
    server process here has one build slot and one "current project", by design (see _Server /
    start_build), so real concurrency means a second process, not a second tab of this one.
    Waits for it to actually answer before returning, so the caller can open the URL immediately."""
    import urllib.error
    import urllib.request
    port = _free_port()
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen([sys.executable, "-m", "vidforge.cli", "ui", str(project_path), "--port", str(port), "--no-browser"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=creationflags, close_fds=True)
    _spawned.append(proc)
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{url}api/health", timeout=1.5)
            return url
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    if proc.poll() is None:   # still alive but never answered — don't leave it running unreachable
        proc.terminate()
    raise RuntimeError(f"新实例在 {timeout:.0f} 秒内没有响应（端口 {port}）")


def code_stamp() -> str:
    """Newest mtime across the package's .py/.js files: tells a running server apart from the
    code on disk. A double-clicked launcher used to just re-open a copy started days ago, so
    freshly pulled features answered 404 ("not found") until the user thought to kill it."""
    pkg = Path(__file__).resolve().parent.parent
    latest = 0.0
    for f in pkg.rglob("*"):
        if f.suffix in (".py", ".js", ".css", ".html") and "node_modules" not in f.parts and "react" not in f.parts:
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass
    return str(int(latest))


STAMP = code_stamp()


def _running_health(port: int, timeout: float = 1.5) -> dict | None:
    """/api/health of whatever answers on this port, if it looks like vidforge."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as r:
            data = json.loads(r.read())
        return data if "ffmpeg" in data else None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _port_is_ours(port: int, timeout: float = 1.5) -> bool:
    """Is something that looks like vidforge already answering on this port?"""
    return _running_health(port, timeout) is not None


def _pid_on_port(port: int) -> int | None:
    """PID listening on 127.0.0.1:<port>, via the OS (no psutil dependency)."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
                    return int(parts[4])
        else:
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=10).stdout
            if out.strip():
                return int(out.split()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _wait_gone(port: int, seconds: float = 10.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.25)
        if _running_health(port, timeout=0.5) is None:
            return True
    return False


def _replace_stale(port: int) -> bool:
    """Make room for this (newer) copy when an older vidforge holds the port; True once it is free.

    Why bother: a server keeps the Python it imported at startup but serves ui/static/* from disk
    on every request — so an instance started before an update hands the browser the *new* page
    while still answering the *old* routes, and the user sees "not found" on a feature that is
    right there in the UI. First ask it to quit (POST /api/shutdown); builds older than that
    endpoint can only be ended by terminating the process, which is safe here because /api/health
    already identified it as vidforge."""
    import urllib.request
    h = _running_health(port)
    if not h or h.get("stamp") == STAMP:
        return False
    print(f"[vidforge] 端口 {port} 上的 vidforge 是旧版本（在这次更新之前启动的），正在替换它…")
    try:
        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", data=b"{}",
                                                      headers={"Content-Type": "application/json"}), timeout=3).read()
        if _wait_gone(port):
            return True
    except Exception:  # noqa: BLE001  an old build without /api/shutdown: terminate it instead
        pass
    pid = _pid_on_port(port)
    if pid is None or pid == os.getpid():
        print(f"[vidforge] 没能自动结束它。请手动关掉那个 vidforge 窗口（或结束进程），然后重新启动。")
        return False
    print(f"[vidforge] 旧版本没有退出接口，结束进程 {pid}。")
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[vidforge] 结束进程失败：{e}；请手动关掉那个窗口。")
        return False
    return _wait_gone(port)


def serve(project: str | Path | None, port: int = 8765, open_browser: bool = True) -> None:
    project_path = None
    if project:
        project_path = Path(project).resolve()
        if project_path.is_dir():
            project_path = project_path / "project.json"
        if not project_path.exists():
            raise SystemExit(f"project file not found: {project_path}")
    state = State(project_path)
    requested_port = port
    try:
        httpd = _Server(("127.0.0.1", port), make_handler(state))
    except OSError:
        httpd = None
        if _port_is_ours(port) and _replace_stale(port):
            try:
                httpd = _Server(("127.0.0.1", port), make_handler(state))
            except OSError:
                httpd = None
        if httpd is None and _port_is_ours(port):
            # Another vidforge (same code) is already up and healthy — just point the browser at it
            # instead of erroring or silently spawning a second server that will never get requests.
            url = f"http://127.0.0.1:{port}/"
            print(f"vidforge is already running at {url} — opening that instead of starting another copy.")
            if open_browser:
                webbrowser.open(url)
            return
        if httpd is None:
            for p in range(port + 1, port + 21):    # something else (or a hung/unhealthy process) has the port
                try:
                    httpd = _Server(("127.0.0.1", p), make_handler(state))
                    port = p
                    break
                except OSError:
                    continue
            else:
                raise SystemExit(f"could not find a free port near {requested_port}")
            print(f"port {requested_port} busy (not vidforge); using {port} instead.")
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"vidforge ui · {project_path or 'project picker'}\n  {url}   (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
