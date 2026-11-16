"""开场大字：the first seconds of the video carry the question in big type over the picture.

Short-video practice (剪映's 花字 openers, Shorts/抖音 hook formulas): a viewer decides in about
three seconds, mostly with the sound off, so the question the video answers is put on screen
while the narrator is still saying it. It is laid over the picture rather than cut in front of
it — a title card in front would push the first spoken word back by its own length, which is
the opposite of a hook.

The card is a picture (drawn here with PIL) faded in and out by the final pass, like the series
badge: it needs neither libass nor Remotion, so it works on every machine that renders at all.
The text is the user's own — nothing here writes a hook for them.
"""

from __future__ import annotations

import platform
from pathlib import Path

DEFAULT_SECONDS = 3.0

# bold faces: the regular CJK fallback in theme.py is the light weight on most Macs, and a hook
# set in a light weight reads as a caption, not as the point of the video
_BOLD = {
    "Darwin": ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
               "/System/Library/Fonts/STHeiti Medium.ttc"],
    "Windows": ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"],
    "Linux": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}
_WEIGHTS = ("Semibold", "Bold", "Medium", "W6", "Heavy")
_OTHER_SCRIPTS = (" JP", " KR", " TC", " HK", " J", " K")


def _bold_face(path: str, size: int):
    """The simplified-Chinese bold face inside a collection: which index that is differs
    between macOS releases, so the faces are asked their names rather than counted."""
    from PIL import ImageFont
    for i in range(24):
        try:
            f = ImageFont.truetype(path, size, index=i)
        except OSError:
            break
        name, style = f.getname()
        if style in _WEIGHTS and not any(name.endswith(t) or f"{t} " in name for t in _OTHER_SCRIPTS):
            return f
    return None


def bold_font(size: int):
    for path in _BOLD.get(platform.system(), []):
        if Path(path).exists():
            f = _bold_face(path, size)
            if f is not None:
                return f
    from .theme import cjk_font
    return cjk_font(size)


def _wrap(text: str, font, max_w: int) -> list[str]:
    """Greedy lines that fit `max_w`; Chinese breaks between any two glyphs, Latin between words.
    A line break the user typed is always kept."""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    out: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        tokens = para.split(" ") if " " in para else list(para)
        sep = " " if " " in para else ""
        line = ""
        for t in tokens:
            cand = f"{line}{sep}{t}" if line else t
            if line and d.textlength(cand, font=font) > max_w:
                out.append(line)
                line = t
            else:
                line = cand
        if line:
            out.append(line)
    return out


def card_png(text: str, out: Path, *, width: int, height: int, theme: dict | None = None,
             accent: str = "#d4793a") -> Path:
    """The hook card: up to three lines in a solid box, the first in the text colour and the rest
    in the accent, like the template's two-line title. Long text gets a smaller size, never a
    fourth line — at that length it is a sentence, not a hook."""
    from PIL import Image, ImageDraw
    from . import theme as th
    k = 2                                           # drawn large, scaled down: smooth corners
    tall = height > width
    if theme:
        p = th.get(theme.get("palette"))
        box, first, rest = p.box, p.text, p.accent
        fill = _rgba(box, 255)
    else:
        box, first, rest = "#000000", "#FFFFFF", accent
        fill = _rgba(box, 200)
    size = round((width * 0.075 if tall else height * 0.085)) * k
    max_w = round(width * 0.82) * k
    while True:
        font = bold_font(size)
        lines = _wrap(text, font, max_w)
        if len(lines) <= 3 or size <= 24 * k:
            break
        size = round(size * 0.88)
    lines = lines[:3]
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    boxes = [d.textbbox((0, 0), ln, font=font) for ln in lines]
    lh = round(size * 1.28)
    pad_x, pad_y = round(size * 0.55), round(size * 0.38)
    w = max(b[2] - b[0] for b in boxes) + 2 * pad_x
    h = lh * len(lines) + 2 * pad_y - (lh - size)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=round(size * 0.32), fill=fill)
    for i, (ln, b) in enumerate(zip(lines, boxes)):
        x = (w - (b[2] - b[0])) // 2 - b[0]
        y = pad_y + i * lh - b[1] + (size - (b[3] - b[1])) // 2 - (size // 12)
        draw.text((x, y), ln, font=font, fill=first if i == 0 else rest)
    im = im.resize((max(2, w // k), max(2, h // k)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def _rgba(colour: str, alpha: int) -> tuple[int, int, int, int]:
    h = colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha


def position(width: int, height: int, card_w: int, card_h: int) -> tuple[int, int]:
    """Centred, in the upper middle: below the vertical template's presenter window and badge
    (they end about a quarter of the way down), well above the subtitle line."""
    cy = 0.40 if height > width else 0.36
    return (width - card_w) // 2, max(0, round(height * cy - card_h / 2))
