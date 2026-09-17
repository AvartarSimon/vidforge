"""Your own footage library: record once, look freshly recorded every time.

    ~/.vidforge/me/                       (or <project>/assets/me/ to override per project)
        backyard_glasses_talking_01.mp4   tags come from the file name: words split on _ - space;
        study_bluejacket_02.mp4           "talking" / "speak" marks a speaking take, else silent B-roll
        beach_walk_wide.mp4

`pick(tags, talking)` returns the least-used clip matching every requested tag (falls back to
any tag, then any clip), so the same shot is not repeated video after video. Usage counts live
in index.json next to the files.

Silent takes (you listening, walking, looking at the horizon) need nothing else and carry no
disclosure obligation. Speaking takes are lip-synced to the narration by lipsync.py and are
realistic synthetic media -> the disclosure flag is set automatically.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import ffmpeg

GLOBAL_DIR = Path.home() / ".vidforge" / "me"
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".m4v")
TALK_WORDS = {"talking", "talk", "speak", "speaking", "说话", "讲"}
_SPLIT = re.compile(r"[\s_\-.]+")


def library_dir(project_root: Path | None = None) -> Path:
    if project_root and (project_root / "assets" / "me").is_dir():
        return project_root / "assets" / "me"
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return GLOBAL_DIR


def tags_from_name(name: str) -> tuple[list[str], bool]:
    tokens = [t.lower() for t in _SPLIT.split(Path(name).stem) if t and not t.isdigit()]
    talking = any(t in TALK_WORDS for t in tokens)
    return [t for t in tokens if t not in TALK_WORDS], talking


class MeLibrary:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.index_path = self.folder / "index.json"
        self.data: dict = {"files": {}}
        if self.index_path.exists():
            try:
                self.data = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

    def scan(self) -> list[dict]:
        """Refresh index.json from the files on disk (keeps usage counts and manual tags)."""
        files = self.data.setdefault("files", {})
        seen = set()
        for f in sorted(self.folder.iterdir()) if self.folder.exists() else []:
            if f.suffix.lower() not in VIDEO_EXT:
                continue
            seen.add(f.name)
            rec = files.get(f.name) or {}
            tags, talking = tags_from_name(f.name)
            rec.setdefault("tags", tags)
            rec.setdefault("talking", talking)
            rec.setdefault("uses", 0)
            if rec.get("size") != f.stat().st_size:
                try:
                    rec["duration"] = round(ffmpeg.duration(f), 2)
                except ffmpeg.FfmpegError:
                    rec["duration"] = None
                rec["size"] = f.stat().st_size
            files[f.name] = rec
        for gone in [n for n in files if n not in seen]:
            del files[gone]
        self.save()
        return self.items()

    def items(self) -> list[dict]:
        return [{"name": n, **r} for n, r in self.data.get("files", {}).items()]

    def set_tags(self, name: str, tags: list[str], talking: bool | None = None) -> None:
        rec = self.data["files"].setdefault(name, {"uses": 0})
        rec["tags"] = [t.lower() for t in tags if t]
        if talking is not None:
            rec["talking"] = talking
        self.save()

    def pick(self, tags: list[str] | None, talking: bool, min_seconds: float = 0.0, avoid: set[str] | None = None) -> Path | None:
        want = {t.lower() for t in (tags or []) if t}
        pool = [i for i in self.items() if bool(i.get("talking")) == talking and i["name"] not in (avoid or set())]
        exact = [i for i in pool if want <= set(i.get("tags", []))]
        some = [i for i in pool if want & set(i.get("tags", []))]
        for cands in (exact, some, pool):
            if cands:
                long_enough = [c for c in cands if (c.get("duration") or 0) >= min_seconds] or cands
                best = sorted(long_enough, key=lambda c: (c.get("uses", 0), c["name"]))[0]
                return self.folder / best["name"]
        return None

    def record_use(self, path: Path) -> None:
        rec = self.data["files"].get(Path(path).name)
        if rec is not None:
            rec["uses"] = rec.get("uses", 0) + 1
            rec["last_used"] = time.strftime("%Y-%m-%d")
            self.save()

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
