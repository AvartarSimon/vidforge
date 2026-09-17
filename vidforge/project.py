"""project.json schema: dataclasses + loader with validation.

A project is a *type-free* description of one video: metadata, voice, output format,
background music, subtitle style, and an ordered list of segments. A segment is the
narration for one stretch of the video plus the **clips** shown while it is spoken:

    { "id": "eruption", "text": "…",
      "clips": [
        { "video": "assets/pexels/lava-123.mp4", "in": 4.0, "out": 9.5 },     // a 5.5 s slice
        { "image": "assets/commons/tambora.jpg", "motion": "zoom_in", "duration": 4 },
        { "video": "pexels:volcanic ash cloud" },                               // fetched on build
        { "remotion": { "composition": "TitleCard", "props": { "title": "1815" } } }
      ],
      "fit": "stretch" }                     // clips shorter than the narration: last clip is extended

The older single-visual forms — "image": …, "video": …, "remotion": … directly on the
segment — are still accepted and become a one-clip list. Durations are never written by
hand for the segment: the narration decides; only individual clips may carry in/out/duration.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "none")
FITS = ("stretch", "trim")
ASSET_PREFIXES = ("pexels:", "pixabay:", "commons:", "wikimedia:", "google:", "google_all:", "baidu:", "openverse:", "archive:")
QUALITIES = ("draft", "final")


class ProjectError(ValueError):
    pass


@dataclass
class RemotionSpec:
    composition: str                 # TitleCard | Timeline | BarChart
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class Clip:
    image: Path | None = None        # absolute after load / after asset resolution
    video: Path | None = None
    source: str | None = None        # unresolved asset spec, e.g. "pexels:mount tambora volcano"
    source_kind: str = "image"       # what `source` should fetch: image | video
    in_: float | None = None         # video slice start (s)
    out: float | None = None         # video slice end (s)
    duration: float | None = None    # image hold (s); None = share of what the narration leaves
    motion: str = "zoom_in"          # camera move for images
    remotion: RemotionSpec | None = None
    credit: str | None = None        # attribution text, kept in the project so credits.txt survives re-indexing

    @property
    def needs_asset(self) -> bool:
        return self.image is None and self.video is None and self.remotion is None

    @property
    def is_video(self) -> bool:
        return self.video is not None or self.remotion is not None or (self.source is not None and self.source_kind == "video")

    @property
    def slice_length(self) -> float | None:
        """Natural length of a video slice when both ends are known."""
        if self.in_ is not None and self.out is not None:
            return max(0.0, self.out - self.in_)
        return None


POSITIONS = ("top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right")


@dataclass
class Overlay:
    """Picture-in-picture layer over a segment: a still, a (muted) video slice, or the presenter avatar."""
    image: Path | None = None
    video: Path | None = None
    avatar: bool = False             # the project's digital host, lip-synced to this segment's narration
    at: float = 0.0                  # seconds after the segment starts
    duration: float | None = None    # None = until the segment ends
    in_: float | None = None         # video slice
    out: float | None = None
    position: str = "bottom-right"   # one of POSITIONS, or "x,y" as fractions of the frame (0..1)
    size: float = 0.3                # width as a fraction of the frame width
    border: bool = True
    animate: str = "slide"           # slide | fade | none
    credit: str | None = None


@dataclass
class PresenterConfig:
    """The digital host: a stylised character (Remotion 'Host', local, free) or a photoreal
    provider (HeyGen) that needs an API key and a synthetic-content disclosure."""
    provider: str = "host"           # host | heygen | none
    where: str = "none"              # none | first_last | all  — which segments get the presenter overlay by default
    position: str = "bottom-right"
    size: float = 0.28
    style: dict[str, Any] = field(default_factory=dict)     # Host: skin/hair/shirt/bg/hair_style/glasses …
    heygen_avatar_id: str | None = None


@dataclass
class Segment:
    id: str
    text: str
    clips: list[Clip] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    presenter: bool | None = None    # override PresenterConfig.where for this segment
    fit: str = "stretch"             # stretch | trim — what to do when clips are shorter than the narration
    pause_after: float = 0.5         # seconds of silence appended after the narration
    voice: str | None = None         # override the project voice for this segment
    label: str | None = None         # chapter name (defaults to a prettified id)
    alt_text: str | None = None      # the other language's narration (bilingual subtitles)

    # -- conveniences for code that only needs "the" visual (thumbnail, UI card) --------
    @property
    def first(self) -> Clip | None:
        return self.clips[0] if self.clips else None

    @property
    def image(self) -> Path | None:
        return next((c.image for c in self.clips if c.image), None)

    @property
    def video(self) -> Path | None:
        return next((c.video for c in self.clips if c.video), None)

    @property
    def remotion(self) -> RemotionSpec | None:
        return next((c.remotion for c in self.clips if c.remotion), None)

    @property
    def needs_asset(self) -> bool:
        return any(c.needs_asset for c in self.clips)


@dataclass
class TtsConfig:
    provider: str = "edge"           # edge | elevenlabs | silent (layout previews, no network)
    model: str = "eleven_multilingual_v2"
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speaker_boost: bool = True


@dataclass
class Disclosure:
    """What synthetic media the video contains — drives YouTube's altered/synthetic flag and the
    description lines required by China's 2025-09-01 AI-content labelling rules."""
    ai_voice: bool = True                 # TTS narration (vidforge default)
    ai_visuals: bool = False              # AI-generated pictures/video (not stock, not drawn charts)
    realistic_presenter: bool = False     # photoreal digital twin / face swap (HeyGen etc.)
    note: str = ""                        # extra wording

    @property
    def youtube_synthetic_flag(self) -> bool:
        # YouTube asks for the label when content could be mistaken for a real person/place/event
        return self.realistic_presenter or self.ai_visuals

    def lines(self, lang: str) -> list[str]:
        parts = []
        if lang.startswith("zh"):
            what = [w for w, on in (("配音由 AI 合成", self.ai_voice), ("部分画面由 AI 生成", self.ai_visuals), ("主持人形象为数字合成", self.realistic_presenter)) if on]
            if what:
                parts.append("本视频包含人工智能生成内容：" + "，".join(what) + "。")
        else:
            what = [w for w, on in (("AI-synthesised narration", self.ai_voice), ("AI-generated visuals", self.ai_visuals), ("a digitally synthesised presenter", self.realistic_presenter)) if on]
            if what:
                parts.append("This video contains AI-generated content: " + ", ".join(what) + ".")
        if self.note.strip():
            parts.append(self.note.strip())
        return parts


@dataclass
class YouTubeConfig:
    title: str | None = None         # defaults to project.title
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: int = 27            # 27 Education, 22 People & Blogs, 28 Science & Technology, 24 Entertainment
    privacy: str = "private"         # private | unlisted | public (public needs an audited OAuth app)
    playlist_id: str | None = None
    caption_name: str | None = None
    disclosure: Disclosure = field(default_factory=Disclosure)


@dataclass
class Bgm:
    file: Path
    volume_db: float = -18.0
    fade_out: float = 3.0
    duck: bool = True                # lower the music while the voice speaks (sidechain compression)


@dataclass
class SubtitleStyle:
    burn: bool = False               # burn into the video (else only .srt is produced)
    max_chars: int = 42              # per cue line
    font: str = "Arial"
    font_size: int = 22
    margin_v: int = 48
    style: str = "outline"           # outline | box (semi-transparent background, YouTube-style)
    bilingual: bool = False          # second line in `bilingual_lang` (learner edition)
    bilingual_lang: str = "zh"


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
    quality: str = "final"           # draft (fast preview) | final (crf 18, 2x supersample)
    encoder: str = "auto"            # auto | libx264 | h264_nvenc | h264_qsv | h264_amf | h264_videotoolbox
    motion_amount: float = 0.15      # zoom factor / pan distance as a fraction of the frame
    supersample: int | None = None   # zoompan supersampling; None = by quality (draft 1, final 2)
    transition: float = 0.0          # crossfade seconds between clips inside a segment (0 = hard cut)
    auto_title_cards: bool = False   # prepend a 3 s TitleCard to every segment that has a label (needs Remotion)
    presenter: PresenterConfig = field(default_factory=PresenterConfig)
    outro_vocab: int = 0             # learner edition: append a vocabulary card with N words (0 = off)
    normalize_audio: bool = True     # loudnorm the narration to -16 LUFS so every segment/provider sounds alike
    parallel: int = 0                # segments rendered at once; 0 = auto (cores / 2)
    out_dir: Path = Path("build")
    bgm: Bgm | None = None
    subtitles: SubtitleStyle = field(default_factory=SubtitleStyle)
    thumbnail_text: str | None = None
    tts: TtsConfig = field(default_factory=TtsConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    warnings: list[str] = field(default_factory=list)   # non-fatal advice (long segments, …)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def build_dir(self) -> Path:
        return self.out_dir if self.out_dir.is_absolute() else self.root / self.out_dir

    @property
    def effective_supersample(self) -> int:
        if self.supersample:
            return self.supersample
        return 1 if self.quality == "draft" else 2


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


def _parse_clip(c: dict, ctx: str, resolve, lang: str, base_lang: str, langs: set[str]) -> Clip:
    visuals = [k for k in ("image", "video", "remotion") if k in c]
    if len(visuals) != 1:
        raise ProjectError(f"{ctx}: a clip needs exactly one of 'image', 'video', 'remotion' (got {visuals or 'none'})")
    key = visuals[0]
    clip = Clip()
    if key == "remotion":
        r = c["remotion"]
        if not isinstance(r, dict) or "composition" not in r:
            raise ProjectError(f"{ctx}: remotion needs {{'composition': …, 'props': {{…}}}}")
        clip.remotion = RemotionSpec(composition=str(r["composition"]),
                                     props=localize(dict(r.get("props", {})), lang, base_lang, langs))
    else:
        spec = str(c[key])
        if spec.startswith(ASSET_PREFIXES):
            clip.source, clip.source_kind = spec, key
        else:
            local = resolve(spec)
            if not spec.strip() or not local.is_file():
                raise ProjectError(f"{ctx}: {key} is not a file: {spec!r}")
            if key == "video":
                clip.video = local
            else:
                clip.image = local
    if "in" in c or "out" in c:
        if key != "video":
            raise ProjectError(f"{ctx}: in/out only apply to video clips")
        clip.in_ = float(c.get("in", 0.0))
        clip.out = float(c["out"]) if "out" in c else None
        if clip.in_ < 0 or (clip.out is not None and clip.out <= clip.in_):
            raise ProjectError(f"{ctx}: need 0 <= in < out (got in={clip.in_}, out={clip.out})")
    if "duration" in c:
        clip.duration = float(c["duration"])
        if clip.duration <= 0:
            raise ProjectError(f"{ctx}: duration must be > 0")
    clip.motion = c.get("motion", "zoom_in")
    if clip.motion not in MOTIONS:
        raise ProjectError(f"{ctx}: motion '{clip.motion}' not in {MOTIONS}")
    clip.credit = c.get("credit")
    return clip


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
    narr_lang = data.get("text_from") or lang            # variant may narrate in another language (en-zh)
    text_key = "text" if narr_lang == base_lang else f"text_{narr_lang}"
    label_key = "label" if narr_lang == base_lang else f"label_{narr_lang}"
    if narr_lang != lang:
        data["language"] = narr_lang
    sub_cfg = data.get("subtitles") or {}
    alt_lang = sub_cfg.get("bilingual_lang", "zh") if sub_cfg.get("bilingual") else None
    alt_key = None if not alt_lang else ("text" if alt_lang == base_lang else f"text_{alt_lang}")
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

        clips: list[Clip] = []
        legacy = [k for k in ("image", "video", "remotion") if k in s]
        if "clips" in s and legacy:
            raise ProjectError(f"{ctx}: use either 'clips' or a single image/video/remotion, not both")
        if "clips" in s:
            if not isinstance(s["clips"], list):
                raise ProjectError(f"{ctx}: clips must be a list")
            for j, c in enumerate(s["clips"]):
                clips.append(_parse_clip(c, f"{ctx}.clips[{j}]", resolve, lang, base_lang, langs))
        elif legacy:
            one = {k: s[k] for k in legacy}
            if "motion" in s:
                one["motion"] = s["motion"]
            clips.append(_parse_clip(one, ctx, resolve, lang, base_lang, langs))
        else:
            raise ProjectError(f"{ctx}: segment has no visual — add 'clips' or an image/video/remotion")

        overlays: list[Overlay] = []
        for j, o in enumerate(s.get("overlays") or []):
            octx = f"{ctx}.overlays[{j}]"
            ov = Overlay()
            kinds = [k for k in ("image", "video", "avatar") if o.get(k)]
            if len(kinds) != 1:
                raise ProjectError(f"{octx}: an overlay needs exactly one of image / video / avatar")
            if kinds[0] == "avatar":
                ov.avatar = True
            else:
                local = resolve(str(o[kinds[0]]))
                if not local.is_file():
                    raise ProjectError(f"{octx}: {kinds[0]} is not a file: {o[kinds[0]]!r}")
                setattr(ov, kinds[0], local)
            ov.at = float(o.get("at", 0.0))
            ov.duration = float(o["duration"]) if o.get("duration") is not None else None
            ov.in_ = float(o["in"]) if "in" in o else None
            ov.out = float(o["out"]) if "out" in o else None
            ov.position = str(o.get("position", "bottom-right"))
            if ov.position not in POSITIONS and not re.fullmatch(r"\s*[0-9.]+\s*,\s*[0-9.]+\s*", ov.position):
                raise ProjectError(f"{octx}: position must be one of {POSITIONS} or 'x,y' fractions")
            ov.size = float(o.get("size", 0.3))
            if not 0.05 <= ov.size <= 1.0:
                raise ProjectError(f"{octx}: size must be between 0.05 and 1.0 (fraction of frame width)")
            ov.border = bool(o.get("border", True))
            ov.animate = str(o.get("animate", "slide"))
            ov.credit = o.get("credit")
            overlays.append(ov)

        fit = s.get("fit", "stretch")
        if fit not in FITS:
            raise ProjectError(f"{ctx}: fit '{fit}' not in {FITS}")
        if float(s.get("pause_after", 0.5)) < 0:
            raise ProjectError(f"{ctx}: pause_after must be >= 0")
        segments.append(Segment(
            id=sid, text=text, clips=clips, fit=fit,
            pause_after=float(s.get("pause_after", 0.5)), voice=s.get("voice"),
            label=s.get(label_key) or s.get("label"), overlays=overlays,
            alt_text=(str(s.get(alt_key) or "").strip() or None) if alt_key else None,
            presenter=(bool(s["presenter"]) if "presenter" in s else None),
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
        bgm = Bgm(file=bf, volume_db=float(b.get("volume_db", -18.0)), fade_out=float(b.get("fade_out", 3.0)),
                  duck=bool(b.get("duck", True)))

    sub = SubtitleStyle(**{k: v for k, v in data.get("subtitles", {}).items()
                           if k in SubtitleStyle.__dataclass_fields__})

    fps = int(data.get("fps", 30))
    if fps <= 0:
        raise ProjectError("fps must be > 0")
    quality = data.get("quality", "final")
    if quality not in QUALITIES:
        raise ProjectError(f"quality '{quality}' not in {QUALITIES}")

    tts = TtsConfig(**{k: v for k, v in data.get("tts", {}).items() if k in TtsConfig.__dataclass_fields__})
    if tts.provider not in ("edge", "elevenlabs", "silent"):
        raise ProjectError(f"tts.provider '{tts.provider}' not in ('edge', 'elevenlabs', 'silent')")

    pres = PresenterConfig(**{k: v for k, v in (data.get("presenter") or {}).items() if k in PresenterConfig.__dataclass_fields__})
    if pres.provider not in ("host", "heygen", "none") or pres.where not in ("none", "first_last", "all"):
        raise ProjectError("presenter.provider must be host|heygen|none and presenter.where none|first_last|all")

    yt_raw = dict(data.get("youtube", {}))
    disc_raw = yt_raw.pop("disclosure", {}) or {}
    yt = YouTubeConfig(**{k: v for k, v in yt_raw.items() if k in YouTubeConfig.__dataclass_fields__})
    yt.disclosure = Disclosure(**{k: v for k, v in disc_raw.items() if k in Disclosure.__dataclass_fields__})
    if pres.provider == "heygen":
        yt.disclosure.realistic_presenter = True                 # photoreal twin always discloses
    if yt.privacy not in ("private", "unlisted", "public"):
        raise ProjectError(f"youtube.privacy '{yt.privacy}' not in (private, unlisted, public)")

    warnings = [f"segment '{s.id}' is {len(s.text)} characters — ElevenLabs caps a request at 5000 and "
                f"subtitles/pictures pace better under ~600; consider splitting" for s in segments if len(s.text) > 2500]

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
        quality=quality,
        encoder=data.get("encoder", "auto"),
        motion_amount=float(data.get("motion_amount", 0.15)),
        supersample=int(data["supersample"]) if data.get("supersample") else None,
        transition=float(data.get("transition", 0.0)),
        auto_title_cards=bool(data.get("auto_title_cards", False)),
        outro_vocab=int(data.get("outro_vocab", 0) or 0),
        presenter=pres,
        normalize_audio=bool(data.get("normalize_audio", True)),
        parallel=int(data.get("parallel", 0)),
        out_dir=Path(data.get("out_dir", "build")),
        bgm=bgm,
        subtitles=sub,
        thumbnail_text=data.get("thumbnail_text"),
        tts=tts,
        youtube=yt,
        warnings=warnings,
        raw=data,
    )


TEMPLATE: dict[str, Any] = {
    "title": "My first video",
    "language": "en",
    "voice": "en-US-AndrewNeural",
    "rate": "+0%",
    "tts": {"provider": "edge"},
    "width": 1920, "height": 1080, "fps": 30, "quality": "final",
    "bgm": None,
    "subtitles": {"burn": False, "max_chars": 42, "font": "Arial", "font_size": 22},
    "thumbnail_text": "MY FIRST\nVIDEO",
    "youtube": {"description": "What this video is about, sources, links.", "tags": ["history"],
                "category_id": 27, "privacy": "private"},
    "variants": {
        "zh": {"voice": "zh-CN-YunxiNeural", "rate": "-5%", "title": "我的第一条视频", "thumbnail_text": "我的第一条\n视频",
               "subtitles": {"font": "Microsoft YaHei", "font_size": 24},
               "youtube": {"description": "中文简介", "tags": ["历史"]}},
        "en-zh": {"text_from": "en", "title": "My first video（双语学习版）",
                  "subtitles": {"burn": True, "bilingual": True, "bilingual_lang": "zh", "style": "box", "font": "Microsoft YaHei", "font_size": 22},
                  "outro_vocab": 8, "youtube": {"description": "英文原声 + 中英双语字幕 + 本集词汇", "tags": ["英语学习"]}}
    },
    "segments": [
        {"id": "intro", "text": "Write the narration for the first segment here.",
         "text_zh": "在这里写第一段的旁白。",
         "clips": [{"image": "assets/01.jpg", "motion": "zoom_in"}], "pause_after": 0.6},
        {"id": "part1", "text": "A segment can show several clips: a slice of a stock video, then a still.",
         "clips": [{"video": "pexels:ocean waves aerial", "in": 2, "out": 7},
                   {"image": "assets/02.jpg", "motion": "pan_right"}]},
        {"id": "part2", "text": "Or an animated title card.",
         "remotion": {"composition": "TitleCard", "props": {"title": "Part 2"}}},
    ],
}
