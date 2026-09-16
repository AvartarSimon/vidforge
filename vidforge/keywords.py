"""Search-term suggestions from a segment's narration (no model, no network).

Heuristic: proper nouns (capitalised words not at sentence start), then long content words,
minus a stopword list; CJK text falls back to 2–4 character runs that repeat or sit next to
a place/thing marker. Good enough to pre-fill the picker's search box; the user edits it."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_STOP = set("""
a an the and or but if then than so of to in on at by for from with without into onto over under
about after before between during through across is are was were be been being have has had do does did
will would shall should can could may might must this that these those it its they them their there here
his her he she we you i me my our your who whom which what when where why how not no nor only own same
very more most other some such all any both each few many much one two three first second next last
year years day days time times part story world people man men woman women new old great little long
said says say also just like even still ever never already again ago because while until
""".split())


def _is_cjk(s: str) -> bool:
    return sum(1 for ch in s if "CJK" in unicodedata.name(ch, "")) > len(s) * 0.3


def suggest(text: str, n: int = 3) -> list[str]:
    if not text.strip():
        return []
    if _is_cjk(text):
        runs = re.findall(r"[一-鿿]{2,4}", text)
        counts = Counter(runs)
        picks = [w for w, _ in counts.most_common(n * 2)]
        return picks[:n]

    sentences = re.split(r"(?<=[.!?])\s+", text)
    proper: list[str] = []
    for s in sentences:
        words = re.findall(r"[A-Za-z][A-Za-z'\-]+", s)
        for i, w in enumerate(words):
            if w.lower() in _STOP or not w[0].isupper():
                continue
            # sentence-initial words count only when the next word is a proper noun too ("Mount Tambora")
            if i > 0 or (len(words) > 1 and words[1][0].isupper() and words[1].lower() not in _STOP):
                proper.append(w)
    # merge adjacent proper nouns ("Mount Tambora", "New England")
    merged: list[str] = []
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+|[^A-Za-z]+", text)
    buf: list[str] = []
    for tok in tokens:
        if tok in proper:
            buf.append(tok)
        elif buf and tok.isspace():
            continue                                   # "Mount" + " " + "Tambora"
        else:
            if buf:
                merged.append(" ".join(buf)); buf = []
    if buf:
        merged.append(" ".join(buf))
    ranked = [w for w, _ in Counter(merged).most_common()]
    if len(ranked) < n:
        content = [w.lower() for w in re.findall(r"[A-Za-z]{5,}", text) if w.lower() not in _STOP]
        for w, _ in Counter(content).most_common():
            if w not in [r.lower() for r in ranked]:
                ranked.append(w)
            if len(ranked) >= n:
                break
    return ranked[:n]
