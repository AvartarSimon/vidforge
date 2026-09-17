"""Lip-sync a speaking take of you to the narration audio.

Providers (set `lipsync.provider` in project.json or LIPSYNC_PROVIDER):
  synclabs  — sync.so API (model lipsync-2). Needs SYNC_API_KEY. The API takes URLs, so the
              take and the audio are uploaded to a temporary host first (tmpfiles.org, files
              expire after ~1 h). Your face video passes through a third-party host — say no
              to that by using `musetalk` instead.                                   ⚠ untested here
  musetalk  — a local command you provide (LIPSYNC_CMD), e.g. a MuseTalk / LatentSync wrapper:
              placeholders {video} {audio} {out}. Needs an NVIDIA GPU in practice.     ⚠ untested here
  none      — no lip-sync: the take is used muted (mouth will not match; only for silent takes)

Output: mp4 with the narration baked in, exactly the narration length (looped/trimmed take).
Results are cached by (take, audio) hash under build/lipsync/.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path

from . import ffmpeg


class LipsyncError(RuntimeError):
    pass


def _key(video: Path, audio: Path) -> str:
    return hashlib.sha1(f"{video.name}:{video.stat().st_size}:{audio.name}:{audio.stat().st_size}:{int(audio.stat().st_mtime)}".encode()).hexdigest()[:12]


def prepare_take(video: Path, seconds: float, out: Path) -> Path:
    """Loop/trim the take to the narration length, muted, so every provider gets a matching input."""
    ffmpeg.run(["-y", "-stream_loop", "-1", "-i", str(video), "-an", "-t", f"{seconds:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)])
    return out


def sync(video: Path, audio: Path, seconds: float, out_dir: Path, provider: str | None = None, log=print) -> Path:
    provider = provider or os.environ.get("LIPSYNC_PROVIDER", "none")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video.stem}_{_key(video, audio)}_{provider}.mp4"
    if out.exists():
        return out
    take = prepare_take(video, seconds, out_dir / f"{video.stem}_{_key(video, audio)}_take.mp4")
    if provider == "none":
        return take
    if provider == "synclabs":
        return _synclabs(take, audio, out, log)
    if provider == "musetalk":
        return _local_cmd(take, audio, out, log)
    raise LipsyncError(f"unknown lipsync provider '{provider}'")


def _tmp_upload(path: Path) -> str:
    """tmpfiles.org: anonymous, ~1 h retention; returns a direct-download URL."""
    boundary = "----vidforge" + hashlib.sha1(str(time.time()).encode()).hexdigest()[:10]
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request("https://tmpfiles.org/api/v1/upload", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "vidforge"})
    with urllib.request.urlopen(req, timeout=300) as r:
        url = json.loads(r.read())["data"]["url"]
    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def _synclabs(take: Path, audio: Path, out: Path, log) -> Path:
    key = os.environ.get("SYNC_API_KEY", "").strip()
    if not key:
        raise LipsyncError("Sync Labs 需要 SYNC_API_KEY（https://sync.so）")
    log("[lipsync] uploading take + audio to a temporary host …")
    v_url, a_url = _tmp_upload(take), _tmp_upload(audio)
    body = {"model": "lipsync-2", "input": [{"type": "video", "url": v_url}, {"type": "audio", "url": a_url}],
            "options": {"sync_mode": "bounce", "output_format": "mp4"}}
    req = urllib.request.Request("https://api.sync.so/v2/generate", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        job = json.loads(r.read())
    jid = job.get("id")
    log(f"[lipsync] sync.so job {jid} …")
    for _ in range(180):
        time.sleep(5)
        with urllib.request.urlopen(urllib.request.Request(f"https://api.sync.so/v2/generate/{jid}", headers={"x-api-key": key}), timeout=60) as r:
            st = json.loads(r.read())
        if st.get("status") == "COMPLETED":
            urllib.request.urlretrieve(st["outputUrl"], out)
            return out
        if st.get("status") in ("FAILED", "REJECTED", "CANCELED"):
            raise LipsyncError(f"sync.so {st.get('status')}: {st.get('error')}")
    raise LipsyncError("sync.so timed out after 15 minutes")


def _local_cmd(take: Path, audio: Path, out: Path, log) -> Path:
    tmpl = os.environ.get("LIPSYNC_CMD", "").strip()
    if not tmpl:
        raise LipsyncError("本地口型同步需要 LIPSYNC_CMD，例如 MuseTalk 的封装脚本：python musetalk.py --video {video} --audio {audio} --out {out}")
    cmd = [part.format(video=str(take), audio=str(audio), out=str(out)) for part in shlex.split(tmpl, posix=os.name != "nt")]
    log(f"[lipsync] {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    if r.returncode != 0 or not out.exists():
        raise LipsyncError(f"lipsync command failed:\n{(r.stderr or r.stdout)[-2000:]}")
    return out
