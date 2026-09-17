"""Turn pasted text (yours, or another AI's) into segments, honouring structure it already has.

Recognised, in priority order:
    headings   # / ##, "1." "1)" "一、" "第一章/节" "Part 1" "Segment 3:" "Scene 2", 【标题】
    bare titles: a short line with no ending punctuation, immediately followed by a Visual:/画面:
                 or Narration:/旁白: line, e.g. an AI that ignored "put ## before chapter names"
                 but still wrote a plain title line before each Visual:/narration pair
    screenplay two-column lines: 旁白: / Narration: / VO:  -> text ;  画面: / Visual: / Shot: -> visual_hint
    blank-line paragraphs (fallback), long ones split at sentence ends (~50 words / 140 CJK chars)

Without the bare-title rule, a script with plain titles and no "##" collapses into one giant
block: every "Visual:" line in the whole document gets attached to that single block (so only
the very first segment gets a visual hint, and it's every hint in the document concatenated),
and each paragraph — titles included — becomes its own flat segment. The bare-title rule keys
off the same Visual:/Narration: marker the AI was already asked to write, so it doesn't need
the "##" to have been followed for the split to work.

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
class Para:
    lines: list[str] = field(default_factory=list)
    visual: str | None = None       # the Visual:/画面: line(s) that appeared right before this paragraph


@dataclass
class Block:
    label: str | None = None
    paras: list[Para] = field(default_factory=list)


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


_TITLE_END = ".!?。！？…,，、"


def _bare_title(line: str, lines: list[str], i: int) -> str | None:
    """A short line with no ending punctuation, directly followed (skipping blanks) by a
    Visual:/画面: or Narration:/旁白: marker, is almost certainly a chapter title written
    without a leading '##' — see module docstring for why this matters."""
    t = line.strip()
    if not t or t[-1] in _TITLE_END or len(t) > 40 or len(t.split()) > 8:
        return None
    if _NARR.match(line) or _VISUAL.match(line) or _IGNORE.match(line):
        return None                                       # the line itself is a marker, not a title
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and (_VISUAL.match(lines[j]) or _NARR.match(lines[j])):
        return t.strip("*_ ")
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
    lines = text.split("\n")
    blocks: list[Block] = []
    cur = Block()
    cur_para = Para()
    pending_visual: str | None = None      # a Visual:/画面: line waiting for the paragraph it describes
    structured = False

    def flush_para() -> None:
        nonlocal cur_para
        if cur_para.lines:
            cur.paras.append(cur_para)
        cur_para = Para()

    def flush_block() -> None:
        nonlocal cur
        flush_para()
        if cur.paras or cur.label:
            blocks.append(cur)
        cur = Block()

    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            flush_para()                                  # blank line = paragraph break
            continue
        h = _heading(line)
        if h is None:
            h = _bare_title(line, lines, i)
        if h is not None:
            structured = True
            flush_block()
            cur.label = h
            continue
        m = _NARR.match(line)
        if m:
            structured = True
            text_line = m.group("t").strip()
        else:
            mv = _VISUAL.match(line)
            if mv:
                structured = True
                v = mv.group("t").strip()
                if cur_para.lines:                        # paragraph already started: attach directly
                    cur_para.visual = f"{cur_para.visual}; {v}" if cur_para.visual else v
                else:                                      # paragraph hasn't started: queue for it
                    pending_visual = f"{pending_visual}; {v}" if pending_visual else v
                continue
            if _IGNORE.match(line):
                continue
            text_line = line.strip()
        if not cur_para.lines and pending_visual is not None:
            cur_para.visual, pending_visual = pending_visual, None
        cur_para.lines.append(text_line)
    flush_block()

    segments: list[dict] = []
    for b in blocks:
        if not b.paras:
            if b.label:                                   # heading with no body: a chapter card
                segments.append({"label": b.label, "text": b.label, "visual_hint": None})
            continue
        # each paragraph is one idea = one segment; under a heading we tolerate longer paragraphs
        limits = (90, 220) if structured and b.label is not None else (60, 140)
        first_of_block = True
        for para in b.paras:
            body = " ".join(para.lines)
            for i, piece in enumerate(_split_long(body, *limits)):
                segments.append({"label": b.label if first_of_block else None, "text": piece,
                                 "visual_hint": para.visual if i == 0 else None})
                first_of_block = False
    return segments
