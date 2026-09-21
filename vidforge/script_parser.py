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
]
# Ambiguous patterns: the marker itself (digits, **bold**) can also occur inside an ordinary
# sentence, so these additionally require the captured text to look like a title, not a sentence
# (short, no terminal punctuation) — unlike the markers above, which are unambiguous on their own.
_HEADING_AMBIGUOUS = [
    # a whole line wrapped in **bold** (optionally ***/__): many AIs bold chapter titles instead
    # of using "##" despite being asked to.
    re.compile(r"^\s*(?:\*\*\*|\*\*|__)(?P<t>(?!\s*$).+?)(?:\*\*\*|\*\*|__)\s*:?\s*$"),
    re.compile(r"^\s*(?:\d{1,2})[.)、．]\s+(?P<t>.{1,60})$"),                        # "1. Title" (short line only)
]
_NARR = re.compile(r"^\s*(?:旁白|解说|配音|台词|Narration|Narrator|VO|Voice[- ]?over)\s*[:：]\s*(?P<t>.*)$", re.I)
_VISUAL = re.compile(r"^\s*(?:画面|镜头|视觉|素材|Visual|Visuals|Shot|B-?roll|Image|On[- ]screen)\s*[:：]\s*(?P<t>.*)$", re.I)
_IGNORE = re.compile(r"^\s*(?:字幕|音乐|BGM|音效|SFX|Music|Sound|Subtitle|Title|时长|Duration)\s*[:：]", re.I)
_SENT_END = re.compile(r"(?<=[.!?。！？])\s+|(?<=[。！？])")
# Lines that are the AI talking *about* the script, not the script: preamble ("以下是…", "Here is…"),
# sign-off ("希望对你有帮助", "Let me know…"), production notes ("注：", "Note:", "备注："), word
# counts, fences and rules. They read out loud otherwise ("以下是约一千五百字的脚本…").
_CHATTER = re.compile(
    r"^\s*(?:以下是|下面是|这是|好的[，,]|当然[，,]|没问题|希望(?:这|对|以上)|如需|如果(?:你|您)需要|需要我|以上(?:就是|是)|全文完|【?完】?$|"
    r"字数[:：]|总字数|约\s*\d+\s*字|注[:：]|备注[:：]|说明[:：]|提示[:：]|温馨提示|注意[:：]|"
    r"here(?:'s| is)\b|below is|sure[,!]|certainly|of course|hope (?:this|it) helps|let me know|feel free|"
    r"note[:：]|notes?[:：]|word count|total(?: word)?s?[:：]|end of script|```|---+\s*$|\*\*\*+\s*$)", re.I)
# a whole line inside brackets = stage direction / annotation, never narration ("（停顿两秒）", "[Music swells]")
_BRACKETED = re.compile(r"^\s*[（(\[【][^）)\]】]{1,80}[）)\]】]\s*[:：]?\s*$")
# inline production notes inside a narration line: （注：…）  (Note: …)  [注：…]  — [核实]/[verify] stay
_INLINE_NOTE = re.compile(r"\s*[（(\[]\s*(?:注|备注|说明|译注|Note|Editor)[:：]?[^）)\]]*[）)\]]")
_MD_EMPHASIS = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")


def clean_line(line: str) -> str | None:
    """None = drop the line (chatter / stage note); else the line with inline notes and **bold** removed."""
    if _CHATTER.match(line) or _BRACKETED.match(line):
        return None
    line = _INLINE_NOTE.sub("", line)
    line = _MD_EMPHASIS.sub(r"\2", line)
    return line


_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'’\-]*(?:\s+[A-Za-z][A-Za-z'’\-]*){3,}")   # 4+ English words in a row


def language_issues(segments: list[dict], lang: str) -> list[dict]:
    """Segments whose narration mixes in the other language: for a Chinese project, a run of 4+
    English words (a stray sentence, not a proper noun); for an English one, any CJK characters.
    Returned as [{"index", "snippet"}] so the UI can point at them — the fix is a re-prompt or an
    edit, not something a parser should guess at."""
    out = []
    zh = lang.startswith("zh")
    for i, seg in enumerate(segments):
        t = seg.get("text", "")
        m = _LATIN_RUN.search(t) if zh else re.search(r"[一-鿿]{2,}", t)
        if m:
            out.append({"index": i, "snippet": m.group(0)[:60]})
    return out


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
            return (m.group("t") or "").strip().strip("*_ ") or "…"
    for rx in _HEADING_AMBIGUOUS:
        m = rx.match(line)
        if m:
            t = (m.group("t") or "").strip().strip("*_ ")
            # must look like a title, not a full sentence someone just happened to bold/number
            if len(t.split()) > 10 or t.endswith((".", "。", "!", "！", "?", "？")):
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
    has_visual = False                     # did the document use Visual:/画面: lines at all?

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
            cleaned = clean_line(line)
            if cleaned is None:
                continue
            if not cleaned.strip():
                flush_para()
                continue
            line = cleaned
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
                has_visual = True
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
        # under a heading we tolerate longer combined paragraphs before splitting on length
        limits = (90, 220) if structured and b.label is not None else (60, 140)
        first_of_block = True
        if b.label is not None and has_visual:
            # A chapter's Visual: line is the deliberate "new picture" signal, not a blank line:
            # the common real-world pattern is one Visual: right after the chapter title, then
            # 2-4 short paragraphs with no Visual: of their own — those are prose continuing the
            # same scene, not each a separate picture. Merge them into one segment per Visual:
            # instead of one per paragraph, or a script with one Visual: per chapter fragments
            # into several times as many segments as chapters (confirmed against real output:
            # 48 chapters -> 117 segments).
            runs: list[tuple[str | None, list[str]]] = []
            for para in b.paras:
                if para.visual or not runs:
                    runs.append((para.visual, list(para.lines)))
                else:
                    runs[-1][1].extend(para.lines)
            for visual, para_lines in runs:
                body = " ".join(para_lines)
                # a run that's too long still describes one scene once merged — every piece it
                # gets split into keeps the same hint, unlike the per-paragraph fallback below
                # (there, splitting only happens for one already-standalone overlong paragraph).
                for piece in _split_long(body, *limits):
                    segments.append({"label": b.label if first_of_block else None, "text": piece,
                                     "visual_hint": visual})
                    first_of_block = False
        else:
            # No Visual: lines anywhere in the document (or an unheaded block): fall back to one
            # paragraph = one segment, the only signal available for where a segment should end.
            last_visual: str | None = None
            for para in b.paras:
                if para.visual:
                    last_visual = para.visual
                body = " ".join(para.lines)
                for i, piece in enumerate(_split_long(body, *limits)):
                    segments.append({"label": b.label if first_of_block else None, "text": piece,
                                     "visual_hint": last_visual if i == 0 else None})
                    first_of_block = False
    return segments
