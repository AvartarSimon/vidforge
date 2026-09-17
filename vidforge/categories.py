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


def list_categories() -> list[dict]:
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
