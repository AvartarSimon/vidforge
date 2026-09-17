"""Word timings -> SRT cues.

Cues are built greedily: words are appended to the current cue until adding the
next one would exceed `max_chars`, or the gap to the next word exceeds `max_gap`
(a natural pause = a new line on screen).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .tts import Word


@dataclass
class Cue:
    start: float
    end: float
    text: str


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
            cues.append(Cue(start, end, sep.join(w.text for w in line)))
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


def write_srt(cues: list[Cue], path: Path) -> None:
    lines: list[str] = []
    for i, c in enumerate(cues, 1):
        lines += [str(i), f"{_ts(c.start)} --> {_ts(c.end)}", c.text, ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
