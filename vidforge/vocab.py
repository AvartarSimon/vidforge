"""Vocabulary card for the learner variant: 6–10 words worth teaching from the script.

Extraction uses the local Ollama model when present (word, IPA, Chinese meaning, example
sentence from the script); without it, a heuristic picks the longest distinct content words
(no IPA/meaning — the card still shows the words and their sentence).
Cached per script hash in build/vocab.json.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .keywords import _STOP

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{4,}")


def _heuristic(text: str, n: int) -> list[dict]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    seen: dict[str, str] = {}
    for s in sentences:
        for w in _WORD.findall(s):
            lw = w.lower()
            if lw in _STOP or lw in seen or w[0].isupper():
                continue
            seen[lw] = s.strip()
    ranked = sorted(seen.items(), key=lambda kv: -len(kv[0]))[:n]
    return [{"word": w, "ipa": "", "meaning": "", "example": ex} for w, ex in ranked]


def extract(text: str, n: int = 8, build_dir: Path | None = None) -> list[dict]:
    key = hashlib.sha1(f"{n}|{text}".encode("utf-8")).hexdigest()[:12]
    cache = (build_dir / "vocab.json") if build_dir else None
    if cache and cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("key") == key:
                return d["items"]
        except json.JSONDecodeError:
            pass
    items: list[dict] = []
    try:
        from . import llm
        if llm.available():
            out = llm.chat(
                f"From this English narration pick {n} words or short phrases most worth teaching to an intermediate "
                f"Chinese learner of English (useful, not proper nouns). For each give: word, IPA (British, in slashes), "
                f"a concise Chinese meaning, and the sentence from the text where it appears (shorten to <= 18 words).\n\n"
                f"Return JSON: {{\"items\": [{{\"word\": \"\", \"ipa\": \"\", \"meaning\": \"\", \"example\": \"\"}}]}}\n\nNarration:\n{text[:6000]}",
                json_mode=True, timeout=240)
            items = [i for i in json.loads(out).get("items", []) if i.get("word")][:n]
    except Exception:  # noqa: BLE001 — no model / bad JSON: heuristic below
        items = []
    if not items:
        items = _heuristic(text, n)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"key": key, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    return items
