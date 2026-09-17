# vidforge

> 中文分步指南：**[QUICKSTART.zh.md](QUICKSTART.zh.md)**

Script-to-video assembly line for narrated explainer videos (history, tech, …).
One `project.json` describes a video, `vidforge build` renders it; `vidforge ui` opens a local web page
to edit segments, swap visuals, proof-listen each segment and watch the build.

```
project.json ──► edge-tts per segment ──► word timings ──► final.srt
      │                 │
      │                 └──► Ken Burns clip per segment (ffmpeg zoompan)
      │                              │
      └── images, motion ────────────┴──► concat ──► + BGM, optional burned subs ──► final.mp4
                                                                                  └──► thumbnail.jpg
```

The default path needs **no API key**: Microsoft Edge neural voices (free, unofficial), your own
images, ffmpeg. Optional providers, enabled by a key in `.env` (see `.env.example`):

| Provider | Key | Turns on |
|---|---|---|
| ElevenLabs | `ELEVENLABS_API_KEY` | `"tts": {"provider": "elevenlabs", "model": "eleven_multilingual_v2"}`, `voice` = name or voice_id; word timings from `/with-timestamps` |
| Pexels | `PEXELS_API_KEY` | `"image": "pexels:<query>"` / `"video": "pexels:<query>"` per segment; downloads to `assets/pexels/`, indexed so rebuilds are offline; `build/credits.txt` |
| Remotion | Node.js + `vidforge remotion setup` | `"remotion": {"composition": "TitleCard" / "Timeline" / "BarChart", "props": {…}}` segments — animated graphics at exactly the narration length |
| YouTube | `~/.vidforge/client_secret.json` + `pip install -e .[youtube]` | `vidforge upload <project>`: video + description (chapters + credits) + thumbnail + captions + playlist |

## Install

```bash
# ffmpeg
winget install Gyan.FFmpeg          # Windows
brew install ffmpeg                 # macOS

# vidforge (from this folder)
python -m pip install -e .
vidforge doctor                     # verifies ffmpeg + edge-tts
```

## Use

```bash
vidforge demo demo1                 # runnable sample: 4 segments, placeholder images
vidforge build demo1                # -> demo1/build/final.mp4, final.srt, thumbnail.jpg

vidforge init my-video              # empty project.json + assets/
vidforge voices --lang en-US        # pick a voice (zh-CN-YunxiNeural, en-US-AndrewNeural, …)
vidforge build my-video --only-tts  # synthesize narration only, proof-listen before rendering
vidforge build my-video --burn      # burn subtitles (otherwise final.srt is a sidecar for YouTube upload)
vidforge assets my-video            # fetch pexels:… assets only, review them before a long render
vidforge voices --provider elevenlabs
vidforge ui my-video                # local web UI (127.0.0.1:8765): edit, proof-listen, build, play the result
vidforge remotion setup|studio      # animated segments: install once / open Remotion Studio
vidforge upload my-video [--lang zh] [--privacy unlisted] [--publish-at 2026-10-01T09:00:00Z]
vidforge i18n export my-video --lang zh   # translation sheet -> fill -> `i18n import` -> `build --lang zh`
python -m unittest discover -s tests      # 44 tests; e2e needs pip install -e .[dev]
```

## project.json

```jsonc
{
  "title": "The Year Without a Summer",
  "language": "en",
  "voice": "en-US-AndrewNeural",      // edge-tts voice, or an ElevenLabs voice name/id; per-segment "voice" overrides
  "rate": "-3%",                       // speaking rate (ElevenLabs: mapped to speed 0.7–1.2)
  "tts": { "provider": "edge" },       // or elevenlabs + model/stability/similarity_boost/style
  "width": 1920, "height": 1080, "fps": 30,
  "motion_amount": 0.15,               // zoom factor / pan distance (fraction of frame)
  "bgm": { "file": "assets/bgm.mp3", "volume_db": -18, "fade_out": 3 },   // or null
  "subtitles": { "burn": false, "max_chars": 42, "font": "Arial", "font_size": 22 },
  "thumbnail_text": "THE YEAR\nWITHOUT A SUMMER",
  "segments": [
    { "id": "hook", "text": "In 1815, a volcano …", "image": "assets/01.jpg",
      "motion": "zoom_in", "pause_after": 0.6 },
    { "id": "farm", "text": "…", "image": "pexels:snow covered farm field" },
    { "id": "rain", "text": "…", "video": "pexels:rain on window" },  // looped/trimmed to the narration
    { "id": "tl", "label": "From eruption to famine", "text": "…", "text_zh": "…",
      "remotion": { "composition": "Timeline", "props": { "title": {"en": "From eruption", "zh": "从喷发"},
                    "events": [ { "date": "Apr 1815", "text": "Tambora erupts" } ] } } }
    // motion: zoom_in | zoom_out | pan_left | pan_right | none (stills only)
  ],
  "youtube":  { "description": "…", "tags": ["history"], "category_id": 27, "privacy": "private" },
  "variants": { "zh": { "voice": "zh-CN-YunxiNeural", "title": "…", "subtitles": { "font": "Microsoft YaHei" } } }
}
```

Durations are never typed: each segment lasts as long as its narration plus `pause_after`.

## Build output (`build/`)

| File | What |
|---|---|
| `audio/<seg>.mp3` + `.json` | narration + word timings, cached by hash of (voice, rate, text) — editing one segment re-synthesizes only that one |
| `clips/<seg>.mp4` | rendered segment |
| `merged.mp4` | all clips, narration only (drop this into DaVinci Resolve for manual finishing) |
| `final.srt` | subtitles; sentence-first, balanced line breaks; punctuation restored (edge-tts drops it) |
| `final.mp4` | + BGM, optional burned subtitles |
| `thumbnail.jpg` | 1280×720, first image darkened + outlined title |
| `timeline.json` | segment start/end — paste as YouTube chapters (also printed after the build) |

## Speed and length

Segments render in parallel; a hardware H.264 encoder (NVENC / QSV / AMF / VideoToolbox) is used
when `encoder: auto` finds one. Measured here (Intel QSV, 4 workers): a 30-minute / 40-segment
project renders in **159 s** with cached narration (258 s including first-time TTS); timeline
drift over 30 minutes is 21 ms. `quality: draft` skips supersampling and sharpening for previews;
`tools/stress.py` generates long synthetic projects. See `docs/six-hats-rounds-2026-09-17.md`.

## Roadmap

- providers: Azure TTS; Pixabay; local Flux image generation; Kling / MiniMax clips for intros
- more Remotion compositions: map with moving markers, quote card, side-by-side comparison

## Notes

- edge-tts is an unofficial endpoint. The audio cache means a finished project never depends on it again; if it breaks, swap the provider.
- Chinese subtitles omit punctuation by convention but still break at clause marks. Set `"font": "Microsoft YaHei"` (Windows) or `"PingFang SC"` (macOS) when burning.
- Everything is data: a wrong image, a typo, a different voice — edit `project.json`, rebuild; only the changed segments are re-synthesized.
