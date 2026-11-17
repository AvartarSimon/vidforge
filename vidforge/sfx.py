"""转场音效: a soft whoosh (or a tick) where one segment hands over to the next.

Short-video editors lay a sound under almost every cut; it tells the ear a new beat has started
and makes a run of still pictures feel edited rather than played. The sounds here are made by
ffmpeg from noise and a sine — nothing is downloaded, so there is no licence to track and nothing
a platform's audio fingerprinting can match. They sit well under the narration (peaks around
-20 dBFS against speech normalised to -16 LUFS): heard, not noticed.
"""

from __future__ import annotations

from pathlib import Path

from . import ffmpeg

# (lavfi source, seconds before the cut where it starts): the whoosh swells into the cut, the
# tick lands on it
KINDS: dict[str, tuple[str, float]] = {
    "whoosh": ("anoisesrc=d=0.55:c=pink:r=48000:a=0.5,bandpass=f=1400:width_type=o:w=2.2,"
               "afade=t=in:st=0:d=0.32:curve=exp,afade=t=out:st=0.32:d=0.23,volume=1.1", 0.32),
    "tick": ("sine=f=1650:d=0.07:r=48000,afade=t=out:st=0.008:d=0.06,volume=0.7", 0.0),
}
NAMES = {"none": "不加", "whoosh": "嗖（轻）", "tick": "嗒（短）"}


def track(kind: str, at: list[float], total: float, out: Path) -> Path | None:
    """A stereo track `total` seconds long with the sound at each time in `at` (seconds, the cut)."""
    if kind not in KINDS:
        return None
    src, lead = KINDS[kind]
    at = [max(0.0, t - lead) for t in at if 0.0 < t < total]
    if not at:
        return None
    n = len(at)
    parts = [f"[0:a]aformat=channel_layouts=stereo,asplit={n}" + "".join(f"[s{i}]" for i in range(n))]
    for i, t in enumerate(at):
        parts.append(f"[s{i}]adelay={int(t * 1000)}:all=1[d{i}]")
    parts.append("".join(f"[d{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,"
                 f"apad=whole_dur={total:.3f}[a]")
    out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-y", "-f", "lavfi", "-i", src, "-filter_complex", ";".join(parts), "-map", "[a]",
                "-t", f"{total:.3f}", "-c:a", "pcm_s16le", str(out)])
    return out
