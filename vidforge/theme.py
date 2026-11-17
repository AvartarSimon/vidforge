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

from .subtitles import SCRIPT_LINES


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


# 画幅: the shapes a project can be made in. Upright ones get the phone layout (window up top,
# subtitles lifted over the platform's caption area); the rest keep the subtitles low.
FRAMES: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),     # YouTube / B站 / 头条·西瓜
    "9:16": (1080, 1920),     # 抖音 / 快手 / TikTok / Shorts / 视频号
    "3:4": (1080, 1440),      # 小红书 (its feed tile and the full-screen player both take it)
    "1:1": (1080, 1080),      # square: feeds that show either orientation
}
CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
SHAPES = ("rounded", "circle")


def frame_of(raw: dict) -> tuple[int, int]:
    return int(raw.get("width") or 1920), int(raw.get("height") or 1080)


def window_box(width: int, height: int, shape: str = "rounded") -> tuple[float, float]:
    """The presenter window as overlay (size, height): fractions of the frame's width and height.

    Worked out from the frame's own proportions — a 3:4 box sized for 9:16 came out as a strip
    461x194 in a 1920x1080 project. Upright frames get a 3:4 portrait box, wide ones a 4:3 one,
    a circle is square in pixels whatever the frame."""
    tall = height > width
    size = WINDOW_W if tall else 0.22
    px_w = size * width
    ratio = 1.0 if shape == "circle" else (4 / 3 if tall else 3 / 4)
    return size, round(px_w * ratio / height, 4)


def window_place(width: int, height: int, size: float, box_h: float, corner: str = "top-left",
                 sub_band: float = 0.0) -> str:
    """`position` (fractions of the free space, as render.py reads it) for a corner. A bottom
    corner sits above the subtitle line: wide subtitles run nearly edge to edge, and on a phone the
    lifted line and the platform's caption take the lower part of the frame."""
    tall = height > width
    win_w, win_h = size * width, box_h * height
    mx = width * (MARGIN_X if tall else 0.03)
    top = height * (MARGIN_TOP if tall else 0.05)
    bottom_clear = height * max(SUB_LIFT + 0.12 if tall else sub_band + 0.02, 0.05)
    left = mx if "left" in corner else width - mx - win_w
    y = top if corner.startswith("top") else height - bottom_clear - win_h
    fx = left / max(1.0, width - win_w)
    fy = max(0.0, y) / max(1.0, height - win_h)
    return f"{min(1.0, max(0.0, fx)):.4f},{min(1.0, max(0.0, fy)):.4f}"


def _sub_band(raw: dict) -> float:
    from .subtitles import band
    sub = raw.get("subtitles") or {}
    if not sub.get("burn"):
        return 0.0
    return band(int(sub.get("font_size", 22)), int(sub.get("margin_v", 48)), 2 if sub.get("bilingual") else 1)


def apply(raw: dict, palette: str, *, badge: str = "", side: str = "left", frame: str | None = None) -> dict:
    """Set the project's frame and colours, in place. Returns `raw`.

    `frame` ("16:9", "9:16", "3:4", "1:1") changes the size; None keeps the project's own. The
    palette colours the subtitles, the badge, the charts and the presenter window's frame in any
    shape; the phone layout (lifted subtitles, 12 glyphs a line) only applies to upright frames."""
    p = get(palette)
    if frame:
        if frame not in FRAMES:
            raise KeyError(f"未知画幅 '{frame}'（可选：{', '.join(FRAMES)}）")
        raw["width"], raw["height"] = FRAMES[frame]
    w, h = frame_of(raw)
    tall = h > w
    raw["theme"] = {"palette": p.id, "badge": badge.strip(), "side": side}
    sub = raw.setdefault("subtitles", {})
    sub.update({"burn": True, "style": "box", "highlight_colour": p.accent, "box_colour": p.box, "text_colour": p.text})
    if tall:
        sub.update({
            # word by word: on a phone the eye follows the lit word, which is what keeps it on the line
            "highlight": "word",
            # in subtitle script units (288 lines to the frame), like every other project's
            "font_size": round(SCRIPT_LINES * 0.034), "margin_v": round(SCRIPT_LINES * SUB_LIFT),
            # counted in Latin characters, and build_cues() halves it for Chinese: 24 is 12 glyphs,
            # which at this font size is the width of the frame less its margins
            "max_chars": 24,
        })
    else:
        # back to the wide defaults if the project was upright before
        sub.update({"highlight": sub.get("highlight") or "keywords", "font_size": 22, "margin_v": 48, "max_chars": 42})
    for seg in raw.get("segments") or []:
        for o in seg.get("overlays") or []:
            if is_presenter_overlay(o):
                o.update(presenter_overlay(o.get("video") or "", raw, shape=o.get("shape"), corner=o.get("corner")))
    return raw


def presenter_overlay(video_rel: str, raw: dict, *, shape: str | None = None, corner: str | None = None) -> dict:
    """The overlay a studio take becomes when it is the small window rather than the picture."""
    t = raw.get("theme") or {}
    w, h = frame_of(raw)
    shape = shape if shape in SHAPES else "rounded"
    if corner not in CORNERS:
        # up top on the template's side — the series badge takes the other top corner; with no
        # template, a wide frame puts it top right, where a face-cam usually is
        side = t.get("side") or ("left" if h > w else "right")
        corner = f"top-{'right' if side == 'right' else 'left'}"
    size, box_h = window_box(w, h, shape)
    frame_colour = get(t.get("palette")).frame if t else "#ffffff"
    return {"video": video_rel, "presenter": True, "shape": shape, "corner": corner, "size": size, "height": box_h,
            "position": window_place(w, h, size, box_h, corner, _sub_band(raw)), "border": True,
            "border_color": frame_colour, "animate": "fade"}


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
