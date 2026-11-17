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
    # CJK text needs a CJK-capable face first — and PingFang is not a file on every macOS
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        # bold: the regular CJK fallback is the light weight on most Macs, too thin for a cover
        from .hook import bold_font
        return bold_font(size)
    for c in cands:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def wrap_for(text: str, size: tuple[int, int]) -> str:
    """An upright cover is narrow: a title on one line would shrink to nothing, so it is broken
    into two or three balanced lines. A line break the user typed is kept as it is."""
    text = text.strip()
    if "\n" in text or size[1] <= size[0]:
        return text
    cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    units = list(text) if cjk else text.split()
    per = 7 if cjk else 3                                   # glyphs / words a line holds at cover size
    n = min(3, -(-len(units) // per))
    if n <= 1:
        return text
    base, extra = divmod(len(units), n)                     # balanced: no one-word last line
    lines, i = [], 0
    for j in range(n):
        k = base + (1 if j < extra else 0)
        lines.append(("" if cjk else " ").join(units[i:i + k]))
        i += k
    return "\n".join(lines)


def make(image: Path, text: str, out: Path, size: tuple[int, int] = (1280, 720)) -> None:
    text = wrap_for(text, size)
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
