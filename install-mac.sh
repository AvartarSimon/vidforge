#!/bin/bash
# vidforge one-shot installer (macOS). Safe to run again: every step skips what is already there.
#
#   ./install-mac.sh            # everything vidforge needs, plus the free optional extras
#   ./install-mac.sh --minimal  # only what a first video needs (python deps, ffmpeg, the UI)
#   ./install-mac.sh --with-ai  # also Ollama + the two small local models (~5 GB download)
#
# What it installs and why:
#   ffmpeg-full, node   Homebrew   rendering (with libass for burned subtitles) / the web UI and Remotion
#   .venv               python     vidforge itself + playwright (browser bridge), opencv (face
#                                  tools), faster-whisper (subtitle alignment for your own voice),
#                                  google api client (YouTube upload)
#   ui/react/dist       npm        the web UI, built once here so the first start is instant
#   remotion            npm        animated charts / title cards (skipped with --minimal)
#   ollama              Homebrew   optional local LLM for keywords and image checks (--with-ai)
set -e
cd "$(dirname "$0")"
# Finder starts this without the shell profile, so Homebrew may not be on PATH yet
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
MINIMAL=0; WITH_AI=0
for a in "$@"; do
  case "$a" in
    --minimal) MINIMAL=1 ;;
    --with-ai) WITH_AI=1 ;;
  esac
done
say() { printf "\n\033[1;36m[vidforge]\033[0m %s\n" "$*"; }

if ! command -v brew >/dev/null; then
  say "Homebrew not found. Install it first (one line, from https://brew.sh):"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  say "installing python 3.12 (the system python3 is older than 3.10) ..."
  brew install python@3.12; PY=python3.12
fi

# ffmpeg-full, not ffmpeg: the plain formula has no libass (burned subtitles) and no rubberband
[ -x /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg ] || [ -x /usr/local/opt/ffmpeg-full/bin/ffmpeg ] \
  || { say "installing ffmpeg-full (subtitles + pitch filters) ..."; brew install ffmpeg-full; }
command -v node >/dev/null || { say "installing node ..."; brew install node; }

if [ ! -x .venv/bin/python ]; then
  say "creating .venv with $PY ..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
EXTRAS="dev,video,youtube"
[ "$MINIMAL" = 1 ] || EXTRAS="$EXTRAS,align"
say "installing vidforge [$EXTRAS] into .venv ..."
.venv/bin/python -m pip install -q -e ".[$EXTRAS]"

say "building the web UI ..."
( cd vidforge/ui/react && npm install --no-audit --no-fund && npm run build )

if [ "$MINIMAL" = 0 ]; then
  say "installing Remotion (animated charts / title cards) ..."
  .venv/bin/vidforge remotion setup || say "Remotion setup failed — everything else still works; retry later with: .venv/bin/vidforge remotion setup"
fi

if [ "$WITH_AI" = 1 ]; then
  command -v ollama >/dev/null || { say "installing Ollama ..."; brew install --cask ollama; }
  # `ollama pull` talks to the local server, and a fresh install has not started one. The app does
  # not always open from a script (macOS asks about a new app first), so fall back to the bare
  # server — and say so when a model did not arrive, instead of finishing as if it had.
  ollama_up() { ollama list >/dev/null 2>&1; }
  wait_for_ollama() { for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do ollama_up && return 0; sleep 1; done; return 1; }
  if ! ollama_up; then
    open -a Ollama 2>/dev/null || true
    if ! wait_for_ollama; then
      say "the Ollama app did not start — running its server in the background for now"
      nohup ollama serve >/tmp/vidforge-ollama.log 2>&1 &
      wait_for_ollama || true
    fi
  fi
  for model in qwen2.5:3b qwen2.5vl:3b; do
    ollama pull "$model" || say "could not download $model — open the Ollama app once, then run: ollama pull $model"
  done
fi

say "checking ..."
.venv/bin/vidforge doctor
chmod +x start-vidforge.command
say "done. Start with:  ./start-vidforge.command   (or: .venv/bin/vidforge start)"
