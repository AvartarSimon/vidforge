"""The channel's own look: name, slogan, colours, logo, a 1-second opener and an end card.

Why these shapes and not a fancier intro — the research is unambiguous and it decides the design:
an intro over about five seconds depresses YouTube's "Intro" metric (the share of viewers still
there at 0:30), and that metric feeds recommendations directly. So:

    opener   ~1.2 s  logo + slogan, placed *after* the hook, not before it (cold open first)
    end card ~6 s    logo + slogan + what the next video is + where to subscribe
                     (YouTube end screens need at least 5 s to be clickable)

A brand kit lives in `~/.vidforge/brand.json` and any project may override it. One kit drives the
opener, the end card and the colour of every chart, so a channel looks like one channel.

    vidforge brand init --name 刻度 --slogan "把热点放进时间里"   # writes logo SVGs + the kit
    vidforge brand sting                                         # a 1.4 s audio mark, no licence
    vidforge brand preview                                       # renders the opener + end card

On music: every "free AI music" route has a licence trap — MusicGen is CC-BY-NC, which a
monetised channel may not use. `sting` therefore *synthesises* a mark from pure tones with
ffmpeg: nobody owns a sine wave, so there is nothing to clear.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import ffmpeg

BRAND_DIR = Path.home() / ".vidforge" / "brand"
BRAND_FILE = BRAND_DIR / "brand.json"


class BrandError(RuntimeError):
    pass


@dataclass
class Brand:
    name: str = ""                       # 频道名，出现在片头和片尾
    slogan: str = ""                     # 一句话，别超过 12 个字，片头只有一秒
    en_name: str = ""                    # optional second line for bilingual channels
    bg: str = "#0d1117"
    fg: str = "#f3f4f6"
    muted: str = "#8b949e"
    accent: str = "#d4793a"
    font: str = 'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif'
    logo: str = ""                       # path to an SVG/PNG; "" = draw the built-in mark
    mark: str = "ticks"                  # built-in mark: ticks | line | axis
    intro: bool = True                   # prepend the 1.2 s opener at build time
    outro: bool = True                   # append the end card
    intro_seconds: float = 1.2
    outro_seconds: float = 6.0
    sting: str = ""                      # audio for the opener; "" = silent
    outro_music: str = ""
    subscribe: str = "订阅，下期继续"
    next_hint: str = ""                  # 片尾那句「下期：…」
    extra: dict = field(default_factory=dict)

    def theme(self) -> dict:
        """The palette every chart and card shares."""
        return {"bg": self.bg, "fg": self.fg, "muted": self.muted, "accent": self.accent, "font": self.font}


def load(project_raw: dict | None = None) -> Brand:
    """Global kit, with this project's `brand` block layered on top."""
    data: dict = {}
    if BRAND_FILE.is_file():
        try:
            data = json.loads(BRAND_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    if project_raw:
        data = {**data, **(project_raw.get("brand") or {})}
    fields = {f for f in Brand.__dataclass_fields__}
    return Brand(**{k: v for k, v in data.items() if k in fields})


def save(brand: Brand) -> Path:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    BRAND_FILE.write_text(json.dumps(asdict(brand), ensure_ascii=False, indent=1), encoding="utf-8")
    return BRAND_FILE


# -- the mark -------------------------------------------------------------------------------
# Three marks, all built from the same idea: this channel measures things over time. They are
# drawn rather than illustrated so they stay legible at 32 px (a YouTube avatar) and as a corner
# watermark, which is where a logo actually has to work.

def logo_svg(brand: Brand, mark: str | None = None, size: int = 512) -> str:
    """The channel mark as SVG. `ticks` is the default: a ruler, which is both a chart axis and
    a timeline — the two halves of "用数据看热点，用历史看今天" in one shape."""
    mark = mark or brand.mark
    bg, fg, accent = brand.bg, brand.fg, brand.accent
    s = size
    pad = s * 0.16
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}">'
    frame = f'<rect x="0" y="0" width="{s}" height="{s}" rx="{s*0.22:.0f}" fill="{bg}"/>'

    if mark == "ticks":
        # a measuring scale: evenly spaced ticks, one of them longer and in the accent colour —
        # "this moment, measured". Reads as a ruler at any size.
        base = s * 0.70
        ticks = []
        n = 7
        for i in range(n):
            x = pad + (s - 2 * pad) * i / (n - 1)
            is_now = i == n - 3
            h = s * (0.30 if is_now else 0.16)
            colour = accent if is_now else fg
            w = s * (0.055 if is_now else 0.035)
            ticks.append(f'<rect x="{x - w/2:.1f}" y="{base - h:.1f}" width="{w:.1f}" height="{h:.1f}" '
                         f'rx="{w/2:.1f}" fill="{colour}"/>')
        rule = f'<rect x="{pad:.1f}" y="{base:.1f}" width="{s - 2*pad:.1f}" height="{s*0.035:.1f}" rx="{s*0.018:.1f}" fill="{fg}" opacity="0.85"/>'
        return head + frame + "".join(ticks) + rule + "</svg>"

    if mark == "line":
        # a rising series whose newest point is a filled dot: the chart, reduced to its gesture
        pts = [(0.0, 0.62), (0.25, 0.50), (0.5, 0.56), (0.75, 0.30), (1.0, 0.18)]
        coords = [(pad + (s - 2 * pad) * x, pad + (s - 2 * pad) * y) for x, y in pts]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(coords))
        last = coords[-1]
        return (head + frame +
                f'<path d="{d}" fill="none" stroke="{fg}" stroke-width="{s*0.055:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="{s*0.075:.1f}" fill="{accent}"/>'
                "</svg>")

    if mark == "axis":
        # two axes and one point — the smallest possible "a measurement exists here"
        x0, y0 = pad, s - pad
        return (head + frame +
                f'<path d="M{x0:.1f},{pad:.1f} L{x0:.1f},{y0:.1f} L{s-pad:.1f},{y0:.1f}" fill="none" '
                f'stroke="{fg}" stroke-width="{s*0.05:.1f}" stroke-linecap="round"/>'
                f'<circle cx="{s*0.66:.1f}" cy="{s*0.36:.1f}" r="{s*0.085:.1f}" fill="{accent}"/>'
                f'<path d="M{x0:.1f},{y0:.1f} L{s*0.66:.1f},{s*0.36:.1f}" stroke="{accent}" '
                f'stroke-width="{s*0.03:.1f}" stroke-dasharray="{s*0.06:.1f} {s*0.05:.1f}" opacity="0.6"/>'
                "</svg>")

    raise BrandError(f"未知的标志样式 '{mark}'（可选：ticks | line | axis）")


def write_logos(brand: Brand, folder: Path | None = None) -> list[Path]:
    """All three marks, so the choice is made by looking rather than by imagining."""
    folder = Path(folder or BRAND_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for mark in ("ticks", "line", "axis"):
        p = folder / f"logo-{mark}.svg"
        p.write_text(logo_svg(brand, mark), encoding="utf-8")
        out.append(p)
    return out


# -- the audio mark -------------------------------------------------------------------------
# Three notes and a soft tail. Short enough to sit under a one-second logo, distinctive enough to
# be recognised by the third video, and synthesised here so there is no licence to clear.
STINGS = {
    "rise": (587.33, 880.00, 1174.66),      # D5 A5 D6 — open, optimistic, "a number going up"
    "settle": (880.00, 659.25, 440.00),     # A5 E5 A4 — resolving downward, calmer
    "two": (659.25, 987.77, 0.0),           # E5 B5 — a two-note mark, the least intrusive
}


def sting(out: Path, style: str = "rise", seconds: float = 1.4, gain: float = 0.22) -> Path:
    """Write the audio mark. Pure tones with an exponential decay, mixed to one stereo file."""
    notes = STINGS.get(style)
    if not notes:
        raise BrandError(f"未知的音效 '{style}'（可选：{', '.join(STINGS)}）")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    live = [f for f in notes if f > 0]
    step = seconds / (len(live) + 1.2)
    inputs: list[str] = []
    filters: list[str] = []
    for i, freq in enumerate(live):
        inputs += ["-f", "lavfi", "-t", f"{seconds:.2f}",
                   "-i", f"sine=frequency={freq:.2f}:sample_rate=48000"]
        start = i * step
        # a plucked envelope: silent until this note's turn, then a fast attack and a long decay
        filters.append(
            f"[{i}:a]adelay={int(start*1000)}|{int(start*1000)},"
            f"afade=t=in:st={start:.2f}:d=0.012,"
            f"afade=t=out:st={start + 0.10:.2f}:d={max(0.25, seconds - start - 0.10):.2f},"
            f"volume={gain * (1.0 if i == len(live) - 1 else 0.75):.3f}[n{i}]")
    mix = "".join(f"[n{i}]" for i in range(len(live)))
    filters.append(f"{mix}amix=inputs={len(live)}:normalize=0,aformat=channel_layouts=stereo[a]")
    ffmpeg.run([*inputs, "-filter_complex", ";".join(filters), "-map", "[a]",
                "-t", f"{seconds:.2f}", "-c:a", "aac", "-b:a", "192k", "-y", str(out)])
    return out


# -- clips ----------------------------------------------------------------------------------
def _props(brand: Brand, extra: dict) -> dict:
    return {"name": brand.name, "slogan": brand.slogan, "enName": brand.en_name,
            "mark": brand.mark, "theme": brand.theme(), **extra}


def render_opener(brand: Brand, out_dir: Path, width: int, height: int, fps: int, log=print) -> Path:
    """The ~1 s brand flash that goes after the hook."""
    from . import remotion
    return remotion.render("Intro", _props(brand, {}), duration=max(0.6, brand.intro_seconds),
                           fps=fps, width=width, height=height, out_dir=out_dir, log=log)


def render_endcard(brand: Brand, out_dir: Path, width: int, height: int, fps: int, log=print) -> Path:
    """The end card: long enough for YouTube's end screen to be clickable (>= 5 s)."""
    from . import remotion
    extra = {"subscribe": brand.subscribe, "nextHint": brand.next_hint}
    return remotion.render("Outro", _props(brand, extra), duration=max(5.0, brand.outro_seconds),
                           fps=fps, width=width, height=height, out_dir=out_dir, log=log)


def with_audio(clip: Path, audio: Path | None, out: Path, seconds: float) -> Path:
    """Put the sting (or silence) under a brand clip so it concatenates with the rest."""
    args = ["-y", "-i", str(clip)]
    if audio and Path(audio).is_file():
        args += ["-i", str(audio), "-filter_complex",
                 f"[1:a]atrim=0:{seconds:.2f},apad=whole_dur={seconds:.2f}[a]", "-map", "0:v", "-map", "[a]"]
    else:
        args += ["-f", "lavfi", "-t", f"{seconds:.2f}", "-i", "anullsrc=r=48000:cl=stereo",
                 "-map", "0:v", "-map", "1:a"]
    args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
    ffmpeg.run(args)
    return out


def suggest_slogans(name: str = "") -> list[str]:
    """Starting points that fit a data-and-history channel: short, concrete, no boasting."""
    return [
        "把热点放进时间里",
        "用数据看热点，用历史看今天",
        "每个热点，都有前传",
        "先看数据，再下判断",
        "数字背后，是时间",
    ]


def contrast_ok(bg: str, fg: str) -> bool:
    """WCAG-ish check: a slogan that cannot be read on the card is not a design, it is a bug."""
    def lum(hex_colour: str) -> float:
        h = hex_colour.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]
    a, b = lum(bg), lum(fg)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05) >= 4.5
