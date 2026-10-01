"""Word timings -> SRT cues.

Cues are built greedily: words are appended to the current cue until adding the
next one would exceed `max_chars`, or the gap to the next word exceeds `max_gap`
(a natural pause = a new line on screen).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .tts import Word


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)     # absolute times; empty for synthetic cues


def _is_cjk(s: str) -> bool:
    return any("CJK" in unicodedata.name(ch, "") for ch in s if not ch.isspace())


_STRIP = "".join(chr(c) for c in range(0x10000)
                if unicodedata.category(chr(c)).startswith("P") or chr(c) in "‘’“”")


_BREAK = set(".!?;:。！？；：…")


def restore_punctuation(words: list[Word], text: str) -> list[Word]:
    """edge-tts word boundaries drop punctuation; recover it from the source text.

    Latin scripts: walk whitespace tokens in order; each timed word takes the first
    not-yet-used token whose letters match it, so "1815" becomes "1815," again.
    CJK: the text has no spaces, so align character by character instead; the bare
    word text is kept (Chinese subtitles conventionally omit punctuation) but a
    following clause mark sets `break_after`, so cues split where the sentence does.
    A word that matches nothing keeps its text — mismatch degrades to no punctuation,
    never to a wrong word.
    """
    if _is_cjk(text):
        return _restore_cjk(words, text)
    tokens = text.split()
    ti = 0
    out: list[Word] = []
    for w in words:
        parts = w.text.split()                     # edge-tts may group words: "In 1815"
        keys = [p.strip(_STRIP).lower() for p in parts]
        chosen: list[str] | None = None
        for j in range(ti, min(ti + 3, len(tokens))):     # tolerate a token the TTS skipped
            cand = tokens[j:j + len(keys)]
            if [c.strip(_STRIP).lower() for c in cand] == keys:
                chosen, ti = cand, j + len(keys)
                break
        text_out = " ".join(chosen) if chosen else w.text
        out.append(Word(text=text_out, start=w.start, duration=w.duration,
                        break_after=bool(text_out) and text_out[-1] in _BREAK))
    return out


def _restore_cjk(words: list[Word], text: str) -> list[Word]:
    out: list[Word] = []
    pos = 0
    for w in words:
        bare = w.text.strip(_STRIP)
        idx = text.find(bare, pos) if bare else -1
        brk = False
        if idx != -1:
            pos = idx + len(bare)
            while pos < len(text) and (text[pos].isspace() or text[pos] in _STRIP):
                if text[pos] in _BREAK or text[pos] in "，,":
                    brk = True
                pos += 1
        out.append(Word(text=bare or w.text, start=w.start, duration=w.duration, break_after=brk))
    return out


def build_cues(words: list[Word], *, offset: float, max_chars: int, max_gap: float = 0.8,
               min_duration: float = 0.6) -> list[Cue]:
    """Split at sentence/clause marks and long pauses first, then divide each group into
    the fewest lines that fit `max_chars`, balanced in length (no orphan last word)."""
    if not words:
        return []
    cjk = _is_cjk("".join(w.text for w in words[:20]))
    sep = "" if cjk else " "
    limit = max_chars // 2 if cjk else max_chars   # a CJK glyph is about two Latin chars wide

    groups: list[list[Word]] = [[]]
    for w in words:
        prev = groups[-1][-1] if groups[-1] else None
        if prev is not None and (prev.break_after or w.start - prev.end > max_gap):
            groups.append([])
        groups[-1].append(w)

    cues: list[Cue] = []
    for g in groups:
        total = len(sep.join(w.text for w in g))
        n_lines = max(1, -(-total // limit))            # ceil
        target = total / n_lines
        line: list[Word] = []
        done = 0

        def flush() -> None:
            nonlocal done
            if not line:
                return
            start = line[0].start + offset
            end = max(line[-1].end + offset, start + min_duration)
            timed = [Word(w.text, w.start + offset, w.duration) for w in line]
            cues.append(Cue(start, end, sep.join(w.text for w in line), timed))
            line.clear()
            done += 1

        for w in g:
            cur_len = len(sep.join(x.text for x in line))
            new_len = cur_len + (len(sep) if line else 0) + len(w.text)
            if line and (new_len > limit or (done < n_lines - 1 and new_len > target)):
                flush()
            line.append(w)
        flush()

    for a, b in zip(cues, cues[1:]):                     # a cue must not overlap the next one
        if a.end > b.start:
            a.end = b.start
    return cues


_SENT_SPLIT = re.compile(r"(?<=[.!?。！？；;])\s*")


def bilingual(cues: list[Cue], alt_text: str) -> list[Cue]:
    """Second-language line under each cue. Sentences are paired 1:1 when both texts have the
    same number of sentences; otherwise the alt text is spread over the cues in proportion to
    their duration, cutting at the nearest punctuation or space."""
    if not cues or not alt_text.strip():
        return cues
    en_groups: list[list[Cue]] = [[]]
    for c in cues:
        en_groups[-1].append(c)
        if c.text.rstrip()[-1:] in ".!?。！？":
            en_groups.append([])
    en_groups = [g for g in en_groups if g]
    alt_sents = [s for s in _SENT_SPLIT.split(alt_text.strip()) if s.strip()]
    out: list[Cue] = []
    if len(alt_sents) == len(en_groups):
        for group, sent in zip(en_groups, alt_sents):
            out += _spread(group, sent)
    else:
        out = _spread(cues, alt_text.strip())
    return out


def _spread(group: list[Cue], text: str) -> list[Cue]:
    """Attach `text` (one sentence) as line 2 of its cues. The sentence is cut into clauses at
    punctuation; each cue shows the clause whose time share covers the cue's midpoint, so a
    clause that spans several cues is repeated rather than sliced mid-word."""
    clauses = [c for c in re.split(r"(?<=[，,、；;：:])", text) if c.strip()]
    if len(clauses) <= 1 or len(group) == 1:
        return [Cue(c.start, c.end, c.text + "\n" + text.strip()) for c in group]
    total_chars = sum(len(c) for c in clauses)
    bounds, acc = [], 0.0
    for cl in clauses:                       # cumulative character share of each clause
        acc += len(cl) / total_chars
        bounds.append(acc)
    t0, t1 = group[0].start, group[-1].end
    span = max(0.2, t1 - t0)
    out = []
    for c in group:
        mid = ((c.start + c.end) / 2 - t0) / span
        idx = next((i for i, b in enumerate(bounds) if mid <= b), len(clauses) - 1)
        out.append(Cue(c.start, c.end, c.text + "\n" + clauses[idx].strip()))
    return out


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# What a data channel wants lit up: figures, years, percentages, money, and the units that carry
# the point. Highlighting the number the narrator is saying is the cheapest retention trick we can
# do that nobody else can, because we already know when every word is spoken.
_KEY = re.compile(
    r"^[^\w]*("
    r"\d[\d,.]*\s*(?:%|％|万亿|亿|万|千|百分点|倍|年|月|日|美元|元|人|吨|公里|平方公里)"   # has a unit
    r"|\d{2,}[\d,.]*"                                 # two digits or more
    r"|\d+[.,]\d+"                                    # a decimal
    r"|[一二三四五六七八九十百千万亿零两]{2,}(?:%|％|万亿|亿|万|倍|年|人)"
    r"|[$€£]\d[\d,.]*"
    r")[^\w]*$")


def is_key_word(text: str) -> bool:
    """Does this token carry a figure worth lighting up?"""
    return bool(_KEY.match(text.strip()))


def _ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    sec, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{sec:02d}.{cs:02d}"


def _bgr(hex_colour: str) -> str:
    """#RRGGBB -> ASS &HBBGGRR (ASS stores colours the other way round)."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def write_ass(cues: list[Cue], path: Path, *, font: str, font_size: int, margin_v: int,
              box: bool, highlight: str = "keywords", colour: str = "#d4793a",
              width: int = 1920, height: int = 1080) -> None:
    """Burn-ready subtitles with the key words in the brand colour.

    highlight:
      keywords — figures stay coloured for the whole cue (one line per cue, cheapest, safest)
      karaoke  — each word lights up as it is spoken, figures stay lit afterwards
                 (one line per word; needs the word timings `build_cues` now keeps)
    """
    hi, white = _bgr(colour), "&H00FFFFFF"
    border = "BorderStyle=4,Outline=2,Shadow=0" if box else "BorderStyle=1,Outline=2,Shadow=0"
    head = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 2", "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}", f"PlayResY: {height}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Main,{font},{font_size},{white},{hi},&H00000000,&H99000000,0,0,0,0,100,100,0,0,"
        f"{'4' if box else '1'},2,0,2,60,60,{margin_v},1", "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")

    lines: list[str] = []
    for cue in cues:
        words = cue.words
        if highlight == "none" or not words:
            lines.append(f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Main,,0,0,0,,{esc(cue.text)}")
            continue
        sep = "" if _is_cjk(cue.text) else " "
        keys = [is_key_word(w.text) for w in words]
        if highlight == "karaoke":
            # one line per word: everything up to the current word is lit, the rest is plain —
            # a figure that has been said stays lit so it can still be read a beat later
            for i, w in enumerate(words):
                start = max(cue.start, w.start)
                end = min(cue.end, words[i + 1].start if i + 1 < len(words) else cue.end)
                if end <= start:
                    continue
                parts = []
                for j, w2 in enumerate(words):
                    lit = keys[j] and j <= i
                    parts.append(f"{{\\c{hi}}}{esc(w2.text)}{{\\c{white}}}" if lit else esc(w2.text))
                lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{sep.join(parts)}")
        else:
            parts = [f"{{\\c{hi}}}{esc(w.text)}{{\\c{white}}}" if keys[i] else esc(w.text)
                     for i, w in enumerate(words)]
            lines.append(f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Main,,0,0,0,,{sep.join(parts)}")

    Path(path).write_text("\n".join(head + lines) + "\n", encoding="utf-8")


def write_srt(cues: list[Cue], path: Path) -> None:
    lines: list[str] = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{_ts(c.start)} --> {_ts(c.end)}", c.text, ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
