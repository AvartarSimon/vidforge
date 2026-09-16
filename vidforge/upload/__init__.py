"""Upload targets. Pure helpers (description/chapters) live here; the API client in youtube.py."""

from __future__ import annotations

import json
from pathlib import Path

from ..project import Project


def chapters_text(timeline: list[dict], min_seconds: int = 10) -> str:
    """YouTube chapter list: first at 00:00, >= 3 entries, each >= 10 s — otherwise YouTube
    ignores them. Too-short segments are merged into the previous chapter."""
    rows: list[tuple[int, str]] = []
    for t in timeline:
        start = int(t["start"])
        label = t.get("label") or t["id"].replace("_", " ").replace("-", " ").capitalize()
        if rows and start - rows[-1][0] < min_seconds:
            continue
        rows.append((start, label))
    if len(rows) < 3:
        return ""
    rows[0] = (0, rows[0][1])
    return "\n".join(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d} {label}" if s >= 3600
                     else f"{s // 60:02d}:{s % 60:02d} {label}" for s, label in rows)


def build_description(project: Project, build_dir: Path) -> str:
    """description = project.youtube.description + chapters + credits, capped at YouTube's 5000 chars."""
    parts = [project.youtube.description.strip()]
    tl = build_dir / "timeline.json"
    if tl.exists():
        ch = chapters_text(json.loads(tl.read_text(encoding="utf-8")))
        if ch:
            parts.append("Chapters:\n" + ch)
    credits = build_dir / "credits.txt"
    if credits.exists():
        parts.append(credits.read_text(encoding="utf-8").strip())
    text = "\n\n".join(p for p in parts if p)
    return text[:4990]
