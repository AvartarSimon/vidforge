"""画面预设：把一条自己录的素材修到能用，和 voicefx 是同一个思路。

Same deal as `voicefx`, for the other half of a take. A camera in a normal room hurts footage in
three predictable ways, and each has a plain filter for it:

    皮肤太糙/噪点    a small sensor at indoor light levels    -> bilateral
    画面发灰发暗     no key light, auto-exposure gives up      -> eq
    糊               the smoothing above, if left alone        -> unsharp / cas

The hard part of 美颜 is not smoothing — it is smoothing *skin* without turning eyes, hair and the
edge of the face into wax. `gblur` cannot tell the difference; `bilateral` can, because it only
averages pixels that are already similar in colour. So every beauty preset here is
bilateral-then-sharpen, never a plain blur.

Deliberately not here: face detection, face reshaping, eye enlargement, face swap. Those need a
model, a GPU and — for anything that changes what a real person looks like — a synthetic-media
disclosure. These presets only do what a decent camera would have done.

Applied when a take is saved from the recording studio, and by `vidforge videofx try`. Every
preset preserves duration and resolution, so a clip stays interchangeable with the one it replaced.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Look:
    id: str
    name: str
    about: str
    chain: str


LOOKS: tuple[Look, ...] = (
    Look("none", "不处理", "原样保留。", ""),
    Look(
        "clean", "轻修", "压一点噪点，稍微提亮。不确定选哪个就选这个。",
        "bilateral=sigmaS=4:sigmaR=0.08,eq=brightness=0.02:contrast=1.04:saturation=1.03",
    ),
    Look(
        "beauty", "柔肤", "保边平滑把皮肤修干净，再把细节加回来——不糊眼睛和头发。",
        # bilateral averages only pixels that already look alike, so skin flattens while the eyes,
        # the hairline and the jaw edge survive; unsharp then puts back the detail it did take
        "bilateral=sigmaS=10:sigmaR=0.14,"
        "unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.6,"
        "eq=brightness=0.03:contrast=1.05:saturation=1.04:gamma_r=1.02",
    ),
    Look(
        "bright", "补光", "房间光线不足时用：提亮暗部，别让脸陷进背景里。",
        "eq=brightness=0.08:contrast=1.10:saturation=1.05:gamma=1.06,"
        "bilateral=sigmaS=6:sigmaR=0.10,"
        "unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.5",
    ),
    Look(
        "crisp", "锐利", "画面偏软时提一点清晰度，不加对比度。",
        "cas=strength=0.4,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.4",
    ),
)

_BY_ID = {x.id: x for x in LOOKS}


def get(look: str) -> Look:
    x = _BY_ID.get((look or "none").strip().lower())
    if not x:
        raise KeyError(f"未知的画面预设 '{look}'（可选：{', '.join(_BY_ID)}）")
    return x


def chain(look: str) -> str:
    """Comma-terminated so it splices in front of another filter."""
    c = get(look).chain
    return f"{c}," if c else ""


def listing() -> list[dict]:
    return [{"id": x.id, "name": x.name, "about": x.about, "chain": x.chain} for x in LOOKS]


# ------------------------------------------------------------------------------------------------
# 绿幕换背景。没有绿幕就不要用这个 —— 见模块下方的说明。
GREEN = "0x00B140"          # the standard chroma green; a cloth backdrop is usually close enough


def chromakey_chain(background: str, *, colour: str = GREEN, similarity: float = 0.14,
                    blend: float = 0.08) -> str:
    """Filter_complex that drops a green backdrop and puts `background` behind the person.

    `despill` matters more than people expect: green bounces onto hair and shoulders, and without
    pulling it back out the subject reads as cut out even when the key itself is clean."""
    return (f"[1:v]scale=iw:ih[bg];"
            f"[0:v]chromakey={colour}:{similarity}:{blend},despill=type=green[fg];"
            f"[bg][fg]overlay=shortest=1[v]")
