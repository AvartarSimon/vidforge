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
_VISION_HINTS = ("vl", "llava", "moondream", "minicpm-v", "gemma3", "bakllava", "vision")


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
    # A vision model (qwen2.5vl…) sorts right next to the text one and would otherwise be picked
    # for keyword/translation work, where it is slower and no better.
    text_only = [n for n in names if not any(h in n.lower() for h in _VISION_HINTS)]
    pool = text_only or names
    model = next((n for n in names if want and n.startswith(want)), None) or \
        next((n for n in pool if n.startswith("qwen")), None) or pool[0]
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


# Words that never belong in an image-search phrase: pronouns, auxiliaries, question words and
# the abstract head nouns a small model reaches for when a paragraph is argumentative rather than
# visual. A phrase containing any of them describes the narration, not a picture.
_UNSEARCHABLE = re.compile(
    r"(?i)\b(i|we|you|he|she|it|they|this|that|these|those|who|whom|whose|what|which|when|where|why|how|"
    r"am|is|are|was|were|be|been|being|do|does|did|can|could|will|would|shall|should|may|might|must|"
    r"have|has|had|get|got|just|also|still|then|than|but|because|if|so|not|no|never|more|less|very|"
    r"about|after|before|during|while|again|only|even|really|maybe|perhaps|another|other|often|"
    r"overlooked|obvious|important|interesting|famous|known|few|many|most|some|several|"
    r"rise|fall|power|strategy|strategic|competition|governance|reform|challenge|problem|idea|concept|"
    r"ability|capability|organization|system|policy|influence|importance|significance|advantage|"
    r"weakness|strength|success|failure|change|development|relationship|comparison|analysis|reason|"
    r"cause|effect|impact|pattern|patterns|understanding|survival|constraint|constraints)s?\b")

_PROMPT = (
    "For each narration segment below give ONE English image-search phrase (2-4 words) naming something a "
    "photograph, painting, map or artefact could actually show: a named person, place, building, object, "
    "artwork, map or dated event, written the way a museum or encyclopedia captions it.\n"
    "Good: 'Terracotta Army Xian' · 'Great Wall Qin dynasty' · 'Battle of Lexington 1775' · 'Shang Yang portrait'\n"
    "Bad (never do this): 'Qin rise to power' · 'Asymmetrical competition' · 'What can we learn' · "
    "'This is also understanding' — those describe the narration, not a picture.\n"
    "Hard rules: no pronouns, verbs, question words or abstract nouns; no possessives; no quotes; no "
    "punctuation. If a segment is abstract or argumentative, do NOT paraphrase it — name a concrete thing "
    "from the video's topic that suits it. Always English, even when the narration is Chinese.\n"
    "Return JSON mapping segment id to phrase, nothing else.")


def _clean_phrase(v: object) -> str | None:
    """A usable search phrase, or None. See _UNSEARCHABLE for what gets thrown away."""
    if not isinstance(v, str):
        return None
    v = v.strip().strip('"').replace("\u2019s", "").replace("'s", "")
    if re.search(r"[A-Za-z]{3}", v):          # small models leak a CJK char into an English phrase
        v = re.sub(r"[一-鿿]+", " ", v)
    v = " ".join(v.split()).rstrip(".。")
    if not v or len(v.split()) > 6 or len(v.split()) < 2:
        return None
    if re.search(r"[.?!,;:。？！，；：]", v) or _UNSEARCHABLE.search(v):
        return None
    return v


def topic_queries(topic: str, sample: str = "", n: int = 6) -> list[str]:
    """Concrete English image-search phrases for the video's subject, used for segments whose own
    narration is abstract. Translating the title is not enough ("中国历史宇宙" -> "Chinese history
    universe" finds nothing); naming things from the subject does."""
    if not topic.strip():
        return []
    try:
        out = chat("A video is about: {}\n{}\nGive {} English image-search phrases (2-4 words each) naming "
                   "concrete things a museum or archive would have pictures of for this subject: named people, "
                   "places, buildings, artefacts, artworks, maps, dated events. No abstract nouns, no verbs, no "
                   "pronouns. Return JSON: {{\"queries\": [..]}}"
                   .format(topic, f"Sample narration: {sample[:300]}" if sample else "", n), json_mode=True)
        data = json.loads(out)
    except (LlmError, json.JSONDecodeError):
        return []
    items = data.get("queries") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    seen = []
    for v in items:
        cleaned = _clean_phrase(v)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen[:n]


def keywords_prompt(items: dict[str, str], topic: str = "") -> str:
    """The batched search-phrase prompt, for callers that send it somewhere other than Ollama
    (the browser bridge: a full-size model writes far better phrases than a local 3B one)."""
    head = f"The video is about: {topic}.\n" if topic else ""
    listing = "\n".join(f"{k}: {v[:400]}" for k, v in items.items())
    return head + _PROMPT + "\n\n" + listing


def parse_keywords_answer(text: str, items: dict[str, str]) -> dict[str, str]:
    """Pull {id: phrase} out of a chat answer to keywords_prompt(); unusable phrases are dropped."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict) and isinstance(data.get("keywords"), dict):
        data = data["keywords"]
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        cleaned = _clean_phrase(v)
        if cleaned and str(k) in items:
            out[str(k)] = cleaned
    return out


def keywords_batch(items: dict[str, str], n_words: str = "2-4", topic: str = "", chunk: int = 6) -> dict[str, str]:
    """One English image-search phrase per segment. Ids with no usable phrase are simply absent,
    and the caller falls back to its own keywords.

    `topic` is the video's subject: without it a small model paraphrases abstract narration into
    equally abstract phrases ("Key to Qin's rise") that no archive can answer. `chunk` keeps each
    request small — a 3B model asked for twenty phrases at once starts echoing the narration
    ("So Qin wasn't just", "Now we can"), while six at a time it keeps naming things.
    """
    if not items:
        return {}
    head = f"The video is about: {topic}.\n" if topic else ""
    ids = list(items)
    phrases: dict[str, str] = {}
    for i in range(0, len(ids), max(1, chunk)):
        batch = ids[i:i + max(1, chunk)]
        listing = "\n".join(f"{k}: {items[k][:400]}" for k in batch)
        try:
            out = chat(head + _PROMPT + "\n\n" + listing, json_mode=True)
            data = json.loads(out)
        except (LlmError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("keywords"), dict):
            data = data["keywords"]
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            cleaned = _clean_phrase(v)
            if cleaned and str(k) in items:
                phrases[str(k)] = cleaned
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
