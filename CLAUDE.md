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
| CLI | `vidforge/cli.py` | `vidforge start|ui|build|doctor|voices|assets|upload|i18n|browser|chat|voice|me|category|remotion|structure|short|brand|data|narration|voicefx|shortcut` |
| Pipeline | `pipeline.py`, `render.py`, `subtitles.py`, `thumbnail.py`, `ffmpeg.py` | staged build with per-segment clip cache `build/clips/<seg>.<hash>.mp4`; encoder auto-pick (nvenc/qsv/amf/videotoolbox/libx264) |
| Project model | `project.py` (`Project`, `Segment`, `Clip`, `Overlay`) | `Clip.source` = unresolved spec `"commons:Battle of Lexington 1775"`, resolved at build or by autofill |
| Assets | `assets/` — `pexels.py`, `pixabay.py`, `wikimedia.py`, `openverse.py`, `archive.py`, `google_images.py`, `baidu.py` | `Library` = `assets/index.json` (licence, credits, picks, vision-check verdicts). `pick_many()` is what autofill uses (one search → several files, downloaded in parallel); `relevant()` (contiguous content-word bigram) + `branded()` + `blocked_host()` gate accuracy, `vision_verdict()` is the optional slow check; `normalise()` shrinks museum-sized downloads |
| TTS | `tts/` (edge-tts default, ElevenLabs, VoxCPM) | word timings drive `final.srt` |
| Own voice | `narration.py`, `align.py`, `voicefx.py` | `Segment.narration` = your own recording instead of TTS: decode (video too) → trim the silence → force-align to the script (faster-whisper, **optional**; falls back to an even spread) → the same `list[Word]` TTS returns, cached in a sidecar so Whisper runs once per take. `voicefx` presets (clean/warm/clear/phone) are plain ffmpeg filters applied in `render.py` beside `loudnorm`, and every one preserves duration — the word timings were measured against that audio |
| Local LLM | `llm.py` (Ollama, optional) | text: `qwen2.5:3b` keywords/translation/chapter names, batched `keywords_batch()`; vision: `qwen2.5vl:3b` `vision_check()` (watermark / text overlay / depicts) |
| Browser bridge | `browser/` (Playwright on the user's own Chrome/Edge profile) | types prompts into ChatGPT/Claude/DeepSeek/… web UIs for script generation; no API keys |
| Structure | `structure.py` | retention skeletons (钩子-背景-数据-转折-回扣) + `check()`; feeds the script prompt, the CLI (`vidforge structure`) and `/api/structure/*` |
| Script parsing | `script_parser.py` | pasted AI text → segments; strips chatter/notes/stage directions; `language_issues()` flags mixed language |
| Web UI backend | `ui/__init__.py` (stdlib `ThreadingHTTPServer`, `/api/*`, port 8765) | `State` holds project path, build status, autofill job, background vision-check queue. `STAMP` = code mtime; a stale running copy is replaced on start |
| UI sections | `ui/react/src/components/sections/` | 视频 / 声音 / 图片 — material-centred pages beside the 5-step wizard (React UI only; the old static UI has no nav rail) |
| Web UI frontend | `ui/react/` (Vite + MUI) — **this is the UI**; the backend serves `ui/react/dist/` at `/`, and builds it on first run when Node is present | Dev loop: `npm run dev` on 5175 proxying to 8765. `ui/static/app.js` is a frozen fallback for machines without Node, reachable at `/old`; **do not add features to it** |
| Remotion | `remotion/` | TitleCard / Timeline / BarChart / **LineChart / BigNumber / Compare** / Vocab / Host, each exactly the narration's length; charts carry a source caption; needs Node |
| Data | `data/` — `worldbank.py`, `from_csv()` | public datasets → chart props. World Bank: no key, ~16k indicators, cached 30 days in `~/.vidforge/data-cache/`. Values auto-scaled to 万亿/亿/万 and every series carries its source through to the caption. `vidforge data search|chart`, `/api/data/*`, UI: 画面 → 动画 tab |
| Video tools | `video/heads.py`, `video/face.py` | heads: detect (OpenCV YuNet, weights auto-downloaded to `~/.vidforge/models/`) → track/smooth → cover each face with a still **or an animated head** (`cover_video=`, oval-masked, frame-locked). face: photo → talking head, `motion` (audio-envelope puppet, no GPU) or `cmd` (`PHOTO_TALK_CMD` → SadTalker/EchoMimic/Hallo, needs a GPU). `vidforge video heads|detect|face` + `/api/video/heads/*`, `/api/video/face`. UI: the 视频 section |
| Presenter | `me.py`, `lipsync.py`, `avatar/` | own-footage library `~/.vidforge/me/`, optional lip-sync providers |
| Tests | `tests/` — `python -m unittest discover -s tests` (294 tests, offline; providers/TTS/alignment mocked — the real-alignment tests skip without faster-whisper) | e2e browser test skips without playwright |

Data locations: projects `~/vidforge-projects/` (`VIDFORGE_WORKSPACE`), per-project `assets/`, `build*/`,
`.history/`; user-wide `~/.vidforge/` (browser profile, `me/`, `categories/`, `voices/`, YouTube
`client_secret.json`); secrets in `.env` next to `project.json` or the repo (never committed).

## Conventions

- Before changing code: read the function and its callers; report bugs found before fixing (owner's rule).
- Comments explain *why* (policy, platform quirk, user request), not what. Match existing density.
- Accuracy over quantity for pictures: never insert an unrelated or watermarked image; leave the slot empty.
- Subtitles say what the *script* says. A transcription is only ever consulted about *when* a word
  was spoken, never about what it was — Whisper mishears names and drops punctuation.
- Never invent a figure: a chart's numbers come from a fetched dataset or a pasted table, and the source caption rides along with them to the screen.
- Chinese projects must produce Chinese-only narration (no mixed English sentences, no AI chatter).
- Platform rules that shaped the design: YouTube "inauthentic content" (2025-07) and China's AI-content
  labelling (2025-09-01) — own voice / own footage / original charts are the answer, not evasion.
- Commit messages in Chinese, `[scope]: what and why`; run the unittest suite and `npx tsc -b` in
  `vidforge/ui/react` before committing UI work.
- Do not add Docker, a database, or a cloud dependency; the tool is single-user, local, file-based by design.
