# vidforge — project notes for AI assistants

Script-to-video assembly line for narrated explainer videos: one `project.json` per video →
TTS per segment → word timings → subtitles → Ken Burns / stock video / Remotion graphics →
ffmpeg concat → `final.mp4` + thumbnail + optional YouTube upload. A local web UI drives it.
Owner: Simon (Chinese-speaking, Melbourne). Reply in Chinese; code comments in English.

Full handoff (state of every feature, decisions, known issues): `docs/handoff-mac.md`.
User-facing manual: `QUICKSTART.zh.md`. Roadmap: `docs/roadmap-v0.4-plan.md`.

## Architecture (no Docker, no database — everything is files)

| Layer | Where | Notes |
|---|---|---|
| CLI | `vidforge/cli.py` | `vidforge start|ui|build|doctor|voices|assets|upload|i18n|browser|chat|voice|me|category|remotion|shortcut` |
| Pipeline | `pipeline.py`, `render.py`, `subtitles.py`, `thumbnail.py`, `ffmpeg.py` | staged build with per-segment clip cache `build/clips/<seg>.<hash>.mp4`; encoder auto-pick (nvenc/qsv/amf/videotoolbox/libx264) |
| Project model | `project.py` (`Project`, `Segment`, `Clip`, `Overlay`) | `Clip.source` = unresolved spec `"commons:Battle of Lexington 1775"`, resolved at build or by autofill |
| Assets | `assets/` — `pexels.py`, `pixabay.py`, `wikimedia.py`, `openverse.py`, `archive.py`, `google_images.py`, `baidu.py` | `Library` = `assets/index.json` (licence, credits, picks, vision-check verdicts). `pick_many()` is what autofill uses (one search → several files, downloaded in parallel); `relevant()` (contiguous content-word bigram) + `branded()` + `blocked_host()` gate accuracy, `vision_verdict()` is the optional slow check; `normalise()` shrinks museum-sized downloads |
| TTS | `tts/` (edge-tts default, ElevenLabs, VoxCPM) | word timings drive `final.srt` |
| Local LLM | `llm.py` (Ollama, optional) | text: `qwen2.5:3b` keywords/translation/chapter names, batched `keywords_batch()`; vision: `qwen2.5vl:3b` `vision_check()` (watermark / text overlay / depicts) |
| Browser bridge | `browser/` (Playwright on the user's own Chrome/Edge profile) | types prompts into ChatGPT/Claude/DeepSeek/… web UIs for script generation; no API keys |
| Script parsing | `script_parser.py` | pasted AI text → segments; strips chatter/notes/stage directions; `language_issues()` flags mixed language |
| Web UI backend | `ui/__init__.py` (stdlib `ThreadingHTTPServer`, `/api/*`, port 8765) | `State` holds project path, build status, autofill job, background vision-check queue. `STAMP` = code mtime; a stale running copy is replaced on start |
| UI sections | `ui/react/src/components/sections/` | 视频 / 声音 / 图片 — material-centred pages beside the 5-step wizard (React UI only; the old static UI has no nav rail) |
| Web UI frontends | `ui/static/app.js` (vanilla, served by the backend — what the launchers open) **and** `ui/react/` (Vite + MUI, `npm run dev` on 5175 proxying to 8765) | **Every UI change must be made in both** until the React one replaces the old |
| Remotion | `remotion/` | animated TitleCard / Timeline / BarChart at exact narration length; needs Node |
| Video tools | `video/heads.py`, `video/face.py` | heads: detect (OpenCV YuNet, weights auto-downloaded to `~/.vidforge/models/`) → track/smooth → cover each face with a still **or an animated head** (`cover_video=`, oval-masked, frame-locked). face: photo → talking head, `motion` (audio-envelope puppet, no GPU) or `cmd` (`PHOTO_TALK_CMD` → SadTalker/EchoMimic/Hallo, needs a GPU). `vidforge video heads|detect|face` + `/api/video/heads/*`, `/api/video/face`. UI: the 视频 section |
| Presenter | `me.py`, `lipsync.py`, `avatar/` | own-footage library `~/.vidforge/me/`, optional lip-sync providers |
| Tests | `tests/` — `python -m unittest discover -s tests` (125 tests, offline; providers/TTS mocked) | e2e browser test skips without playwright |

Data locations: projects `~/vidforge-projects/` (`VIDFORGE_WORKSPACE`), per-project `assets/`, `build*/`,
`.history/`; user-wide `~/.vidforge/` (browser profile, `me/`, `categories/`, `voices/`, YouTube
`client_secret.json`); secrets in `.env` next to `project.json` or the repo (never committed).

## Conventions

- Before changing code: read the function and its callers; report bugs found before fixing (owner's rule).
- Comments explain *why* (policy, platform quirk, user request), not what. Match existing density.
- Accuracy over quantity for pictures: never insert an unrelated or watermarked image; leave the slot empty.
- Chinese projects must produce Chinese-only narration (no mixed English sentences, no AI chatter).
- Platform rules that shaped the design: YouTube "inauthentic content" (2025-07) and China's AI-content
  labelling (2025-09-01) — own voice / own footage / original charts are the answer, not evasion.
- Commit messages in Chinese, `[scope]: what and why`; run the unittest suite and `npx tsc -b` in
  `vidforge/ui/react` before committing UI work.
- Do not add Docker, a database, or a cloud dependency; the tool is single-user, local, file-based by design.
