#!/bin/bash
# vidforge launcher (macOS). Double-click in Finder (first time: right-click -> Open).
# The first run hands over to install-mac.sh (venv, ffmpeg, node, UI build); after that it just opens
# the last project — `vidforge start` is the same thing from a terminal.
cd "$(dirname "$0")"
# Finder starts this without the shell profile, so Homebrew may not be on PATH yet
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# a venv next to the repo is what install-mac.sh makes; it keeps vidforge off the system python
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import vidforge, edge_tts" 2>/dev/null \
   || ! { [ -x /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg ] || [ -x /usr/local/opt/ffmpeg-full/bin/ffmpeg ] || command -v ffmpeg >/dev/null; }; then
  echo "[vidforge] first run: installing (a few minutes, only once) ..."
  bash ./install-mac.sh --minimal || { read -r -p "Install failed — press Enter to close"; exit 1; }
fi
PY=.venv/bin/python

PROJECT="$1"
[ -z "$PROJECT" ] && [ -f last-project.txt ] && PROJECT="$(cat last-project.txt)"
if [ -z "$PROJECT" ]; then
  read -r -p "Project folder (empty = examples/demo): " PROJECT
fi
if [ -z "$PROJECT" ]; then
  PROJECT="$PWD/examples/demo"
  [ -f "$PROJECT/project.json" ] || "$PY" -m vidforge.cli demo "$PROJECT"
fi
echo "$PROJECT" > last-project.txt
echo "[vidforge] opening $PROJECT"
"$PY" -m vidforge.cli ui "$PROJECT"
