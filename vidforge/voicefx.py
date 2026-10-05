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
        "deep", "低沉磁性", "降半个到一个半音，加胸腔共鸣和泛音，压齿音。"
        "年轻/偏亮的声音想要成熟感就选这个。",
        "highpass=f=65,afftdn=nr=10:nf=-30,"
        # rubberband shifts pitch and leaves the length alone (measured: delta 0.000s) — asetrate
        # would change the speed too, and atempo would change the length. The word timings were
        # measured against this audio, so only a pitch-only shift is safe here.
        "rubberband=pitch=0.944,"
        "equalizer=f=110:t=q:w=0.8:g=3.5,"    # chest
        "equalizer=f=320:t=q:w=1.0:g=-2.5,"   # mud
        "deesser=i=0.35,"
        "aexciter=amount=1.5:blend=1,"        # added harmonics are what "磁性" actually is
        "acompressor=threshold=-20dB:ratio=3.5:attack=10:release=200",
    ),
    Preset(
        "radio", "电台质感", "压缩更重、泛音更多，像电台主播。"
        "信息密度高的段落听起来更有权威感。",
        "highpass=f=85,afftdn=nr=12:nf=-30,"
        "equalizer=f=150:t=q:w=0.9:g=2,"
        "equalizer=f=400:t=q:w=1.2:g=-2.5,"
        "equalizer=f=2800:t=q:w=1.3:g=2.5,"   # presence: where authority is heard
        "deesser=i=0.4,"
        "aexciter=amount=2:blend=2,"
        "acompressor=threshold=-24dB:ratio=5:attack=5:release=120",
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


MAX_PITCH = 4.0        # semitones either way; beyond this a voice stops sounding like a person


def pitch_filter(semitones: float) -> str:
    """Pitch shift on its own, comma-terminated, or "" for no shift.

    A preset is someone else's taste; how deep *your* voice should sit is not something a preset
    can know, so this one number stays separate and tunable. rubberband changes pitch without
    touching the length — the subtitle timings depend on that."""
    try:
        st = float(semitones)
    except (TypeError, ValueError):
        raise KeyError(f"音高要是一个数字（半音），不是 {semitones!r}") from None
    if st != st or abs(st) > MAX_PITCH:                      # NaN or out of range
        raise KeyError(f"音高要在 ±{MAX_PITCH:.0f} 个半音之内（给的是 {semitones}）")
    if abs(st) < 0.01:
        return ""
    return f"rubberband=pitch={2 ** (st / 12):.6f},"


def listing() -> list[dict]:
    return [{"id": p.id, "name": p.name, "about": p.about, "chain": p.chain} for p in PRESETS]
