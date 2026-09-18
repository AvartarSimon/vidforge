"""Named presets ("分类"): per-topic-vertical settings and reference notes, reused across
projects instead of retyping platform lists, source links, and banned-keyword rules every time
you start a new video in the same lane (e.g. "中国古代历史人文" vs. "FND").

Stored as one JSON file per category under ~/.vidforge/categories/<id>.json — plain files, not
a database. That is a deliberate choice, not a shortcut: there is no concurrent multi-writer
load here (one person, one machine), no relational query need (it's "give me this one blob by
id"), and a flat JSON file is trivially git-friendly, human-editable, diffable, and — the actual
ask — one-click to export/import/merge: `vidforge category export` writes one file with every
category, `import` reads it back and either replaces or merges. A Postgres-in-docker-compose
setup would add a service to keep running, a schema to migrate, and a backup story to build —
for something that is, in full, "read this JSON file, maybe write it back." If this ever needs
real multi-user sharing or querying, that's the point to reconsider; it doesn't yet.

A category record is intentionally free-form beyond `name`/`id` — the fields the user actually
listed (platform list, reference accounts, source library, tags, insights on what works, and for
a "把关" category like FND: banned keywords / platform restrictions) vary a lot per vertical, so
the UI edits it as JSON rather than a fixed form.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

DIR = Path.home() / ".vidforge" / "categories"


class CategoryError(RuntimeError):
    pass


def _slug(name: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", name.strip()).strip("-").lower()
    return s or f"category-{int(time.time())}"


# Shipped so a brand-new install has something to look at instead of an empty list — three
# verticals chosen to show off the different fields a category can use (plain notes/sources,
# a bilingual-learning default, and FND-style banned-keyword/platform gating). Purely a starting
# point: edit or delete freely — the seed only ever runs on the very first list_categories()
# call for a given DIR (tracked by a ".seeded" marker inside it), so deleting them later never
# brings them back.
_DEFAULT_CATEGORIES: list[dict] = [
    {
        "name": "历史科普",
        "topic_notes": "面向大众的历史/科学解说，15 分钟左右，一个反差/悬念开场，中段按时间线或因果链展开，结尾留钩子引出下一集。",
        "insights": "标题带具体数字或年份的完播率更高；避免堆砌人名年代，先给一个让人有画面感的场景。",
        "platforms": ["YouTube"],
        "sources": [{"name": "Wikimedia Commons", "url": "https://commons.wikimedia.org"},
                     {"name": "Internet Archive", "url": "https://archive.org"}],
        "tags": ["历史", "科普"],
        "banned_keywords": [],
        "platform_restrictions": "",
        "defaults": {"voice": "en-US-AndrewNeural", "tts_provider": "edge", "language": "en"},
    },
    {
        "name": "英语学习",
        "topic_notes": "英文原声解说 + 中英双语字幕 + 片尾词汇卡，发在英语学习相关分区/标签下。",
        "insights": "语速比主频道慢 5%，句子拆得更短；词汇卡选中高频但不算基础的词最受欢迎。",
        "platforms": ["YouTube", "B站"],
        "sources": [],
        "tags": ["英语学习", "双语字幕"],
        "banned_keywords": [],
        "platform_restrictions": "",
        "defaults": {"voice": "en-US-AndrewNeural", "tts_provider": "edge", "language": "en",
                     "subtitles_bilingual": True},
    },
    {
        "name": "时政资讯 FND",
        "topic_notes": "时效性新闻/时政类解说，需要严格核实信源，只叙述已被多方证实的事实，不做立场性推断。",
        "insights": "标题避免耸动词；描述里注明信源链接，减少争议投诉。",
        "platforms": ["YouTube"],
        "sources": [{"name": "Reuters", "url": "https://www.reuters.com"},
                     {"name": "AP News", "url": "https://apnews.com"}],
        "tags": ["时政", "新闻"],
        "banned_keywords": ["未经证实", "据传", "小道消息"],
        "platform_restrictions": "涉及在世政治人物的负面表述前必须有至少两个独立信源；不做选举结果预测。",
        "defaults": {"voice": "en-US-AndrewNeural", "tts_provider": "edge", "language": "en"},
    },
]


def seed_defaults() -> None:
    """Create the starter categories the first time this DIR is ever touched (i.e. the
    directory itself doesn't exist yet) — a genuinely fresh install, not just "currently has
    zero categories" (which is also true right after deleting your last one, and shouldn't
    bring the seed back). Reads `DIR` at call time (not a module-level constant) so tests that
    mock.patch.object(cat, "DIR", ...) seed into their own temp directory, never the real
    ~/.vidforge/categories/."""
    if DIR.exists():
        return
    DIR.mkdir(parents=True)
    for record in _DEFAULT_CATEGORIES:
        save(dict(record))


def list_categories() -> list[dict]:
    seed_defaults()
    DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return sorted(out, key=lambda c: c.get("name", ""))


def load(cid: str) -> dict | None:
    f = DIR / f"{Path(cid).name}.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save(record: dict) -> dict:
    name = str(record.get("name") or "").strip()
    if not name:
        raise CategoryError("分类需要一个名字")
    cid = str(record.get("id") or "").strip() or _slug(name)
    record = {**record, "id": cid, "name": name, "updated": time.strftime("%Y-%m-%d %H:%M")}
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{cid}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def delete(cid: str) -> None:
    f = DIR / f"{Path(cid).name}.json"
    if f.is_file():
        f.unlink()


def export_all() -> dict:
    """One JSON document with every category — hand it to `import_bundle` on any machine."""
    return {"exported": time.strftime("%Y-%m-%d %H:%M"), "categories": list_categories()}


def import_bundle(data: dict, merge: bool = True) -> list[dict]:
    """merge=True (default): add/overwrite by id, keep everything else that's already there.
    merge=False: replace the whole set with exactly what's in the bundle."""
    cats = data.get("categories") or []
    if not isinstance(cats, list):
        raise CategoryError("导入文件格式不对：需要 {\"categories\": [...]}")
    if not merge:
        DIR.mkdir(parents=True, exist_ok=True)
        for f in DIR.glob("*.json"):
            f.unlink()
    return [save(c) for c in cats if isinstance(c, dict)]
