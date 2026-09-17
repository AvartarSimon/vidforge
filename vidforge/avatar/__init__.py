"""The presenter: a talking host video for a segment, driven by that segment's narration.

Providers
  host    — stylised drawn character (Remotion `Host`), mouth driven by the audio envelope.
            Local, free, no disclosure needed: it plainly is a cartoon.  ✅ tested
  heygen  — photoreal digital twin via HeyGen's API (HEYGEN_API_KEY + an avatar you created
            from your own footage). Realistic synthetic person ⇒ YouTube's "altered or synthetic
            content" flag must be set; vidforge does that automatically (see disclosure).  ⚠ untested here

Output: an mp4 exactly as long as the narration (+pause), used as a picture-in-picture overlay.
"""

from __future__ import annotations

import array
import json
import math
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from .. import ffmpeg
from ..project import Project, Segment


class AvatarError(RuntimeError):
    pass


def audio_envelope(audio: Path, fps: int, seconds: float | None = None) -> list[float]:
    """Per-frame loudness 0..1 (RMS, normalised to the 95th percentile, fast attack / soft release)."""
    rate = 16000
    cmd = [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", str(audio), "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"]
    pcm = subprocess.run(cmd, capture_output=True, timeout=600).stdout
    samples = array.array("h"); samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    win = max(1, rate // fps)
    n_frames = math.ceil(len(samples) / win)
    if seconds:
        n_frames = max(n_frames, math.ceil(seconds * fps))
    rms = []
    for i in range(n_frames):
        chunk = samples[i * win:(i + 1) * win]
        rms.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)) if len(chunk) else 0.0)
    if not rms:
        return [0.0]
    ref = sorted(rms)[int(len(rms) * 0.95)] or 1.0
    env, prev = [], 0.0
    for v in rms:
        x = min(1.0, v / ref)
        x = x if x >= prev else prev * 0.55 + x * 0.45          # quick to open, softer to close
        env.append(round(x, 3)); prev = x
    return env


def render_presenter(project: Project, seg: Segment, audio: Path, seconds: float, out_dir: Path, log=print) -> Path:
    prov = project.presenter.provider
    if prov == "host":
        return _host(project, seg, audio, seconds, out_dir, log)
    if prov == "heygen":
        return _heygen(project, seg, audio, seconds, out_dir, log)
    raise AvatarError(f"unknown presenter provider '{prov}'")


def _host(project: Project, seg: Segment, audio: Path, seconds: float, out_dir: Path, log) -> Path:
    from .. import remotion
    w = max(240, round(project.width * project.presenter.size))
    h = round(w * 0.75)
    env = audio_envelope(audio, project.fps, seconds)
    props = {"envelope": env, "style": project.presenter.style, "name": project.presenter.style.get("name")}
    return remotion.render("Host", props, duration=seconds, fps=project.fps, width=w, height=h, out_dir=out_dir, log=log)


def _heygen(project: Project, seg: Segment, audio: Path, seconds: float, out_dir: Path, log) -> Path:
    """HeyGen v2: upload the narration as an asset, generate with the user's avatar, poll, download.
    Endpoints per HeyGen API docs (2025); not exercised here — no account."""
    key = os.environ.get("HEYGEN_API_KEY", "").strip()
    avatar_id = project.presenter.heygen_avatar_id
    if not key or not avatar_id:
        raise AvatarError("HeyGen 需要 HEYGEN_API_KEY（.env）和 presenter.heygen_avatar_id（在 HeyGen 里用你自己的录像创建的 avatar）")
    out = Path(out_dir) / f"heygen_{seg.id}_{int(audio.stat().st_mtime)}.mp4"
    if out.exists():
        return out
    hdr = {"X-Api-Key": key}
    # 1. upload audio
    req = urllib.request.Request("https://upload.heygen.com/v1/asset", data=audio.read_bytes(), method="POST",
                                 headers={**hdr, "Content-Type": "audio/mpeg"})
    asset = json.loads(urllib.request.urlopen(req, timeout=120).read())["data"]["id"]
    # 2. generate
    body = {"video_inputs": [{"character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
                              "voice": {"type": "audio", "audio_asset_id": asset},
                              "background": {"type": "color", "value": project.presenter.style.get("bg", "#0f1115")}}],
            "dimension": {"width": 1280, "height": 720}}
    req = urllib.request.Request("https://api.heygen.com/v2/video/generate", data=json.dumps(body).encode(), method="POST",
                                 headers={**hdr, "Content-Type": "application/json"})
    vid = json.loads(urllib.request.urlopen(req, timeout=120).read())["data"]["video_id"]
    log(f"[heygen] generating {seg.id} …")
    # 3. poll
    for _ in range(120):
        time.sleep(5)
        st = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://api.heygen.com/v1/video_status.get?video_id={vid}", headers=hdr), timeout=60).read())["data"]
        if st.get("status") == "completed":
            urllib.request.urlretrieve(st["video_url"], out)
            return out
        if st.get("status") == "failed":
            raise AvatarError(f"HeyGen failed: {st.get('error')}")
    raise AvatarError("HeyGen timed out after 10 minutes")
