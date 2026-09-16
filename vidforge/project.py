"""project.json schema: dataclasses + loader with validation.

A project is a *type-free* description of one video: metadata, voice, output
format, background music, subtitle style, and an ordered list of segments.
Each segment = the narration text for that segment + one image + a camera move.
Durations are never written by hand — they come from the synthesized audio.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "none")


class ProjectError(ValueError):
    pass


ASSET_PREFIXES = ("pexels:",)


@dataclass
class Segment:
    id: str
    text: str
    image: Path | None = None        # absolute after load / after asset resolution
    video: Path | None = None        # a video background instead of a still (looped/trimmed to the narration)
    source: str | None = None        # unresolved asset spec, e.g. "pexels:mount tambora volcano"
    source_kind: str = "image"       # what `source` should fetch: image | video
    motion: str = "zoom_in"
    pause_after: float = 0.5         # seconds of silence appended after the narration
    voice: str | None = None         # override the project voice for this segment
    label: str | None = None         # chapter name (defaults to a prettified id)
    remotion: RemotionSpec | None = None   # animated graphics instead of image/video

    @property
    def needs_asset(self) -> bool:
        return self.image is None and self.video is None and self.remotion is None


@dataclass
class RemotionSpec:
    composition: str                 # TitleCard | Timeline | BarChart
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class TtsConfig:
    provider: str = "edge"           # edge | elevenlabs
    model: str = "eleven_multilingual_v2"
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speaker_boost: bool = True


@dataclass
class YouTubeConfig:
    title: str | None = None         # defaults to project.title
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: int = 27            # 27 Education, 22 People & Blogs, 28 Science & Technology, 24 Entertainment
    privacy: str = "private"         # private | unlisted | public (public needs an audited OAuth app)
    playlist_id: str | None = None
    caption_name: str | None = None


@dataclass
class Bgm:
    file: Path
    volume_db: float = -18.0
    fade_out: float = 3.0


@dataclass
class SubtitleStyle:
    burn: bool = False               # burn into the video (else only .srt is produced)
    max_chars: int = 42              # per cue line
    font: str = "Arial"
    font_size: int = 22
    margin_v: int = 48


@dataclass
class Project:
    title: str
    segments: list[Segment]
    root: Path                       # directory of project.json; relative paths resolve here
    language: str = "en"
    voice: str = "en-US-AndrewNeural"
    rate: str = "+0%"                # edge-tts rate, e.g. "-5%", "+10%"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    motion_amount: float = 0.15      # zoom factor / pan distance as a fraction of the frame
    supersample: int = 2             # zoompan works on a supersampled frame to avoid jitter
    out_dir: Path = Path("build")
    bgm: Bgm | None = None
    subtitles: SubtitleStyle = field(default_factory=SubtitleStyle)
    thumbnail_text: str | None = None
    tts: TtsConfig = field(default_factory=TtsConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def build_dir(self) -> Path:
        return self.out_dir if self.out_dir.is_absolute() else self.root / self.out_dir


def _req(d: dict, key: str, ctx: str) -> Any:
    if key not in d:
        raise ProjectError(f"{ctx}: missing required field '{key}'")
    return d[key]


_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def localize(obj: Any, lang: str, fallback: str, langs: set[str]) -> Any:
    """Resolve {"en": "...", "zh": "..."} dictionaries anywhere inside `obj` to one language.

    A dict counts as localized text only when every key is one of the project's languages,
    so ordinary prop objects are left alone.
    """
    if isinstance(obj, dict):
        if obj and all(isinstance(k, str) and k in langs for k in obj):
            return obj.get(lang, obj.get(fallback, next(iter(obj.values()))))
        return {k: localize(v, lang, fallback, langs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(v, lang, fallback, langs) for v in obj]
    return obj


def _apply_variant(data: dict, lang: str) -> dict:
    """Overlay variants[lang] onto the top-level document (one level deep for dict fields)."""
    variant = (data.get("variants") or {}).get(lang)
    if variant is None and lang != data.get("language", "en"):
        raise ProjectError(f"no variants['{lang}'] in project.json — add at least {{\"voice\": …}} for that language")
    out = dict(data)
    out["language"] = lang
    out.setdefault("out_dir", "build")
    out["out_dir"] = (variant or {}).get("out_dir", f"build_{lang}")
    for k, v in (variant or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "variants":
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def load(path: str | Path, lang: str | None = None) -> Project:
    """Load project.json. `lang` selects a language variant: segment `text_<lang>` /
    `label_<lang>`, `variants[lang]` overrides, and localized Remotion props."""
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "project.json"
    if not path.exists():
        raise ProjectError(f"project file not found: {path}")
    root = path.parent
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    base_lang = data.get("language", "en")
    langs = {base_lang, *(data.get("variants") or {}).keys()}
    if lang and not _LANG_RE.match(lang):
        raise ProjectError(f"bad language code '{lang}'")
    if lang and lang != base_lang:
        data = _apply_variant(data, lang)
    lang = lang or base_lang
    text_key = "text" if lang == base_lang else f"text_{lang}"
    label_key = "label" if lang == base_lang else f"label_{lang}"
    missing: list[str] = []

    def resolve(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else (root / q)

    segments: list[Segment] = []
    seen: set[str] = set()
    for i, s in enumerate(_req(data, "segments", "project")):
        ctx = f"segments[{i}]"
        sid = str(_req(s, "id", ctx))
        if sid in seen:
            raise ProjectError(f"{ctx}: duplicate segment id '{sid}'")
        seen.add(sid)
        _req(s, "text", ctx)
        text = str(s.get(text_key) or "").strip()
        if not text:
            missing.append(sid)
            text = "?"
        image = video = source = remotion = None
        source_kind = "image"
        visuals = [k for k in ("image", "video", "remotion") if k in s]
        if len(visuals) != 1:
            raise ProjectError(f"{ctx}: give exactly one of 'image', 'video', 'remotion' (got {visuals or 'none'})")
        key = visuals[0]
        if key == "remotion":
            r = s["remotion"]
            if not isinstance(r, dict) or "composition" not in r:
                raise ProjectError(f"{ctx}: remotion needs {{'composition': …, 'props': {{…}}}}")
            remotion = RemotionSpec(composition=str(r["composition"]),
                                    props=localize(dict(r.get("props", {})), lang, base_lang, langs))
        else:
            spec = str(s[key])
            if spec.startswith(ASSET_PREFIXES):
                source, source_kind = spec, key
            else:
                local = resolve(spec)
                if not local.exists():
                    raise ProjectError(f"{ctx}: {key} not found: {local}")
                if key == "video":
                    video = local
                else:
                    image = local
        motion = s.get("motion", "zoom_in")
        if motion not in MOTIONS:
            raise ProjectError(f"{ctx}: motion '{motion}' not in {MOTIONS}")
        segments.append(Segment(
            id=sid, text=text, image=image, video=video, source=source, source_kind=source_kind,
            motion=motion, pause_after=float(s.get("pause_after", 0.5)), voice=s.get("voice"),
            label=s.get(label_key) or s.get("label"), remotion=remotion,
        ))
    if not segments:
        raise ProjectError("project has no segments")
    if missing:
        raise ProjectError(f"no '{text_key}' for segments: {', '.join(missing)} — "
                           f"run `vidforge i18n export --lang {lang}` to get a translation sheet")

    bgm = None
    if data.get("bgm"):
        b = data["bgm"]
        bf = resolve(_req(b, "file", "bgm"))
        if not bf.exists():
            raise ProjectError(f"bgm file not found: {bf}")
        bgm = Bgm(file=bf, volume_db=float(b.get("volume_db", -18.0)), fade_out=float(b.get("fade_out", 3.0)))

    sub = SubtitleStyle(**{k: v for k, v in data.get("subtitles", {}).items()
                           if k in SubtitleStyle.__dataclass_fields__})

    fps = int(data.get("fps", 30))
    if fps <= 0:
        raise ProjectError("fps must be > 0")

    tts = TtsConfig(**{k: v for k, v in data.get("tts", {}).items() if k in TtsConfig.__dataclass_fields__})
    if tts.provider not in ("edge", "elevenlabs"):
        raise ProjectError(f"tts.provider '{tts.provider}' not in ('edge', 'elevenlabs')")

    yt = YouTubeConfig(**{k: v for k, v in data.get("youtube", {}).items() if k in YouTubeConfig.__dataclass_fields__})
    if yt.privacy not in ("private", "unlisted", "public"):
        raise ProjectError(f"youtube.privacy '{yt.privacy}' not in (private, unlisted, public)")

    return Project(
        title=str(_req(data, "title", "project")),
        segments=segments,
        root=root,
        language=data.get("language", "en"),
        voice=data.get("voice", "en-US-AndrewNeural"),
        rate=data.get("rate", "+0%"),
        width=int(data.get("width", 1920)),
        height=int(data.get("height", 1080)),
        fps=fps,
        motion_amount=float(data.get("motion_amount", 0.15)),
        supersample=int(data.get("supersample", 2)),
        out_dir=Path(data.get("out_dir", "build")),
        bgm=bgm,
        subtitles=sub,
        thumbnail_text=data.get("thumbnail_text"),
        tts=tts,
        youtube=yt,
        raw=data,
    )


TEMPLATE: dict[str, Any] = {
    "title": "My first video",
    "language": "en",
    "voice": "en-US-AndrewNeural",
    "rate": "+0%",
    "tts": {"provider": "edge"},
    "width": 1920, "height": 1080, "fps": 30,
    "bgm": None,
    "subtitles": {"burn": False, "max_chars": 42, "font": "Arial", "font_size": 22},
    "thumbnail_text": "MY FIRST\nVIDEO",
    "segments": [
        {"id": "intro", "text": "Write the narration for the first segment here.",
         "image": "assets/01.jpg", "motion": "zoom_in", "pause_after": 0.6},
        {"id": "part1", "text": "Each segment is one image plus the words spoken over it.",
         "image": "assets/02.jpg", "motion": "pan_right"},
        {"id": "part2", "text": "An image can also come from Pexels by search query (needs PEXELS_API_KEY).",
         "image": "pexels:old library books", "motion": "zoom_out"},
        {"id": "part3", "text": "Or a stock video clip, looped or trimmed to the narration.",
         "video": "pexels:ocean waves aerial"},
    ],
}
