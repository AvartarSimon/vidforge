"""Turn a still picture into a head that talks along with an audio file.

Two ways, both local and free:

  cmd     Run an open-source photo-driven model you installed yourself (SadTalker, EchoMimic,
          Hallo, LivePortrait, …) through a command template you set once:

              setx PHOTO_TALK_CMD "python C:\\tools\\SadTalker\\inference.py --source_image {image} --driven_audio {audio} --result_dir {outdir} --still --preprocess full"

          Placeholders: {image} {audio} {out} {outdir}. If the tool writes a file of its own
          choosing into {outdir}, the newest mp4 there is taken as the result.
          These models move the head and shoulders and lip-sync the mouth; they do not produce
          body gestures. All of them want an NVIDIA GPU — on a laptop CPU expect tens of times
          realtime, so drive them per segment, not with a whole narration.

  motion   No model at all: the picture itself is animated from the loudness of the audio — the
           mouth area opens and closes, the head nods and sways slightly, eyes blink. It is a
           puppet, not a lip-sync: syllables are not matched, only speech rhythm. It costs
           nothing, runs anywhere, and at picture-in-picture size (or behind a cartoon filter)
           it reads as "a person talking" where a frozen photo reads as "a slideshow".

Both return an mp4 exactly as long as the audio, which `heads.cover(cover_video=…)` can then
paste onto a tracked head — that is the "my gestures, someone else's face" route.
"""

from __future__ import annotations

import math
import os
import shlex
import subprocess
from pathlib import Path

from .. import ffmpeg
from . import VideoToolError

CMD_ENV = "PHOTO_TALK_CMD"


def available() -> dict:
    """What this machine can do right now, for the UI's status line."""
    return {"cmd": bool(os.environ.get(CMD_ENV, "").strip()), "motion": True}


def head_crop(image: Path, out: Path | None = None, margin: float = 1.9, log=print) -> Path:
    """Crop a photo down to the head, so what gets animated (and later pasted onto a tracked head)
    is a head and not a whole portrait. Returns the original if no face is found."""
    from PIL import Image
    from .heads import _cv2, _detector
    cv2 = _cv2()
    img = Image.open(image).convert("RGB")
    import numpy as np
    arr = np.array(img)[:, :, ::-1].copy()                 # PIL RGB -> OpenCV BGR
    h, w = arr.shape[:2]
    _, faces = _detector(cv2, w, h, log).detect(arr)
    if faces is None or not len(faces):
        log("  图片里没检测到人脸，按原图使用（建议自己裁成头部特写）")
        return Path(image)
    f = max(faces, key=lambda f: float(f[2]) * float(f[3]))
    fx, fy, fw, fh = (float(v) for v in f[:4])
    side = max(fw, fh) * margin
    cx, cy = fx + fw / 2, fy + fh / 2 - fh * 0.12         # a head sits a little above its face box
    box = (int(max(0, cx - side / 2)), int(max(0, cy - side / 2)),
           int(min(w, cx + side / 2)), int(min(h, cy + side / 2)))
    out = Path(out or Path(image).with_name(Path(image).stem + "_head.png"))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.crop(box).save(out)
    log(f"  裁出头部 {box[2] - box[0]}x{box[3] - box[1]} -> {out.name}")
    return out


def talk(image: Path, audio: Path, out: Path, provider: str = "motion", fps: int = 25,
         size: int = 512, crop: bool = True, log=print) -> Path:
    if provider not in ("motion", "cmd"):          # check before doing any work
        raise VideoToolError(f"未知的说话头像引擎 '{provider}'（可选：motion | cmd）")
    image, audio, out = Path(image), Path(audio), Path(out)
    if not image.is_file():
        raise VideoToolError(f"找不到图片：{image}")
    if not audio.is_file():
        raise VideoToolError(f"找不到音频：{audio}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if crop:
        image = head_crop(image, out.parent / f"{out.stem}_head.png", log=log)
    if provider == "cmd":
        return _cmd(image, audio, out, log)
    return _motion(image, audio, out, fps=fps, size=size, log=log)


def _cmd(image: Path, audio: Path, out: Path, log) -> Path:
    template = os.environ.get(CMD_ENV, "").strip()
    if not template:
        raise VideoToolError(
            f"没有配置开源模型的命令。装好 SadTalker / EchoMimic / Hallo 之后，把调用命令写进环境变量 "
            f"{CMD_ENV}，用 {{image}} {{audio}} {{out}} {{outdir}} 占位，例如：\n"
            f'  {CMD_ENV}=python D:/SadTalker/inference.py --source_image {{image}} '
            f'--driven_audio {{audio}} --result_dir {{outdir}} --still')
    outdir = out.parent / f"{out.stem}_work"
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = template.format(image=str(image), audio=str(audio), out=str(out), outdir=str(outdir))
    log(f"  运行：{cmd}")
    rc = subprocess.call(shlex.split(cmd) if os.name != "nt" else cmd, shell=(os.name == "nt"))
    if rc != 0:
        raise VideoToolError(f"{CMD_ENV} 退出码 {rc}")
    if out.is_file():
        return out
    made = sorted(outdir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not made:
        raise VideoToolError(f"命令没有产出 mp4（看看 {outdir}）")
    made[-1].replace(out)
    return out


def _motion(image: Path, audio: Path, out: Path, fps: int, size: int, log) -> Path:
    """Animate the picture from the audio's loudness envelope: mouth, nod, sway, blink.

    Drawn with PIL per frame and piped to ffmpeg, the same way heads.cover() composites — no
    frame files on disk. The mouth is a local vertical stretch of the lower face, which is crude
    but reads correctly at the size a presenter inset is actually shown at."""
    from PIL import Image
    from ..avatar import audio_envelope
    seconds = ffmpeg.duration(audio)
    env = audio_envelope(audio, fps, seconds)
    n = len(env)
    src = Image.open(image).convert("RGBA")
    src.thumbnail((size * 2, size * 2), Image.LANCZOS)
    # libx264 + yuv420p needs even dimensions; a face crop is very often odd-sized
    src = src.crop((0, 0, src.width - src.width % 2, src.height - src.height % 2))
    w, h = src.size
    log(f"  {n} 帧 · {seconds:.1f}s · {w}x{h}")

    cmd = [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-i", str(audio), "-shortest",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    mouth_top = int(h * 0.60)          # lower face: everything below this is stretched when open
    try:
        for i, level in enumerate(env):
            t = i / fps
            frame = src.copy()
            # mouth: stretch the lower face down by a few percent of its height
            if level > 0.02:
                grow = 1.0 + 0.09 * level
                lower = src.crop((0, mouth_top, w, h))
                lower = lower.resize((w, max(1, int((h - mouth_top) * grow))), Image.BICUBIC)
                frame.paste(lower, (0, mouth_top))
            # blink: close the eyes for two frames roughly every three seconds
            if i % max(1, int(fps * 3)) in (0, 1):
                band_top, band_h = int(h * 0.34), max(2, int(h * 0.05))
                band = src.crop((0, band_top - band_h, w, band_top))
                frame.paste(band.resize((w, band_h * 2), Image.BICUBIC), (0, band_top - band_h))
            # head: a small nod on loud syllables plus a slow sway, so it is never perfectly still
            dx = int(round(math.sin(t * 1.1) * w * 0.006))
            dy = int(round(math.sin(t * 2.3) * h * 0.004 + level * h * 0.012))
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.paste(frame, (dx, dy))
            try:
                proc.stdin.write(canvas.tobytes())
            except BrokenPipeError:
                break                       # ffmpeg died; its stderr is reported below
    finally:
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read().decode("utf-8", "replace").strip()
        proc.wait()
    if proc.returncode != 0:
        raise VideoToolError(f"ffmpeg 失败（退出码 {proc.returncode}）：{err[:400]}")
    return out
