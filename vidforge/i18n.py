"""Translation sheets: export what needs translating, import the filled sheet back.

    vidforge i18n export my-video --lang zh   ->  my-video/i18n_zh.json
    (translate the empty strings — paste the file into a chat with Claude, or by hand)
    vidforge i18n import my-video --lang zh   ->  writes text_zh / label_zh into project.json,
                                                  and title/thumbnail_text/description into variants.zh

The sheet lists only what is still empty, so re-exporting after new segments were added
gives a short file. project.json is rewritten with indent=2 and keys preserved in order.
"""

from __future__ import annotations

import json
from pathlib import Path

TOP_FIELDS = ("title", "thumbnail_text")
YT_FIELDS = ("title", "description")


def _project_path(project: str | Path) -> Path:
    p = Path(project)
    return p / "project.json" if p.is_dir() else p


def export(project: str | Path, lang: str) -> Path:
    pj = _project_path(project)
    data = json.loads(pj.read_text(encoding="utf-8"))
    variant = (data.get("variants") or {}).get(lang) or {}
    sheet: dict = {"_lang": lang, "_source_language": data.get("language", "en"), "project": {}, "youtube": {}, "segments": {}}
    for f in TOP_FIELDS:
        if data.get(f) and not variant.get(f):
            sheet["project"][f] = {"source": data[f], lang: ""}
    yt_v = variant.get("youtube") or {}
    for f in YT_FIELDS:
        src = (data.get("youtube") or {}).get(f)
        if src and not yt_v.get(f):
            sheet["youtube"][f] = {"source": src, lang: ""}
    for s in data["segments"]:
        entry = {}
        if not s.get(f"text_{lang}"):
            entry["text"] = {"source": s["text"], lang: ""}
        if s.get("label") and not s.get(f"label_{lang}"):
            entry["label"] = {"source": s["label"], lang: ""}
        if entry:
            sheet["segments"][s["id"]] = entry
    out = pj.parent / f"i18n_{lang}.json"
    out.write_text(json.dumps(sheet, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def import_(project: str | Path, lang: str) -> tuple[int, list[str]]:
    """Merge a filled sheet into project.json. Returns (fields written, ids still empty)."""
    pj = _project_path(project)
    sheet_path = pj.parent / f"i18n_{lang}.json"
    if not sheet_path.exists():
        raise FileNotFoundError(f"{sheet_path} not found — run `vidforge i18n export --lang {lang}` first")
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    data = json.loads(pj.read_text(encoding="utf-8"))
    variants = data.setdefault("variants", {})
    variant = variants.setdefault(lang, {})
    written, empty = 0, []

    def val(cell: dict) -> str:
        return (cell.get(lang) or "").strip()

    for f, cell in sheet.get("project", {}).items():
        if val(cell):
            variant[f] = val(cell); written += 1
    for f, cell in sheet.get("youtube", {}).items():
        if val(cell):
            variant.setdefault("youtube", {})[f] = val(cell); written += 1
    by_id = {s["id"]: s for s in data["segments"]}
    for sid, entry in sheet.get("segments", {}).items():
        seg = by_id.get(sid)
        if seg is None:
            continue
        for field, cell in entry.items():
            if val(cell):
                seg[f"{field}_{lang}"] = val(cell); written += 1
            elif field == "text":
                empty.append(sid)
    if "voice" not in variant:
        variant["voice"] = _default_voice(lang)
    pj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return written, empty


def _default_voice(lang: str) -> str:
    return {"zh": "zh-CN-YunxiNeural", "en": "en-US-AndrewNeural", "ja": "ja-JP-KeitaNeural",
            "de": "de-DE-ConradNeural", "fr": "fr-FR-HenriNeural", "es": "es-ES-AlvaroNeural"}.get(lang, "en-US-AndrewNeural")
