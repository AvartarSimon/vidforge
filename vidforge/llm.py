"""Local small language model through Ollama (optional, zero cost, private).

If Ollama is running on localhost:11434 with a model pulled (default `qwen2.5:3b`, ~2 GB;
`qwen2.5:7b` is better if you have 8 GB+ free), vidforge uses it for the quick, private jobs:
search-keyword suggestions, zh<->en query translation, chapter names, the AI drawer's
"本地模型" option. Anything heavier (a whole script) still goes to the browser-bridge chats.

Install: https://ollama.com  →  `ollama pull qwen2.5:3b`.  Model name via OLLAMA_MODEL.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


class LlmError(RuntimeError):
    pass


def available(timeout: float = 1.5) -> dict | None:
    """-> {"model": name, "models": [...]} when Ollama answers and has a usable model, else None."""
    try:
        with urllib.request.urlopen(f"{HOST}/api/tags", timeout=timeout) as r:
            tags = json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception:  # noqa: BLE001
        return None
    names = [m.get("name", "") for m in tags]
    if not names:
        return None
    want = os.environ.get("OLLAMA_MODEL", "")
    model = next((n for n in names if want and n.startswith(want)), None) or \
        next((n for n in names if n.startswith("qwen")), None) or names[0]
    return {"model": model, "models": names}


def chat(prompt: str, *, system: str = "", model: str | None = None, json_mode: bool = False, timeout: float = 120) -> str:
    info = available()
    if not info:
        raise LlmError("本地模型不可用：请安装 Ollama 并执行 `ollama pull qwen2.5:3b`（https://ollama.com）")
    body = {"model": model or info["model"], "stream": False,
            "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}],
            "options": {"temperature": 0.3}}
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(f"{HOST}/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))["message"]["content"].strip()
    except urllib.error.URLError as e:
        raise LlmError(f"Ollama 请求失败：{e}") from None


def keywords(text: str, n: int = 4) -> list[str]:
    """Stock-footage search terms (English) for a narration snippet."""
    out = chat(f"Narration: {text}\n\nGive {n} short English search phrases (2-3 words each) for finding stock photos/video "
               f"that illustrate this narration. Concrete nouns, no abstractions. Return JSON: {{\"keywords\": [..]}}", json_mode=True)
    try:
        return [str(k) for k in json.loads(out).get("keywords", [])][:n]
    except json.JSONDecodeError:
        return []


def keywords_batch(items: dict[str, str], n_words: str = "2-4") -> dict[str, str]:
    """One English search phrase per segment in a single call (autofill over a 60-segment script
    must not take 60 round trips). Missing/garbled ids just fall back to the heuristic."""
    if not items:
        return {}
    listing = "\n".join(f"{k}: {v[:400]}" for k, v in items.items())
    out = chat("For each narration segment below give ONE English image-search phrase ({} words) naming the main "
               "event, person, place or object as an encyclopedia picture caption would (proper nouns first, add the "
               "year when it is a historical event, e.g. 'Battle of Lexington 1775', 'Independence Hall Philadelphia', "
               "'Mayflower ship'). No months, adjectives or abstract words. Always English, even when the narration is "
               "Chinese. Return JSON mapping segment id to phrase, nothing else.\n\n{}".format(n_words, listing), json_mode=True)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("keywords"), dict):
        data = data["keywords"]
    if not isinstance(data, dict):
        return {}
    phrases: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            continue
        v = v.strip().strip('"')
        if re.search(r"[A-Za-z]{3}", v):           # small models sometimes leak a CJK char into an English phrase
            v = re.sub(r"[一-鿿]+", " ", v)
        v = " ".join(v.split())
        if v:
            phrases[str(k)] = v
    return phrases


def translate_query(text: str) -> str:
    """Chinese search words -> English stock-site query."""
    if not any("一" <= ch <= "鿿" for ch in text):
        return text
    return chat(f"Translate this image-search query into 2-5 English words, nothing else: {text}").strip().strip('"')


def chapter_label(text: str, lang: str = "en") -> str:
    zh = lang.startswith("zh")
    return chat(("为下面这段解说词写一个不超过 6 个字的章节名，只输出章节名：\n" if zh else
                 "Write a chapter title of at most 5 words for this narration; output only the title:\n") + text).strip().strip('"“”')
