"""Voice presets: a few ffmpeg filters that make a recording sound like narration.

No machine learning here, and none is needed — a phone recording in a normal room is mostly hurt
by three things, each of which a plain filter fixes:

    低频轰鸣   air conditioning, traffic, the desk              -> highpass
    底噪       the room's own hiss, the microphone's floor      -> afftdn
    音量忽大忽小  leaning in and out of the mic                  -> acompressor

What is left is taste: a little lift around 120 Hz reads as 浑厚, a little lift around 3 kHz reads
as 清亮, and a dip near 5 kHz keeps the s-sounds from stinging. So the presets are named after the
*result* rather than the filters, and there is deliberately no way to type a raw filter chain —
that road ends with a project that only renders on the machine where it was tuned.

Applied in render.py on the same pass as `loudnorm`, which always comes last: the preset shapes the
tone, loudnorm sets the level. Every filter here preserves duration, which is not a nicety — the
word timings that drive the subtitles were measured against this audio, so a filter that stretched
it (atempo, rubberband) would silently slide the whole subtitle track.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    about: str
    chain: str


PRESETS: tuple[Preset, ...] = (
    Preset("none", "不处理", "只做响度统一（loudnorm），音色原样保留。", ""),
    Preset(
        "clean", "只清理", "去低频轰鸣和底噪，不改音色。不确定选哪个就选这个。",
        "highpass=f=80,afftdn=nr=10:nf=-30",
    ),
    Preset(
        "warm", "浑厚解说", "低频加一点身体感，中低频去箱音，齿音压一点。解说类的默认选择。",
        "highpass=f=70,afftdn=nr=10:nf=-30,"
        "equalizer=f=120:t=q:w=0.9:g=3,"      # body
        "equalizer=f=300:t=q:w=1.0:g=-2,"     # boxiness lives here, and it reads as "muddy"
        "equalizer=f=5000:t=q:w=1.2:g=-2,"    # sibilance
        "acompressor=threshold=-18dB:ratio=3:attack=12:release=220",
    ),
    Preset(
        "clear", "清亮口播", "提亮 3 kHz 的咬字，适合语速快、信息密的段落。",
        "highpass=f=90,afftdn=nr=10:nf=-30,"
        "equalizer=f=200:t=q:w=1.0:g=-1.5,"
        "equalizer=f=3000:t=q:w=1.4:g=3,"     # consonant definition
        "acompressor=threshold=-20dB:ratio=3.5:attack=8:release=180",
    ),
    Preset(
        "phone", "手机录音补救", "降噪更狠、压缩更重，用来救嘈杂环境里用手机录的素材。",
        "highpass=f=100,lowpass=f=12000,afftdn=nr=20:nf=-25,"
        "equalizer=f=150:t=q:w=1.0:g=2,"
        "equalizer=f=400:t=q:w=1.2:g=-3,"     # phone mics pile up here
        "equalizer=f=3500:t=q:w=1.4:g=2.5,"
        "acompressor=threshold=-22dB:ratio=4:attack=8:release=160",
    ),
)

_BY_ID = {p.id: p for p in PRESETS}


def get(preset: str) -> Preset:
    p = _BY_ID.get((preset or "none").strip().lower())
    if not p:
        raise KeyError(f"未知的人声预设 '{preset}'（可选：{', '.join(_BY_ID)}）")
    return p


def chain(preset: str) -> str:
    """The filter chain, comma-terminated so it can be spliced in front of another filter."""
    c = get(preset).chain
    return f"{c}," if c else ""


def listing() -> list[dict]:
    return [{"id": p.id, "name": p.name, "about": p.about, "chain": p.chain} for p in PRESETS]
