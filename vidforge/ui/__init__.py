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
import threading
import time
import traceback
import urllib.parse
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import env, ffmpeg, keywords, pipeline, project as proj
from ..tts.silent import estimate_seconds

STATIC = Path(__file__).resolve().parent / "static"


class State:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.root = project_path.parent
        self.lock = threading.Lock()
        self.build = {"state": "idle", "lines": [], "lang": None, "started": None, "finished": None, "error": None}

    def read_raw(self) -> dict:
        return json.loads(self.project_path.read_text(encoding="utf-8"))

    def write_raw(self, data: dict) -> None:
        tmp = self.project_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.project_path)

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
                    return self._json(self.project_view(q.get("lang")))
                if path == "/api/build/status":
                    return self._json(self.status_view())
                if path == "/api/health":
                    return self._json(self.health())
                if path == "/api/voices":
                    from ..tts import get_provider
                    env.load_dotenv(state.root)
                    prov = get_provider(q.get("provider", "edge"))
                    return self._json([{"name": n, "desc": d} for n, d in prov.list_voices(q.get("lang"))])
                if path == "/api/search":
                    return self.search(q)
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
                    return self.save_project(body)
                if path == "/api/tts":
                    return self.tts(body.get("id"), q.get("lang"))
                if path == "/api/assets/fetch":
                    return self.fetch_candidate(body.get("candidate"))
                if path == "/api/assets/upload":
                    return self.upload_asset(body)
                if path == "/api/build":
                    burn = {"1": True, "0": False}.get(q.get("burn", ""), None)
                    ok = state.start_build(q.get("lang") or None, burn)
                    return self._json({"started": ok}) if ok else self._error("a build is already running", HTTPStatus.CONFLICT)
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
                        clips.append({
                            "kind": "remotion" if c.remotion else ("video" if c.is_video else "image"),
                            "path": state.rel(c.video or c.image) if (c.video or c.image) else None,
                            "source": c.source, "in": c.in_, "out": c.out, "duration": c.duration, "motion": c.motion,
                            "remotion": c.remotion.composition if c.remotion else None,
                            "natural": nat, "index": i,
                        })
                    resolved[s.id] = {
                        "text": s.text, "label": s.label, "clips": clips,
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
            return {**b, "elapsed": (b["finished"] or time.time()) - b["started"] if b["started"] else 0}

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
            return {
                "ffmpeg": {"ok": ff_ok, "path": ff}, "encoder": enc,
                "node": bool(shutil.which("node")), "remotion": (APP_DIR / "node_modules").exists(),
                "keys": {k: bool(os.environ.get(k)) for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_API_KEY")},
                "youtube_secret": (Path.home() / ".vidforge" / "client_secret.json").exists()
                                  or bool(os.environ.get("YOUTUBE_CLIENT_SECRET")),
                "cpus": os.cpu_count(),
            }

        def save_project(self, body: dict):
            data = body.get("raw")
            if not isinstance(data, dict):
                return self._error("raw must be an object")
            tmp = state.project_path.with_suffix(".validate.json")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            try:
                proj.load(tmp)
            finally:
                tmp.unlink(missing_ok=True)
            state.write_raw(data)
            return self._json({"saved": True})

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

        def fetch_candidate(self, cand: dict | None):
            from .. import assets
            if not cand:
                return self._error("candidate required")
            c = assets.Candidate(**{k: v for k, v in cand.items() if k in assets.Candidate.__dataclass_fields__})
            dest = assets.fetch(state.root, c)
            return self._json({"path": state.rel(dest), "credit": c.credit_line(), "duration": c.duration,
                               "kind": c.kind})

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
            dur = ffmpeg.duration(dest) if kind == "video" else None
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


def serve(project: str | Path, port: int = 8765, open_browser: bool = True) -> None:
    project_path = Path(project).resolve()
    if project_path.is_dir():
        project_path = project_path / "project.json"
    if not project_path.exists():
        raise SystemExit(f"project file not found: {project_path}")
    state = State(project_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"vidforge ui · {project_path}\n  {url}   (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
