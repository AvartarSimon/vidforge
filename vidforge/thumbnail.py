"""Thumbnail: first segment's image, darkened, with big outlined title text."""

from __future__ import annotations

import platform
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

_FONT_CANDIDATES = {
    "Windows": ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/msyhbd.ttc"],
    "Darwin": ["/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
               "/System/Library/Fonts/PingFang.ttc"],
    "Linux": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def _font(size: int, text: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    cands = list(_FONT_CANDIDATES.get(platform.system(), []))
    # CJK text needs a CJK-capable face first
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        cands = [c for c in cands if "msyh" in c or "PingFang" in c] + cands
    for c in cands:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def make(image: Path, text: str, out: Path, size: tuple[int, int] = (1280, 720)) -> None:
    img = Image.open(image).convert("RGB")
    # cover-fit
    ratio = max(size[0] / img.width, size[1] / img.height)
    img = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)
    left, top = (img.width - size[0]) // 2, (img.height - size[1]) // 2
    img = img.crop((left, top, left + size[0], top + size[1]))
    img = ImageEnhance.Brightness(img).enhance(0.6)

    draw = ImageDraw.Draw(img)
    lines = text.split("\n")
    font_size = int(size[1] * 0.16)
    font = _font(font_size, text)
    # shrink until the longest line fits 90 % of the width
    while font_size > 24:
        widest = max(draw.textlength(ln, font=font) for ln in lines)
        if widest <= size[0] * 0.9:
            break
        font_size -= 4
        font = _font(font_size, text)

    line_h = font_size * 1.15
    total_h = line_h * len(lines)
    y = (size[1] - total_h) / 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (size[0] - w) / 2
        draw.text((x, y), ln, font=font, fill="white", stroke_width=max(2, font_size // 14), stroke_fill="black")
        y += line_h

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
