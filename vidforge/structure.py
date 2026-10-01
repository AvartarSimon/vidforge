"""段落骨架与留存体检：决定「先说什么」，而不是「怎么说」。

Retention is decided before a single picture is chosen. The numbers this module is built on come
from the 2026 retention-editing material and from YouTube's own metric definitions:

  * the first big drop-off sits at **25–35 s** — a video that is still clearing its throat there
    loses the audience it just earned;
  * YouTube's "Intro" metric is the share still watching at **0:30**, and it feeds recommendations;
  * in the first three minutes something on screen should change every **10–20 s**;
  * chapters measurably raise session duration on anything over six minutes.

So a template here is not a writing style. It is a sequence of beats with a share of the runtime
each, chosen so the promise lands before 0:30 and the payoff is spread rather than saved up.

    outline("data_explainer", 10)   -> the segment skeleton, with target lengths
    prompt_block(...)               -> the part of the script prompt that enforces it
    check(project, durations)       -> what is wrong with the script you already have
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


@dataclass
class Beat:
    id: str
    name: str                 # the chapter label the viewer will see
    role: str                 # what this beat has to accomplish — goes into the prompt
    share: float              # fraction of the runtime
    min_seconds: float = 8.0
    max_seconds: float | None = None   # a hook stays a hook at any runtime


@dataclass
class Template:
    id: str
    name: str
    about: str
    beats: list[Beat] = field(default_factory=list)


# Retention thresholds, all from the material cited in the module docstring.
HOOK_SECONDS = 15.0          # the promise must land inside this
DROPOFF_START, DROPOFF_END = 25.0, 35.0
INTRO_METRIC_AT = 30.0
MAX_SEGMENT_SECONDS = 45.0   # a single unbroken stretch longer than this has no visual change
SEGMENT_TARGET_SECONDS = 30.0  # what a new script is planned to, leaving room to run over
CHAPTER_MIN_MINUTES = 6.0


TEMPLATES: dict[str, Template] = {
    "data_explainer": Template(
        id="data_explainer", name="数据解说（钩子-背景-数据-转折-回扣）",
        about="一个热点 + 一组数字 + 一个反直觉的结论。经济、房地产、人口、能源这类题材的默认骨架。",
        beats=[
            Beat("hook", "钩子", "用一个具体数字或反差开场，10 秒内说清这条视频要回答什么问题。不要自我介绍，不要铺垫。", 0.06, 8, max_seconds=HOOK_SECONDS),
            Beat("stakes", "为什么现在讲", "把这个问题和观众自己的处境连起来：它影响谁、为什么是现在。", 0.10, 15),
            Beat("background", "背景", "最少量的前情：只讲理解后面数据所必需的那部分。", 0.16, 20),
            Beat("data", "数据", "摆出核心数据，一次一个指标，配图表并标来源。这里是全片信息密度最高的部分。", 0.30, 40),
            Beat("turn", "转折", "给出一个与直觉相反、或与主流叙述相反的解读，并说明依据。", 0.22, 30),
            Beat("callback", "回扣", "回到开场那个数字，给出结论和它的边界；最后一句引出下一期。", 0.16, 20),
        ]),
    "history_explainer": Template(
        id="history_explainer", name="历史解说（场景-谜题-线索-转折-今天）",
        about="从一个有画面感的场景进入，落到今天。适合历史、国际、政策题材。",
        beats=[
            Beat("scene", "开场场景", "一个具体的时间、地点、人物，像电影开场。不要先讲年代背景。", 0.08, 10, max_seconds=HOOK_SECONDS),
            Beat("puzzle", "谜题", "点明这件事里反常的地方——观众要带着这个问题往下看。", 0.10, 15),
            Beat("timeline", "来龙去脉", "按时间或因果推进，每一步只保留改变结果的那些事实。", 0.32, 40),
            Beat("turn", "转折", "推翻一个流行说法，或给出史料里更站得住的解释。", 0.26, 30),
            Beat("today", "照到今天", "把它和当下的某件事并置，说明为什么现在值得重提。", 0.16, 20),
            Beat("next", "下一期", "一句话留钩子。", 0.08, 10),
        ]),
    "news_take": Template(
        id="news_take", name="热点解读（事件-为什么现在-数据-两种解读-判断）",
        about="短平快地讲清一条新闻，并给出自己的判断。适合政策、金融、科技快评。",
        beats=[
            Beat("what", "发生了什么", "一句话讲清事件本身，不带评论。", 0.10, 10, max_seconds=HOOK_SECONDS),
            Beat("why_now", "为什么现在", "时间点为什么重要，之前有没有预兆。", 0.14, 15),
            Beat("numbers", "数字", "用数据给事件定量：多大、多快、和历史比如何。", 0.28, 30),
            Beat("two_reads", "两种解读", "并列呈现两方最强的论证，不要稻草人。", 0.28, 30),
            Beat("judgement", "我的判断", "给出倾向和理由，并说明什么证据会让你改变看法。", 0.20, 20),
        ]),
}

def list_templates() -> list[dict]:
    return [{"id": t.id, "name": t.name, "about": t.about,
             "beats": [{"id": b.id, "name": b.name, "role": b.role} for b in t.beats]}
            for t in TEMPLATES.values()]


def get(template_id: str) -> Template:
    t = TEMPLATES.get(template_id)
    if not t:
        raise KeyError(f"未知的结构模板 '{template_id}'（可选：{', '.join(TEMPLATES)}）")
    return t


def outline(template_id: str, minutes: float) -> list[dict]:
    """The skeleton: one entry per beat with the seconds and word count it should run to.

    Chinese narration runs at roughly 240 字/分钟 and English at 150 words — the same figures the
    script prompt already uses — so the word target is what actually constrains the writing."""
    t = get(template_id)
    total = max(60.0, minutes * 60.0)
    # Capping the hook frees seconds that have to go somewhere, or a ten-minute script comes back
    # nine minutes long; they are shared out over the beats that have no ceiling.
    floor = min(1.0, total / sum(b.min_seconds for b in t.beats))
    raw = {b.id: max(b.min_seconds * floor, total * b.share) for b in t.beats}
    spare = sum(v - min(v, b.max_seconds) for b in t.beats if b.max_seconds
                for v in [raw[b.id]])
    open_share = sum(b.share for b in t.beats if not b.max_seconds) or 1.0
    out = []
    for b in t.beats:
        seconds = raw[b.id]
        if b.max_seconds:
            seconds = min(seconds, b.max_seconds)
        else:
            seconds += spare * b.share / open_share
        seconds = max(round(b.min_seconds * floor), round(seconds))
        # A beat is a chapter, not a segment: at ten minutes "数据" runs three minutes, and one
        # unbroken three-minute segment is exactly what check() flags. Splitting to the target
        # rather than the 45 s limit leaves the writer room to run long without breaking the rule.
        segments = max(1, math.ceil(seconds / SEGMENT_TARGET_SECONDS))
        out.append({"id": b.id, "label": b.name, "role": b.role,
                    "seconds": seconds, "segments": segments,
                    "zh_words": round(seconds / 60 * 240),
                    "en_words": round(seconds / 60 * 150)})
    return out


def prompt_block(template_id: str, minutes: float, zh: bool = True) -> str:
    """The part of the script prompt that makes the model write to the skeleton."""
    t = get(template_id)
    rows = outline(template_id, minutes)
    nseg = sum(r["segments"] for r in rows)
    if zh:
        lines = [f"\n\n结构（覆盖上面第 3 条里段落数量和顺序的自由度）——按这个骨架写，顺序不要换"
                 f"（{t.name}）：", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {r['label']}（约 {r['zh_words']} 字，拆成 {r['segments']} 个段落）："
                         f"{r['role']}")
        lines += ["",
                  f"全片共 {nseg} 个段落；章节名用这一块的名字，同一块拆成多段时写成"
                  "「数据 1」「数据 2」这样。",
                  f"硬要求：前 {HOOK_SECONDS:.0f} 秒之内必须把这条视频要回答的问题说清楚；"
                  f"第 {DROPOFF_START:.0f}-{DROPOFF_END:.0f} 秒是观众流失最多的地方，"
                  "那里要有一个新信息或一次转折，不能还在铺垫；"
                  "结尾必须回到开场那个数字或那个问题。"]
        return "\n".join(lines)
    lines = [f"\n\nStructure (this overrides the free choice of segment count and order in point 3)"
             f" - write to this skeleton, in this order ({t.name}):", ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['label']} (~{r['en_words']} words, split into {r['segments']} "
                     f"segment{'s' if r['segments'] > 1 else ''}): {r['role']}")
    lines += ["",
              f"{nseg} segments in all; name each chapter after its block, numbering them "
              '"Data 1", "Data 2" when a block spans several segments.',
              f"Hard requirements: state the question this video answers within the first "
              f"{HOOK_SECONDS:.0f} seconds; the {DROPOFF_START:.0f}-{DROPOFF_END:.0f} second mark is "
              "where most viewers leave, so put new information or a turn there, not more setup; "
              "the ending must come back to the number or question you opened with."]
    return "\n".join(lines)


def skeleton_segments(template_id: str, minutes: float) -> list[dict]:
    """Empty segments carrying the beat as the label and the brief as placeholder text."""
    out = []
    for r in outline(template_id, minutes):
        n = r["segments"]
        for i in range(n):
            out.append({"id": r["id"] if n == 1 else f"{r['id']}{i + 1}",
                        "label": r["label"] if n == 1 else f"{r['label']} {i + 1}",
                        "text": "", "clips": [], "visual_hint": "",
                        "_brief": r["role"], "_target_seconds": round(r["seconds"] / n),
                        "_zh_words": round(r["zh_words"] / n)})
    return out


# ---------------------------------------------------------------------------------------------
_NUMBER = re.compile(
    r"\d"                                        # any digit
    r"|[百千万亿兆]"                                   # a magnitude is always a quantity
    r"|[一二三四五六七八九十]{2,}"                     # 二十、一九四九
    r"|[一二三四五六七八九十][年月日倍成代纪元人口%％]"        # 十年、三倍，但不包括“聊一聊”
)
_QUESTION = re.compile(r"[?？]|为什么|怎么|凭什么|会不会|是不是|多少|how |why |what |will ")


@dataclass
class Issue:
    level: str        # "problem" | "advice"
    where: str        # segment id, or "" for the whole video
    what: str
    fix: str


def check(segments: list[dict], durations: dict[str, float] | None = None) -> list[Issue]:
    """Read a script the way the first thirty seconds of the finished video will be watched.

    `durations` are the measured segment lengths when the project has been rendered; without them
    the length is estimated from the text, which is close enough for the opening checks."""
    issues: list[Issue] = []
    if not segments:
        return [Issue("problem", "", "脚本是空的", "先写或生成脚本")]

    def length(seg) -> float:
        if durations and seg.get("id") in durations:
            return durations[seg["id"]]
        text = seg.get("text") or ""
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        return cjk / 4.0 if cjk > len(text) * 0.3 else len(text.split()) / 2.5

    lengths = [length(s) for s in segments]
    starts, cursor = [], 0.0
    for d in lengths:
        starts.append(cursor)
        cursor += d
    total = cursor

    first = segments[0]
    first_text = (first.get("text") or "")[:200]
    if not _NUMBER.search(first_text) and not _QUESTION.search(first_text):
        issues.append(Issue("problem", first.get("id", ""),
                            "开场既没有具体数字，也没有提出问题",
                            "头一两句就抛一个数字或一个问题——观众在这里决定走不走"))
    if lengths[0] > HOOK_SECONDS * 1.6:
        issues.append(Issue("advice", first.get("id", ""),
                            f"第一段约 {lengths[0]:.0f} 秒，钩子被稀释了",
                            f"把要回答的问题压进前 {HOOK_SECONDS:.0f} 秒，其余挪到下一段"))

    # What is on screen during the 25–35 s window. A segment that merely spans it is fine — one
    # that started back inside the hook and is *still* running at 35 s is the failure: the viewer
    # has had no new beat since they arrived.
    straddling = [(i, st, d) for i, (st, d) in enumerate(zip(starts, lengths))
                  if st < DROPOFF_START and st + d > DROPOFF_END]
    if straddling and total > DROPOFF_END:
        i, st, d = straddling[0]
        if st < HOOK_SECONDS and d > 25:
            issues.append(Issue("problem", segments[i].get("id", ""),
                                f"这一段从开场一直讲到 {st + d:.0f} 秒，"
                                f"穿过了 {DROPOFF_START:.0f}–{DROPOFF_END:.0f} 秒这段没有换气",
                                "在 25 秒前切一段，或在这里插入一个新数字/一次转折——这是流失最高的位置"))

    if total > INTRO_METRIC_AT:
        before_30 = sum(1 for st in starts if st < INTRO_METRIC_AT)
        if before_30 < 2:
            issues.append(Issue("advice", "",
                                "前 30 秒只有一个段落",
                                "拆成两段：YouTube 的 Intro 指标看的就是 0:30 的留存"))

    for seg, d in zip(segments, lengths):
        if d > MAX_SEGMENT_SECONDS:
            issues.append(Issue("advice", seg.get("id", ""),
                                f"这一段约 {d:.0f} 秒，中间没有切换点",
                                f"拆成两段（每段不超过 {MAX_SEGMENT_SECONDS:.0f} 秒），画面也才跟着换"))

    labelled = sum(1 for s in segments if (s.get("label") or "").strip())
    if total > CHAPTER_MIN_MINUTES * 60 and labelled < 3:
        issues.append(Issue("advice", "",
                            f"片长超过 {CHAPTER_MIN_MINUTES:.0f} 分钟但几乎没有章节名",
                            "给每段写个章节名：六分钟以上的视频加章节能提高会话时长"))

    last_text = (segments[-1].get("text") or "")
    first_key = set(re.findall(r"\d[\d,.]*", first_text))
    if first_key and not (first_key & set(re.findall(r"\d[\d,.]*", last_text))):
        issues.append(Issue("advice", segments[-1].get("id", ""),
                            "结尾没有回到开场那个数字",
                            "把开场的数字在结尾再说一次并给出结论——回扣是完播率最省力的做法"))
    return issues
