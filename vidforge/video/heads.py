"""Cover every face in a clip with a picture that follows it.

Why: showing your own footage is the cheapest way to look human next to AI-assembled video, but
plenty of people do not want their face on YouTube. Detect the head in each frame, then paint a
cartoon head / avatar / logo / blurred disc over it, moving and resizing with the real one.

    vidforge video heads cover take.mp4 --image avatar.png -o out.mp4
    vidforge video heads cover take.mp4 --blur -o out.mp4        # no picture: blurred disc

How it works, and what each step is for:

  detect()   OpenCV's YuNet finds faces frame by frame (weights fetched once, 230 KB; set
             VIDFORGE_FACE_MODEL to use your own copy).
  track()    Raw detections flicker: a frame or two with no face, boxes jittering by a few pixels.
             Boxes are matched into tracks by overlap, short gaps are interpolated, and the path
             is smoothed — without this the cover jumps around and looks worse than the face.
  render()   The cover layer is generated as raw RGBA and piped straight into ffmpeg, which
             overlays it in one pass. No PNG sequence on disk, and the audio is copied through.

Needs `pip install opencv-python` (installed on first use, like playwright).
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .. import ffmpeg
from . import VideoToolError

FACE_MODEL_ENV = "VIDFORGE_FACE_MODEL"          # path to a YuNet .onnx, to use your own copy
MODEL_DIR = Path.home() / ".vidforge" / "models"
# OpenCV 5 dropped the bundled Haar cascades from the Python wheel, so YuNet is the detector.
# It is one 230 KB file (stored with git-lfs, hence the media. host) and is markedly steadier
# than Haar was on profiles and low light.
YUNET_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
             "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")


def model_path(log=print) -> Path:
    """The YuNet weights, downloading them once on first use."""
    env = os.environ.get(FACE_MODEL_ENV, "")
    if env and Path(env).is_file():
        return Path(env)
    dest = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
    if dest.is_file() and dest.stat().st_size > 100_000:
        return dest
    import urllib.request
    log("[vidforge] 正在下载人脸检测模型 YuNet（一次性，约 230 KB）…")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = urllib.request.urlopen(YUNET_URL, timeout=120).read()
    except Exception as e:  # noqa: BLE001
        raise VideoToolError(f"下载人脸检测模型失败：{e}。可手动下载后设 {FACE_MODEL_ENV}=<路径>") from None
    if len(data) < 100_000:
        raise VideoToolError(f"下载到的模型文件不完整。可手动下载 {YUNET_URL} 后设 {FACE_MODEL_ENV}=<路径>")
    dest.write_bytes(data)
    return dest


def _detector(cv2, width: int, height: int, log=print):
    return cv2.FaceDetectorYN_create(str(model_path(log)), "", (width, height), 0.6, 0.3, 5000)


def _cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        pass
    print("[vidforge] 正在安装 opencv-python（一次性，约 40 MB）…")
    if subprocess.call([sys.executable, "-m", "pip", "install", "--quiet", "opencv-python"]) == 0:
        try:
            import cv2
            return cv2
        except ImportError:
            pass
    raise VideoToolError("人脸检测需要 opencv：请运行 python -m pip install opencv-python")


@dataclass
class Box:
    """A face in one frame, in pixels."""
    frame: int
    x: float
    y: float
    w: float
    h: float
    score: float = 1.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Track:
    """One face followed across frames: frame index -> box."""
    boxes: dict[int, Box] = field(default_factory=dict)

    @property
    def first(self) -> int:
        return min(self.boxes)

    @property
    def last(self) -> int:
        return max(self.boxes)


def _iou(a: Box, b: Box) -> float:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def detect(video: Path, every: int = 1, min_size: float = 0.04, min_score: float = 0.85,
           log=print) -> tuple[list[Box], dict]:
    """Faces per frame, plus {width, height, fps, frames} of the clip.

    `every` > 1 checks only every Nth frame (detection is the slow part; the gaps are filled in
    by track()). `min_size` ignores faces smaller than this fraction of the frame height and
    `min_score` those the detector is unsure about — on a head turned side-on YuNet also reports
    a weak box over the ear, and covering that is worse than missing it."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise VideoToolError(f"打不开视频：{video}")
    meta = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
        "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
    }
    yunet = _detector(cv2, meta["width"], meta["height"], log)
    min_px = int(meta["height"] * min_size)
    out: list[Box] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % max(1, every) == 0:
            _, faces = yunet.detect(frame)
            keep: list[Box] = []
            for f in (faces if faces is not None else []):
                x, y, w, h = (float(v) for v in f[:4])
                score = float(f[14]) if len(f) > 14 else 1.0
                if h < min_px or score < min_score:
                    continue
                b = Box(i, x, y, w, h, score)
                # the detector returns several boxes for one face; without this they become two
                # tracks and the clip ends up with two covers side by side on one head
                if any(_iou(b, k) > 0.3 for k in keep):
                    continue
                keep.append(b)
            out.extend(keep)
        i += 1
    cap.release()
    meta["frames"] = meta["frames"] or i
    log(f"  {len(out)} 个人脸框 / {i} 帧")
    return out, meta


def track(boxes: list[Box], frames: int, max_gap: int = 12, smooth: float = 0.35) -> list[Track]:
    """Group per-frame detections into tracks, fill short gaps, smooth the path.

    max_gap: a face may vanish for this many frames (a turn of the head, a blink of the detector)
    and still count as the same face — the cover holds its place instead of flashing off."""
    by_frame: dict[int, list[Box]] = {}
    for b in boxes:
        by_frame.setdefault(b.frame, []).append(b)

    tracks: list[Track] = []
    for f in sorted(by_frame):
        for b in by_frame[f]:
            best, best_iou = None, 0.0
            for t in tracks:
                if f - t.last > max_gap:
                    continue
                score = _iou(t.boxes[t.last], b)
                if score > best_iou:
                    best, best_iou = t, score
            if best is not None and best_iou > 0.2:
                best.boxes[f] = b
            else:
                tracks.append(Track({f: b}))

    out: list[Track] = []
    for t in tracks:
        if len(t.boxes) < 3:
            continue                                  # a couple of stray hits, not a face
        known = sorted(t.boxes)
        filled: dict[int, Box] = {}
        for a, b in zip(known, known[1:]):
            filled[a] = t.boxes[a]
            for f in range(a + 1, b):                 # linear interpolation across the gap
                k = (f - a) / (b - a)
                p, q = t.boxes[a], t.boxes[b]
                filled[f] = Box(f, p.x + (q.x - p.x) * k, p.y + (q.y - p.y) * k,
                                p.w + (q.w - p.w) * k, p.h + (q.h - p.h) * k)
        filled[known[-1]] = t.boxes[known[-1]]

        # exponential smoothing, forwards then backwards, so the cover does not lag the face
        for seq in (sorted(filled), sorted(filled, reverse=True)):
            prev: Box | None = None
            for f in seq:
                cur = filled[f]
                if prev is not None:
                    a = smooth
                    cur = Box(f, prev.x + (cur.x - prev.x) * a, prev.y + (cur.y - prev.y) * a,
                              prev.w + (cur.w - prev.w) * a, prev.h + (cur.h - prev.h) * a)
                    filled[f] = cur
                prev = cur
        out.append(Track(filled))
    return [t for t in out if t.last < frames + 1]


def _cover_image(path: Path, size: int):
    from PIL import Image
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def _blur_disc(size: int):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((0, 0, size - 1, size - 1), fill=(24, 24, 28, 235))
    return img


def cover(video: Path, out: Path, image: Path | None = None, scale: float = 1.5,
          y_offset: float = -0.08, every: int = 1, min_score: float = 0.85, log=print) -> dict:
    """Write `out`: the same clip with every tracked face covered.

    scale:    cover size as a multiple of the detected face box (a face box is the face, a head
              with hair is bigger, so the default overshoots on purpose).
    y_offset: move the cover up by this fraction of its size — detectors box the face, while a
              head sits higher.
    """
    from PIL import Image
    video, out = Path(video), Path(out)
    boxes, meta = detect(video, every=every, min_score=min_score, log=log)
    tracks = track(boxes, meta["frames"])
    log(f"  {len(tracks)} 张脸被跟踪")
    if not tracks:
        raise VideoToolError("没有检测到人脸。正面对镜头的画面最容易识别；也可以设 VIDFORGE_FACE_MODEL 用 YuNet。")

    w, h, fps = meta["width"], meta["height"], meta["fps"]
    cmd = [ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
           "-i", str(video),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
           "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto[v]",
           "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    blank = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cache: dict[int, object] = {}
    covered = 0
    try:
        for f in range(meta["frames"]):
            layer = None
            for t in tracks:
                b = t.boxes.get(f)
                if b is None:
                    continue
                size = max(8, int(round(max(b.w, b.h) * scale)))
                art = cache.get(size)
                if art is None:
                    art = _cover_image(image, size) if image else _blur_disc(size)
                    cache[size] = art
                    if len(cache) > 64:
                        cache.pop(next(iter(cache)))
                if layer is None:
                    layer = blank.copy()
                layer.alpha_composite(art, (int(round(b.cx - art.width / 2)),
                                            int(round(b.cy - art.height / 2 + art.height * y_offset))))
            if layer is not None:
                covered += 1
            proc.stdin.write((layer or blank).tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise VideoToolError(f"ffmpeg 失败（退出码 {proc.returncode}）")
    log(f"  {covered}/{meta['frames']} 帧盖住了人脸 -> {out.name}")
    return {"out": str(out), "faces": len(tracks), "frames": meta["frames"], "covered": covered}


def preview_frame(video: Path, out_png: Path, at: float = 0.0, min_score: float = 0.85) -> Path:
    """One frame with red boxes where faces were found — to check detection before a full render."""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise VideoToolError(f"打不开视频：{video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(at * fps)))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise VideoToolError("读不到这一帧")
    h, w = frame.shape[:2]
    _, faces = _detector(cv2, w, h).detect(frame)
    n = 0
    for f in (faces if faces is not None else []):
        x, y, w_, h_ = (int(v) for v in f[:4])
        score = float(f[14]) if len(f) > 14 else 1.0
        strong = score >= min_score
        cv2.rectangle(frame, (x, y), (x + w_, y + h_),
                      (0, 0, 255) if strong else (120, 120, 120), max(2, h // 300))
        cv2.putText(frame, f"{score:.2f}", (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.4, h / 1200), (0, 0, 255) if strong else (120, 120, 120), 2)
        n += 1 if strong else 0
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_png), frame)
    return out_png


def estimate_minutes(frames: int) -> float:
    """Rough wall-clock estimate, for telling the user before they start (measured ~120 fps
    detection on a laptop CPU at 1080p with the Haar cascade)."""
    return math.ceil(frames / 120 / 60 * 10) / 10
