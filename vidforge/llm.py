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


_VISION_HINTS = ("vl", "llava", "moondream", "minicpm-v", "gemma3", "bakllava", "vision")


def vision_model() -> str | None:
    """Name of a pulled model that can look at pictures (qwen2.5vl, llava, gemma3, …), else None.
    Used to reject watermarked / off-topic pictures; `ollama pull qwen2.5vl:3b` (~3 GB) enables it."""
    info = available()
    if not info:
        return None
    want = os.environ.get("OLLAMA_VISION_MODEL", "")
    names = info["models"]
    if want:
        return next((n for n in names if n.startswith(want)), None)
    return next((n for n in names if any(h in n.lower() for h in _VISION_HINTS)), None)


def vision_check(image_path: str, subject: str = "", timeout: float = 300) -> dict:
    """Look at one picture: {"watermark": bool, "text": bool, "depicts": bool|None, "reason": str}.

    watermark = agency/site watermark, logo stamp or copyright overlay; text = large captions,
    labels, annotations or UI chrome burned into the image (a museum plaque *in* a photo is not
    an overlay). depicts = does it show `subject`? (None when no subject was asked).
    Raises LlmError when no vision model is pulled — callers decide whether to skip the check."""
    import base64
    model = vision_model()
    if not model:
        raise LlmError("没有本地视觉模型：ollama pull qwen2.5vl:3b 后可自动识别水印和核对图片内容")
    data = base64.b64encode(open(image_path, "rb").read()).decode("ascii")
    q = ("Look at this picture. Answer in JSON only: {\"watermark\": true/false, \"text\": true/false"
         + (", \"depicts\": true/false" if subject else "") + ", \"reason\": \"<10 words>\"}.\n"
         "watermark: a stock-agency or website watermark, logo stamp, copyright notice or URL overlaid on the image.\n"
         "text: large captions, labels, arrows, annotations, screenshot UI or meme text overlaid on the image "
         "(text that is part of the scene, like a sign or a book page, does not count).\n"
         + (f"depicts: does the picture clearly show {subject!r} (the actual place / event / person / object, "
            "not something merely related)?" if subject else ""))
    # keep_alive: a CPU-only box takes ~1 min per picture; reloading the model between segments would double that
    body = {"model": model, "stream": False, "format": "json", "options": {"temperature": 0}, "keep_alive": "30m",
            "messages": [{"role": "user", "content": q, "images": [data]}]}
    req = urllib.request.Request(f"{HOST}/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode("utf-8"))["message"]["content"].strip()
        j = json.loads(out)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError) as e:
        raise LlmError(f"视觉模型请求失败：{e}") from None

    def b(v):
        return v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "1")
    return {"watermark": b(j.get("watermark")), "text": b(j.get("text")),
            "depicts": (b(j.get("depicts")) if subject else None), "reason": str(j.get("reason", ""))[:120], "model": model}


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
        v = " ".join(v.split()).rstrip(".。")
        # a sentence ("This is about abstract.") is not a search phrase: drop it, the caller falls back
        if not v or len(v.split()) > 7 or re.search(r"[.?!,;:。？！，；：]", v)                 or re.match(r"(?i)(this|it|there|here|these|those|the video|the segment|about)", v):
            continue
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
