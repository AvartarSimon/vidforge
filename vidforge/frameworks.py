"""框架：从一条参考视频拆出它的结构，变成「段落骨架」里能直接套用的模板。

What a good video does with its time is the part worth copying — never its pictures or its words.
So the framework is the sequence of blocks (what each one does and how long it runs) plus the
numbers that show the pace, and it is saved as a structure template: the script step lists it
beside the built-in skeletons, the AI script prompt writes to it, `structure.check()` measures
against it.

How it is read:

    words    faster-whisper with timestamps (the same model the own-voice alignment uses)
    cuts     ffmpeg's scene score on a 320 px copy — cheap, and enough to count shots
    blocks   the local model (Ollama) groups ~10 s chunks of transcript into blocks and says what
             each does and by what device; without a model the video is cut by time into a hook,
             three middle blocks and an ending, and the framework says so
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import ffmpeg, references, structure

_PUNCT = re.compile(r"[。！？!?；;]$|[.](?=\s|$)")


class FrameworkError(RuntimeError):
    pass


def _cuts(video: Path) -> list[float]:
    r = subprocess.run([ffmpeg.find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(video), "-an",
                        "-vf", "scale=320:-2,select='gt(scene,0.3)',metadata=print:file=-", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", r.stdout)]


def sentences(words: list[tuple[str, float, float]]) -> list[dict]:
    """Whisper's words joined into sentences: at punctuation, at a pause of 0.6 s, or at 40 characters
    (Chinese transcripts often come back with no punctuation at all)."""
    out: list[dict] = []
    cur: list[tuple[str, float, float]] = []
    for i, w in enumerate(words):
        cur.append(w)
        text = "".join(x[0] for x in cur) if _is_cjk(w[0]) else " ".join(x[0] for x in cur)
        gap = words[i + 1][1] - w[2] if i + 1 < len(words) else 9.0
        if _PUNCT.search(w[0].strip()) or gap > 0.6 or len(text) >= 40:
            out.append({"start": round(cur[0][1], 2), "end": round(cur[-1][2], 2), "text": text.strip()})
            cur = []
    return out


def _is_cjk(s: str) -> bool:
    return bool(re.search(r"[一-鿿]", s))


def chunks(sents: list[dict], seconds: float = 10.0, limit: int = 40) -> list[dict]:
    """Sentences merged into ~10 s chunks, at most `limit` of them: what fits a small model's window."""
    if not sents:
        return []
    total = sents[-1]["end"] - sents[0]["start"]
    seconds = max(seconds, total / limit)
    out: list[dict] = []
    for s in sents:
        if out and s["start"] - out[-1]["start"] < seconds:
            out[-1]["end"] = s["end"]
            out[-1]["text"] = (out[-1]["text"] + " " + s["text"]).strip()
        else:
            out.append(dict(s))
    return out


def metrics(sents: list[dict], cuts: list[float], total: float) -> dict:
    text = "".join(s["text"] for s in sents)
    zh = _is_cjk(text)
    spoken = sum(s["end"] - s["start"] for s in sents) or total
    first15 = " ".join(s["text"] for s in sents if s["start"] < 15)
    hook_end = next((s["end"] for s in sents if s["end"] >= 5), sents[0]["end"] if sents else 0.0)
    return {
        "seconds": round(total, 1),
        "pace": round(len(re.sub(r"\s", "", text)) / (spoken / 60)) if zh else round(len(text.split()) / (spoken / 60)),
        "pace_unit": "字/分钟" if zh else "词/分钟",
        "shots": len(cuts) + 1,
        "shot_seconds": round(total / (len(cuts) + 1), 1),
        "cuts_first_15s": sum(1 for c in cuts if c < 15),
        "first_line_seconds": round(hook_end, 1),
        "question_up_front": bool(re.search(r"[？?]|为什么|怎么|吗|why|how|what", first15, re.I)),
        "number_up_front": bool(re.search(r"\d|[一二三四五六七八九十百千万亿]{2,}", first15)),
        "language": "zh" if zh else "en",
    }


def _llm_blocks(parts: list[dict], title: str, zh: bool) -> dict | None:
    from . import llm
    if not llm.available():
        return None
    listing = "\n".join(f"{i}. [{p['start']:.0f}s] {p['text'][:70]}" for i, p in enumerate(parts))
    if zh:
        prompt = (f"下面是一条做得很好的视频《{title}》按时间切成的小段转写（编号. [开始秒] 内容）：\n\n{listing}\n\n"
                  "把它分成 4 到 7 个连续的结构块（比如钩子、背景、数据、转折、案例、回扣、引导关注，按实际内容命名），"
                  "每块给出起止编号、一句话说这一块在做什么（写成给写稿人的指令，不要复述原文内容）、用了什么手法。"
                  '只返回 JSON：{"name": "这个框架的名字（10 字以内）", "about": "一句话说这种结构适合什么题材", '
                  '"blocks": [{"name": "块名", "from": 0, "to": 3, "role": "这一块要做到什么", "technique": "手法"}]}')
    else:
        prompt = (f"Below is the transcript of a well-made video \"{title}\", cut into short timed chunks "
                  f"(index. [start s] text):\n\n{listing}\n\n"
                  "Group it into 4-7 consecutive structural blocks (hook, context, data, turn, example, payoff, "
                  "call to action - name them by what they actually do). For each give the first and last index, "
                  "one line on what the block must achieve (an instruction to a script writer, not a summary of "
                  "this video's content) and the device it uses. Return JSON only: {\"name\": \"a short name for "
                  "this framework\", \"about\": \"one line on what topics it suits\", \"blocks\": [{\"name\": "
                  "\"...\", \"from\": 0, \"to\": 3, \"role\": \"...\", \"technique\": \"...\"}]}")
    try:
        data = json.loads(llm.chat(prompt, json_mode=True, timeout=240))
    except (llm.LlmError, ValueError):
        return None
    blocks = data.get("blocks") if isinstance(data, dict) else None
    if not isinstance(blocks, list) or not blocks:
        return None
    # the model's indices are advice: made contiguous, in order, covering every chunk
    clean, nxt = [], 0
    for b in blocks:
        try:
            to = max(nxt, min(len(parts) - 1, int(b.get("to", nxt))))
        except (TypeError, ValueError):
            continue
        if nxt > len(parts) - 1:
            break
        clean.append({"name": str(b.get("name") or "块")[:12], "from": nxt, "to": to,
                      "role": str(b.get("role") or "")[:160], "technique": str(b.get("technique") or "")[:60]})
        nxt = to + 1
    if not clean:
        return None
    clean[-1]["to"] = len(parts) - 1
    return {"name": str(data.get("name") or "")[:20], "about": str(data.get("about") or "")[:120], "blocks": clean}


def _time_blocks(parts: list[dict], zh: bool) -> dict:
    """Without a model: a hook (up to ~15 s), three middle blocks, an ending (~the last tenth)."""
    n = len(parts)
    total = parts[-1]["end"]
    hook_to = max(0, max((i for i, p in enumerate(parts) if p["end"] <= 15), default=0))
    end_from = min(n - 1, max(hook_to + 1, next((i for i, p in enumerate(parts) if p["start"] >= total * 0.9), n - 1)))
    middle = list(range(hook_to + 1, end_from))
    names = ("钩子", "展开 1", "展开 2", "展开 3", "结尾") if zh else ("Hook", "Part 1", "Part 2", "Part 3", "Ending")
    spans = [(0, hook_to)]
    if middle:
        k = max(1, len(middle) // 3)
        cuts = [middle[0], middle[min(len(middle) - 1, k)], middle[min(len(middle) - 1, 2 * k)]]
        bounds = sorted(set(cuts)) + [end_from]
        spans += [(bounds[i], bounds[i + 1] - 1) for i in range(len(bounds) - 1)]
    spans.append((end_from, n - 1))
    blocks = []
    for j, (a, b) in enumerate(spans):
        if a > b:
            continue
        name = names[0] if j == 0 else names[-1] if j == len(spans) - 1 else names[min(j, 3)]
        blocks.append({"name": name, "from": a, "to": b, "technique": "",
                       "role": ("（原片这里在说：" if zh else "(the original says here: ") + parts[a]["text"][:40] + ("…）" if zh else "…)")})
    return {"name": "", "about": "", "blocks": blocks}


def split_hook(blocks: list[dict], parts: list[dict], zh: bool) -> list[dict]:
    """A small model happily calls the first minute "the hook". The hook is what is said before the
    viewer decides (structure.HOOK_SECONDS); a first block that runs past 20 s is cut there and the
    rest of it becomes the set-up."""
    first = blocks[0]
    if parts[first["to"]]["end"] - parts[first["from"]]["start"] <= 20 or first["to"] == first["from"]:
        return blocks
    cut = max((i for i in range(first["from"], first["to"]) if parts[i]["end"] <= structure.HOOK_SECONDS),
              default=first["from"])
    hook = {**first, "to": cut, "name": "钩子" if zh else "Hook"}
    rest = {**first, "from": cut + 1, "name": "铺垫" if zh else "Set-up",
            "role": first["role"] if first["name"] not in ("钩子", "Hook") else ("把开场的问题展开，交代为什么值得看下去" if zh
                                                                                 else "open up the question from the hook and why it matters")}
    return [hook, rest, *blocks[1:]]


def extract(ref_id: str, log=print) -> dict:
    """Read one reference video into a framework; save it beside the video and as a template."""
    from . import align
    folder = references.folder_of(ref_id)
    info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
    video = folder / "video.mp4"
    total = ffmpeg.duration(video)
    if not align.available():
        raise FrameworkError("拆结构要先听清台词：需要 faster-whisper（.venv/bin/pip install faster-whisper）")
    log("听台词（Whisper）…")
    words = align.transcribe(video)
    sents = sentences(words)
    if not sents:
        raise FrameworkError("这条视频里没听到说话（纯音乐或无旁白的视频拆不出台词结构）")
    log(f"{len(sents)} 句；找镜头切换…")
    cuts = _cuts(video)
    m = metrics(sents, cuts, total)
    zh = m["language"] == "zh"
    parts = chunks(sents)
    log("分结构块（本地模型）…")
    made = _llm_blocks(parts, info.get("title", ""), zh)
    how = "llm"
    if made is None:
        made, how = _time_blocks(parts, zh), "time"
    made["blocks"] = split_hook(made["blocks"], parts, zh)
    beats = []
    for b in made["blocks"]:
        start, end = parts[b["from"]]["start"], parts[b["to"]]["end"]
        beats.append({"name": b["name"], "start": round(start, 1), "end": round(end, 1), "seconds": round(end - start, 1),
                      "role": b["role"], "technique": b["technique"],
                      "excerpt": " ".join(p["text"] for p in parts[b["from"]:b["to"] + 1])[:120]})
    fw = {"ref": {k: info.get(k) for k in ("id", "title", "url", "platform", "author", "views")},
          "name": made["name"] or (f"参考：{info.get('title', '')[:14]}" if zh else f"Ref: {info.get('title', '')[:24]}"),
          "about": made["about"], "made_by": how, "metrics": m, "beats": beats, "cuts": cuts,
          "template": f"ref-{ref_id}"}
    (folder / "framework.json").write_text(json.dumps(fw, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "transcript.json").write_text(json.dumps(sents, ensure_ascii=False, indent=1), encoding="utf-8")
    to_template(fw)
    log(f"完成：{len(beats)} 块" + ("（没有本地模型，按时间粗分）" if how == "time" else ""))
    return fw


def to_template(fw: dict) -> structure.Template:
    """The framework as a structure template: blocks become beats with their share of the runtime."""
    total = sum(b["seconds"] for b in fw["beats"]) or 1.0
    beats = []
    for i, b in enumerate(fw["beats"]):
        role = b["role"] + (f"（手法：{b['technique']}）" if b.get("technique") and fw["metrics"]["language"] == "zh"
                            else f" (device: {b['technique']})" if b.get("technique") else "")
        beats.append(structure.Beat(
            id=f"b{i + 1}", name=b["name"], role=role, share=round(max(0.03, b["seconds"] / total), 3),
            min_seconds=round(max(5.0, min(20.0, b["seconds"] * 0.5)), 1),
            # the opening block keeps its job at any length: never longer than the hook limit
            max_seconds=round(min(structure.HOOK_SECONDS, max(6.0, b["seconds"])), 1) if i == 0 else None))
    m = fw["metrics"]
    about = fw.get("about") or ""
    about = (about + " · " if about else "") + (
        f"原片 {m['seconds']:.0f} 秒，{m['pace']} {m['pace_unit']}，平均 {m['shot_seconds']} 秒一个镜头"
        if m["language"] == "zh" else f"original {m['seconds']:.0f} s, {m['pace']} {m['pace_unit']}, a shot every {m['shot_seconds']} s")
    t = structure.Template(id=fw["template"], name=fw["name"], about=about, beats=beats)
    structure.save_user_template(t, {"source": fw["ref"], "metrics": m})
    return t


def load(ref_id: str) -> dict | None:
    f = references.folder_of(ref_id) / "framework.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
