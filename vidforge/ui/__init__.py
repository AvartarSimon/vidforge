"""Local web UI: edit segments, proof-listen, fetch/replace visuals, build, watch the result.

    vidforge ui my-video            # http://127.0.0.1:8765, opens the browser

Standard library only (ThreadingHTTPServer + one static page). One project per server;
project.json on disk is the single source of truth — every edit is saved there, so the
CLI and the UI never disagree. Builds run in a background thread; the page polls
/api/build/status for log lines and the finished files.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import ffmpeg, pipeline, project as proj

STATIC = Path(__file__).resolve().parent / "static"


class State:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.root = project_path.parent
        self.lock = threading.Lock()
        self.build = {"state": "idle", "lines": [], "lang": None, "started": None, "finished": None, "error": None}

    # -- project.json ---------------------------------------------------------------
    def read_raw(self) -> dict:
        return json.loads(self.project_path.read_text(encoding="utf-8"))

    def write_raw(self, data: dict) -> None:
        tmp = self.project_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self.project_path)

    def load(self, lang: str | None) -> proj.Project:
        return proj.load(self.project_path, lang=lang or None)

    def base_lang(self) -> str:
        return self.read_raw().get("language", "en")

    def build_dir(self, lang: str | None) -> Path:
        raw = self.read_raw()
        base = raw.get("language", "en")
        if not lang or lang == base:
            return self.root / raw.get("out_dir", "build")
        v = (raw.get("variants") or {}).get(lang) or {}
        return self.root / v.get("out_dir", f"build_{lang}")

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root.resolve()).as_posix()

    # -- build thread -----------------------------------------------------------------
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

        def log_message(self, fmt, *args):  # quiet
            pass

        # -- helpers ----------------------------------------------------------
        def _json(self, obj, status=HTTPStatus.OK):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, msg, status=HTTPStatus.BAD_REQUEST):
            self._json({"error": msg}, status)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

        def _file(self, path: Path, download_name: str | None = None):
            if not path.is_file():
                return self._error("not found", HTTPStatus.NOT_FOUND)
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            size = path.stat().st_size
            rng = self.headers.get("Range")
            start, end = 0, size - 1
            if rng and rng.startswith("bytes="):            # <video>/<audio> seek support
                a, _, b = rng[6:].partition("-")
                start = int(a or 0)
                end = int(b) if b else size - 1
                end = min(end, size - 1)
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            if download_name:
                self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _safe_path(self, rel: str) -> Path | None:
            p = (state.root / urllib.parse.unquote(rel)).resolve()
            try:
                p.relative_to(state.root.resolve())
            except ValueError:
                return None
            return p

        # -- routing ------------------------------------------------------------
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(url.query))
            path = url.path
            try:
                if path == "/" or path == "/index.html":
                    return self._file(STATIC / "index.html")
                if path.startswith("/files/"):
                    p = self._safe_path(path[len("/files/"):])
                    return self._file(p) if p else self._error("forbidden", HTTPStatus.FORBIDDEN)
                if path == "/api/project":
                    return self._json(self.project_view(q.get("lang")))
                if path == "/api/build/status":
                    return self._json(self.status_view())
                if path == "/api/voices":
                    from ..tts import get_provider
                    prov = get_provider(q.get("provider", "edge"))
                    return self._json([{"name": n, "desc": d} for n, d in prov.list_voices(q.get("lang"))])
                if path.startswith("/api/poster/"):
                    return self.poster(path[len("/api/poster/"):], q.get("lang"))
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
                    return self.fetch_asset(body.get("id"), q.get("lang"))
                if path == "/api/assets/upload":
                    return self.upload_asset(body)
                if path == "/api/build":
                    ok = state.start_build(q.get("lang") or None, {"1": True, "0": False}.get(q.get("burn", ""), None))
                    return self._json({"started": ok}) if ok else self._error("a build is already running", HTTPStatus.CONFLICT)
                return self._error("not found", HTTPStatus.NOT_FOUND)
            except proj.ProjectError as e:
                return self._error(f"project.json: {e}")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return self._error(str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

        # -- views ----------------------------------------------------------------
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
                    # e.g. untranslated segments: still show visuals, resolved through the base language
                    issues = str(e)
                    p = state.load(base)
                for s in p.segments:
                    audio = bd / "audio" / f"{pipeline._safe(s.id)}.mp3"
                    meta = audio.with_suffix(".json")
                    fresh = False
                    if audio.exists() and meta.exists():
                        try:
                            from ..tts import get_provider
                            prov = get_provider(p.tts.provider, rate=p.rate, config=p.tts.__dict__)
                            key = f"{prov.name}:{prov.cache_key(s.text, s.voice or p.voice)}"
                            fresh = json.loads(meta.read_text(encoding="utf-8")).get("key") == key
                        except Exception:  # noqa: BLE001
                            fresh = False
                    resolved[s.id] = {
                        "text": s.text, "label": s.label,
                        "image": state.rel(s.image) if s.image else None,
                        "video": state.rel(s.video) if s.video else None,
                        "source": s.source, "remotion": s.remotion.composition if s.remotion else None,
                        "audio": state.rel(audio) if audio.exists() else None, "audio_fresh": fresh,
                        "duration": ffmpeg.duration(audio) if audio.exists() else None,
                    }
            except proj.ProjectError as e:
                issues = str(e)
            final = bd / "final.mp4"
            out = {
                "raw": raw, "lang": lang, "base_lang": base, "langs": langs, "issues": issues, "resolved": resolved,
                "build_dir": state.rel(bd) if bd.exists() else bd.name,
                "outputs": {
                    "final": state.rel(final) if final.exists() else None,
                    "final_mtime": final.stat().st_mtime if final.exists() else None,
                    "srt": state.rel(bd / "final.srt") if (bd / "final.srt").exists() else None,
                    "thumbnail": state.rel(bd / "thumbnail.jpg") if (bd / "thumbnail.jpg").exists() else None,
                    "timeline": json.loads((bd / "timeline.json").read_text(encoding="utf-8")) if (bd / "timeline.json").exists() else None,
                },
                "root": str(state.root),
            }
            return out

        def status_view(self) -> dict:
            b = state.build
            return {**b, "elapsed": (b["finished"] or time.time()) - b["started"] if b["started"] else 0}

        def save_project(self, body: dict):
            data = body.get("raw")
            if not isinstance(data, dict):
                return self._error("raw must be an object")
            # validate before writing: keep the old file if the new one is broken
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

        def fetch_asset(self, seg_id: str | None, lang: str | None):
            from .. import assets
            from ..assets.pexels import Pexels
            p = state.load(lang)
            seg = next((s for s in p.segments if s.id == seg_id), None)
            if seg is None:
                return self._error(f"segment {seg_id} not found")
            if not seg.source:
                return self._error("segment has no pexels: source")
            # forget the previous pick for this query so a re-fetch gets a different result
            px = Pexels(state.root / "assets" / "pexels")
            spec = f"{'video' if seg.source_kind == 'video' else 'photo'}:{seg.source.partition(':')[2]}"
            px.index["by_spec"].pop(spec, None)
            px.save()
            seg.image = seg.video = None
            assets.resolve_all(p, log=lambda *_: None)
            return self._json({"image": state.rel(seg.image) if seg.image else None,
                               "video": state.rel(seg.video) if seg.video else None})

        def upload_asset(self, body: dict):
            name = re.sub(r"[^A-Za-z0-9_.\-一-鿿]+", "_", body.get("name", "upload"))
            data = base64.b64decode(body.get("data_b64", ""))
            if not data:
                return self._error("empty file")
            dest = state.root / "assets" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            i = 1
            while dest.exists():
                dest = dest.with_name(f"{Path(name).stem}-{i}{Path(name).suffix}")
                i += 1
            dest.write_bytes(data)
            return self._json({"path": state.rel(dest)})

        def poster(self, seg_id: str, lang: str | None):
            """A still frame for a video segment's card (cached under build/ui/)."""
            p = state.load(lang)
            seg = next((s for s in p.segments if s.id == seg_id), None)
            if seg is None or seg.video is None:
                return self._error("no video", HTTPStatus.NOT_FOUND)
            out = state.build_dir(lang) / "ui" / f"poster_{pipeline._safe(seg_id)}_{seg.video.stat().st_size}.jpg"
            if not out.exists():
                out.parent.mkdir(parents=True, exist_ok=True)
                ffmpeg.run(["-y", "-ss", "1", "-i", str(seg.video), "-frames:v", "1", "-vf", "scale=480:-2", str(out)])
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
