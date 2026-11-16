"""竖屏主题模板：配色 + 版式，一次设定，整条视频都按它出。

The layout Simon specified for 竖屏 talking-head explainers (2026-11-16):

    主画面铺满整个竖屏               the segment's own pictures, edge to edge (1080x1920)
    真人小窗 ≈ 22–26 % 宽，3:4 圆角   the presenter take as a picture-in-picture box, upper left
    小窗只在讲解/讲述的段落出现        a segment opts in by having a presenter overlay
    字幕在中下部，避开底部平台信息区   lifted ~24 % off the bottom: 抖音/快手/TikTok put the
                                    caption, the music line and the buttons in the bottom fifth
    顶部系列角标                     "RESTART · 001": series name + episode number

and "颜色再明亮，鲜一点" — so every palette here is a light or saturated one; there is no dark-grey
option on purpose. A palette colours the subtitle box and its highlight, the badge, and the
presenter window's frame; the pictures themselves are never tinted.

`apply()` writes all of that into project.json (size, subtitle style, the presenter overlays'
box) so it stays visible and editable in the UI; `badge_png()` draws the badge the final pass
lays over the whole video.
"""

from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Palette:
    id: str
    name: str
    box: str          # subtitle box
    text: str         # subtitle text
    accent: str       # highlighted words, the second title line
    badge_bg: str
    badge_text: str
    frame: str        # presenter window border
    page: str         # the backdrop colour used in previews / title cards


PALETTES: tuple[Palette, ...] = (
    Palette("sunny", "暖阳橙", "#FF8A3D", "#FFFFFF", "#FFF35C", "#FFFFFF", "#FF6A1A", "#FFFFFF", "#FFE3C7"),
    Palette("mint", "薄荷绿", "#14C38E", "#FFFFFF", "#FFF35C", "#FFFFFF", "#0FA578", "#FFFFFF", "#D8F7EA"),
    Palette("sky", "天空蓝", "#2F8CFF", "#FFFFFF", "#FFE066", "#FFFFFF", "#1E6FE0", "#FFFFFF", "#DCEBFF"),
    Palette("coral", "珊瑚粉", "#FF5C7A", "#FFFFFF", "#FFF0A8", "#FFFFFF", "#F2385C", "#FFFFFF", "#FFE0E6"),
    Palette("lemon", "柠檬黄", "#FFD93D", "#1F2A30", "#E8483B", "#1F2A30", "#FFD93D", "#FFD93D", "#FFF7CC"),
    Palette("violet", "活力紫", "#8B5CF6", "#FFFFFF", "#FDE047", "#FFFFFF", "#7C3AED", "#FFFFFF", "#EDE4FF"),
)
_BY_ID = {p.id: p for p in PALETTES}

# 版式 (fractions of the 1080x1920 frame)
WINDOW_W = 0.24                     # 22–26 % of the width
WINDOW_H = WINDOW_W * 1080 * 4 / 3 / 1920   # 3:4 box, as a fraction of the height
MARGIN_X = 0.045
MARGIN_TOP = 0.075                  # below the status bar / the platform's own top chrome
SUB_LIFT = 0.24                     # subtitle baseline above the bottom: clear of the caption area


def get(pid: str | None) -> Palette:
    return _BY_ID.get(pid or "", PALETTES[0])


def listing() -> list[dict]:
    return [asdict(p) for p in PALETTES]


def _luma(colour: str) -> float:
    h = colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def graphics_theme(t: dict | None) -> dict | None:
    """The template's colours as the `theme` prop of the animated charts and title cards. Without it
    they keep their own near-black backdrop, and a bright video goes dark for every chart.

    The accent is whichever of the palette's two strong colours is darker: the other one is the
    yellow that highlights words inside the subtitle box, unreadable on the pale page."""
    if not t:
        return None
    p = get(t.get("palette"))
    return {"bg": p.page, "fg": "#1F2A30", "muted": "#5B6770", "accent": min((p.box, p.accent), key=_luma)}


def window_position(side: str = "left") -> str:
    """The presenter window's `position` as render.py reads it: fractions of the *free* space."""
    fx = MARGIN_X / (1 - WINDOW_W)
    fy = MARGIN_TOP / (1 - WINDOW_H)
    return f"{(fx if side == 'left' else 1 - fx):.4f},{fy:.4f}"


def is_presenter_overlay(o: dict) -> bool:
    """A take of you rather than a picture: from the footage library, or a studio take."""
    v = str(o.get("video") or "")
    return bool(o.get("me")) or "/takes/" in f"/{v}" or v.startswith("takes/") or bool(o.get("presenter"))


def apply(raw: dict, palette: str, *, badge: str = "", side: str = "left") -> dict:
    """Set the project up for the vertical template, in place. Returns `raw`."""
    p = get(palette)
    raw["width"], raw["height"] = 1080, 1920
    raw["theme"] = {"palette": p.id, "badge": badge.strip(), "side": side}
    sub = raw.setdefault("subtitles", {})
    sub.update({
        "burn": True, "style": "box", "highlight": "keywords",
        "font_size": round(1920 * 0.034), "margin_v": round(1920 * SUB_LIFT),
        # counted in Latin characters, and build_cues() halves it for Chinese: 24 is 12 glyphs,
        # which at this font size is the width of the frame less its margins
        "max_chars": 24,
        "highlight_colour": p.accent, "box_colour": p.box, "text_colour": p.text,
    })
    for seg in raw.get("segments") or []:
        for o in seg.get("overlays") or []:
            if is_presenter_overlay(o):
                o.update({"shape": "rounded", "size": WINDOW_W, "height": round(WINDOW_H, 4),
                          "position": window_position(side), "border": True, "border_color": p.frame,
                          "animate": o.get("animate") or "fade"})
    return raw


def presenter_overlay(video_rel: str, raw: dict) -> dict:
    """The overlay a studio take becomes when it is the small window rather than the picture."""
    t = raw.get("theme") or {}
    p = get(t.get("palette"))
    return {"video": video_rel, "presenter": True, "shape": "rounded", "size": WINDOW_W, "height": round(WINDOW_H, 4),
            "position": window_position(t.get("side", "left")), "border": True, "border_color": p.frame,
            "animate": "fade"}


# -- the badge ------------------------------------------------------------------------------------
_CJK_FONTS = {
    "Darwin": ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
               "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"],
    "Windows": ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"],
    "Linux": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def cjk_font(size: int):
    """A font that can draw Chinese on this machine (PingFang is not a file on every macOS)."""
    from PIL import ImageFont
    for c in _CJK_FONTS.get(platform.system(), []):
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def badge_png(text: str, palette: str, out: Path, *, height: int = 1920) -> Path:
    """The series badge: rounded pill, palette colours, sized for the frame."""
    from PIL import Image, ImageDraw
    p = get(palette)
    k = 3                                       # drawn large, scaled down: smooth corners
    size = round(height * 0.022) * k
    font = cjk_font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    pad_x, pad_y = round(size * 0.7), round(size * 0.42)
    w, h = (r - l) + 2 * pad_x, (b - t) + 2 * pad_y
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=p.badge_bg)
    d.text((pad_x - l, pad_y - t), text, font=font, fill=p.badge_text)
    im = im.resize((max(2, w // k), max(2, h // k)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def badge_position(side: str, width: int, height: int, badge_w: int) -> tuple[int, int]:
    """Top corner opposite the presenter window, so the two never collide."""
    y = round(height * MARGIN_TOP)
    x = round(width * MARGIN_X)
    return (width - x - badge_w, y) if side == "left" else (x, y)
