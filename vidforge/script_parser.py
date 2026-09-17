"""Turn pasted text (yours, or another AI's) into segments, honouring structure it already has.

Recognised, in priority order:
    headings   # / ##, "1." "1)" "一、" "第一章/节" "Part 1" "Segment 3:" "Scene 2", 【标题】
    screenplay two-column lines: 旁白: / Narration: / VO:  -> text ;  画面: / Visual: / Shot: -> visual_hint
    blank-line paragraphs (fallback), long ones split at sentence ends (~50 words / 140 CJK chars)

Returns [{"label": str|None, "text": str, "visual_hint": str|None}]. Pure function; unit-tested.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_HEADING = [
    re.compile(r"^\s{0,3}#{1,6}\s+(?P<t>.+?)\s*#*\s*$"),                         # markdown
    re.compile(r"^\s*(?:第[一二三四五六七八九十百零\d]+[章节段部分集幕])\s*[:：.、\s]?\s*(?P<t>.*)$"),
    re.compile(r"^\s*(?:Part|Chapter|Section|Segment|Scene|Act)\s*\d+\s*[:：.\-–]?\s*(?P<t>.*)$", re.I),
    re.compile(r"^\s*(?:[一二三四五六七八九十]+、)\s*(?P<t>.+)$"),
    re.compile(r"^\s*【(?P<t>[^】]{1,40})】\s*$"),
    re.compile(r"^\s*(?:\d{1,2})[.)、．]\s+(?P<t>.{1,60})$"),                        # "1. Title" (short line only)
]
_NARR = re.compile(r"^\s*(?:旁白|解说|配音|台词|Narration|Narrator|VO|Voice[- ]?over)\s*[:：]\s*(?P<t>.*)$", re.I)
_VISUAL = re.compile(r"^\s*(?:画面|镜头|视觉|素材|Visual|Visuals|Shot|B-?roll|Image|On[- ]screen)\s*[:：]\s*(?P<t>.*)$", re.I)
_IGNORE = re.compile(r"^\s*(?:字幕|音乐|BGM|音效|SFX|Music|Sound|Subtitle|Title|时长|Duration)\s*[:：]", re.I)
_SENT_END = re.compile(r"(?<=[.!?。！？])\s+|(?<=[。！？])")


@dataclass
class Block:
    label: str | None = None
    lines: list[str] = field(default_factory=list)
    visual: list[str] = field(default_factory=list)


def _is_cjk(s: str) -> bool:
    return sum(1 for ch in s if "CJK" in unicodedata.name(ch, "")) > len(s) * 0.3


def _heading(line: str) -> str | None:
    for rx in _HEADING:
        m = rx.match(line)
        if m:
            t = (m.group("t") or "").strip().strip("*_ ")
            # "1. Title" must look like a title, not a sentence
            if rx is _HEADING[-1] and (len(t.split()) > 10 or t.endswith((".", "。", "!", "！", "?", "？"))):
                return None
            return t or "…"
    return None


def _split_long(text: str, max_words: int = 60, max_cjk: int = 140) -> list[str]:
    sentences = [s for s in _SENT_END.split(text) if s and s.strip()]
    out, buf = [], ""
    for s in sentences:
        cand = (buf + " " + s).strip() if buf and not _is_cjk(s) else (buf + s)
        too_long = len(cand.split()) > max_words if not _is_cjk(cand) else len(cand) > max_cjk
        if buf and too_long:
            out.append(buf.strip()); buf = s
        else:
            buf = cand
    if buf.strip():
        out.append(buf.strip())
    return out or [text.strip()]


def parse(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    blocks: list[Block] = []
    cur = Block()
    structured = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if cur.lines or cur.visual:
                cur.lines.append("")                      # paragraph break inside a block
            continue
        h = _heading(line)
        if h is not None:
            structured = True
            if cur.lines or cur.visual or cur.label:
                blocks.append(cur)
            cur = Block(label=h)
            continue
        m = _NARR.match(line)
        if m:
            structured = True
            cur.lines.append(m.group("t").strip()); continue
        m = _VISUAL.match(line)
        if m:
            structured = True
            cur.visual.append(m.group("t").strip()); continue
        if _IGNORE.match(line):
            continue
        cur.lines.append(line.strip())
    if cur.lines or cur.visual or cur.label:
        blocks.append(cur)

    segments: list[dict] = []
    for b in blocks:
        paras = [p.strip() for p in "\n".join(b.lines).split("\n\n") if p.strip()]
        body = " ".join(p.replace("\n", " ") for p in paras)
        hint = "; ".join(b.visual) or None
        if not body:
            if b.label:                                   # heading with no body: a chapter card
                segments.append({"label": b.label, "text": b.label, "visual_hint": hint})
            continue
        # each paragraph is one idea = one segment; under a heading we tolerate longer paragraphs
        limits = (90, 220) if structured and b.label is not None else (60, 140)
        pieces = []
        for p in paras:
            pieces += _split_long(p.replace("\n", " "), *limits)
        for i, piece in enumerate(pieces):
            segments.append({"label": b.label if i == 0 else None, "text": piece, "visual_hint": hint if i == 0 else None})
    return segments
