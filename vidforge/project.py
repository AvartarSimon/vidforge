"""project.json schema: dataclasses + loader with validation.

A project is a *type-free* description of one video: metadata, voice, output
format, background music, subtitle style, and an ordered list of segments.
Each segment = the narration text for that segment + one image + a camera move.
Durations are never written by hand — they come from the synthesized audio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "none")


class ProjectError(ValueError):
    pass


@dataclass
class Segment:
    id: str
    text: str
    image: Path                      # absolute after load
    motion: str = "zoom_in"
    pause_after: float = 0.5         # seconds of silence appended after the narration
    voice: str | None = None         # override the project voice for this segment


@dataclass
class Bgm:
    file: Path
    volume_db: float = -18.0
    fade_out: float = 3.0


@dataclass
class SubtitleStyle:
    burn: bool = False               # burn into the video (else only .srt is produced)
    max_chars: int = 42              # per cue line
    font: str = "Arial"
    font_size: int = 22
    margin_v: int = 48


@dataclass
class Project:
    title: str
    segments: list[Segment]
    root: Path                       # directory of project.json; relative paths resolve here
    language: str = "en"
    voice: str = "en-US-AndrewNeural"
    rate: str = "+0%"                # edge-tts rate, e.g. "-5%", "+10%"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    motion_amount: float = 0.15      # zoom factor / pan distance as a fraction of the frame
    supersample: int = 2             # zoompan works on a supersampled frame to avoid jitter
    out_dir: Path = Path("build")
    bgm: Bgm | None = None
    subtitles: SubtitleStyle = field(default_factory=SubtitleStyle)
    thumbnail_text: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def build_dir(self) -> Path:
        return self.out_dir if self.out_dir.is_absolute() else self.root / self.out_dir


def _req(d: dict, key: str, ctx: str) -> Any:
    if key not in d:
        raise ProjectError(f"{ctx}: missing required field '{key}'")
    return d[key]


def load(path: str | Path) -> Project:
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "project.json"
    if not path.exists():
        raise ProjectError(f"project file not found: {path}")
    root = path.parent
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    def resolve(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else (root / q)

    segments: list[Segment] = []
    seen: set[str] = set()
    for i, s in enumerate(_req(data, "segments", "project")):
        ctx = f"segments[{i}]"
        sid = str(_req(s, "id", ctx))
        if sid in seen:
            raise ProjectError(f"{ctx}: duplicate segment id '{sid}'")
        seen.add(sid)
        text = str(_req(s, "text", ctx)).strip()
        if not text:
            raise ProjectError(f"{ctx}: text is empty")
        image = resolve(_req(s, "image", ctx))
        if not image.exists():
            raise ProjectError(f"{ctx}: image not found: {image}")
        motion = s.get("motion", "zoom_in")
        if motion not in MOTIONS:
            raise ProjectError(f"{ctx}: motion '{motion}' not in {MOTIONS}")
        segments.append(Segment(
            id=sid, text=text, image=image, motion=motion,
            pause_after=float(s.get("pause_after", 0.5)),
            voice=s.get("voice"),
        ))
    if not segments:
        raise ProjectError("project has no segments")

    bgm = None
    if data.get("bgm"):
        b = data["bgm"]
        bf = resolve(_req(b, "file", "bgm"))
        if not bf.exists():
            raise ProjectError(f"bgm file not found: {bf}")
        bgm = Bgm(file=bf, volume_db=float(b.get("volume_db", -18.0)), fade_out=float(b.get("fade_out", 3.0)))

    sub = SubtitleStyle(**{k: v for k, v in data.get("subtitles", {}).items()
                           if k in SubtitleStyle.__dataclass_fields__})

    fps = int(data.get("fps", 30))
    if fps <= 0:
        raise ProjectError("fps must be > 0")

    return Project(
        title=str(_req(data, "title", "project")),
        segments=segments,
        root=root,
        language=data.get("language", "en"),
        voice=data.get("voice", "en-US-AndrewNeural"),
        rate=data.get("rate", "+0%"),
        width=int(data.get("width", 1920)),
        height=int(data.get("height", 1080)),
        fps=fps,
        motion_amount=float(data.get("motion_amount", 0.15)),
        supersample=int(data.get("supersample", 2)),
        out_dir=Path(data.get("out_dir", "build")),
        bgm=bgm,
        subtitles=sub,
        thumbnail_text=data.get("thumbnail_text"),
        raw=data,
    )


TEMPLATE: dict[str, Any] = {
    "title": "My first video",
    "language": "en",
    "voice": "en-US-AndrewNeural",
    "rate": "+0%",
    "width": 1920, "height": 1080, "fps": 30,
    "bgm": None,
    "subtitles": {"burn": False, "max_chars": 42, "font": "Arial", "font_size": 22},
    "thumbnail_text": "MY FIRST\nVIDEO",
    "segments": [
        {"id": "intro", "text": "Write the narration for the first segment here.",
         "image": "assets/01.jpg", "motion": "zoom_in", "pause_after": 0.6},
        {"id": "part1", "text": "Each segment is one image plus the words spoken over it.",
         "image": "assets/02.jpg", "motion": "pan_right"},
    ],
}
