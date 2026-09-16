"""`vidforge demo DIR` — a self-contained sample project with generated placeholder images."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

DEMO_SEGMENTS = [
    ("hook", "zoom_in",
     "In 1815, a volcano on the other side of the world cancelled summer in Europe. "
     "This is the story of the year without a summer."),
    ("eruption", "pan_right",
     "Mount Tambora, on the island of Sumbawa, erupted with a force ten times greater than Krakatoa. "
     "It threw so much ash into the stratosphere that sunlight itself dimmed."),
    ("europe", "zoom_out",
     "By the following June, snow was falling in New England and crops were failing across France and Germany. "
     "Bread riots followed. Nobody yet understood why."),
    ("legacy", "pan_left",
     "Out of that cold, wet summer came Frankenstein, written by Mary Shelley while trapped indoors by the rain. "
     "One eruption, one lost harvest, one monster that never died."),
]

PALETTE = [(38, 70, 83), (231, 111, 81), (42, 157, 143), (233, 196, 106)]


def _placeholder(path: Path, idx: int, label: str, size=(1920, 1080)) -> None:
    base = PALETTE[idx % len(PALETTE)]
    img = Image.new("RGB", size, base)
    draw = ImageDraw.Draw(img)
    # simple diagonal stripes so camera motion is visible
    for i in range(-size[1], size[0], 160):
        draw.line([(i, size[1]), (i + size[1], 0)], fill=tuple(min(255, c + 25) for c in base), width=40)
    draw.text((80, 80), f"{idx + 1:02d}  {label}", fill="white", font_size=96)
    img.save(path, quality=90)


def create(target: Path) -> Path:
    target = Path(target)
    assets = target / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, (sid, motion, text) in enumerate(DEMO_SEGMENTS):
        img = assets / f"{i + 1:02d}_{sid}.jpg"
        _placeholder(img, i, sid)
        segments.append({"id": sid, "text": text, "image": f"assets/{img.name}",
                         "motion": motion, "pause_after": 0.6})
    project = {
        "title": "The Year Without a Summer",
        "language": "en",
        "voice": "en-US-AndrewNeural",
        "rate": "-3%",
        "width": 1920, "height": 1080, "fps": 30,
        "bgm": None,
        "subtitles": {"burn": True, "max_chars": 42, "font": "Arial", "font_size": 22},
        "thumbnail_text": "THE YEAR\nWITHOUT A SUMMER",
        "segments": segments,
    }
    (target / "project.json").write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    return target / "project.json"
