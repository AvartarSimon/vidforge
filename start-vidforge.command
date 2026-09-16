#!/bin/bash
# vidforge launcher (macOS). Double-click in Finder (first time: right-click -> Open).
# 1) python3 + vidforge installed?  2) ffmpeg?  3) open the wizard for the project.
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
  echo "[vidforge] python3 not found. Install Xcode command line tools (xcode-select --install) or python.org."
  read -r -p "Press Enter to close"; exit 1
fi
python3 -c "import vidforge" 2>/dev/null || { echo "[vidforge] installing vidforge ..."; python3 -m pip install -e . || exit 1; }
if ! python3 -c "from vidforge import ffmpeg; ffmpeg.find_binary('ffmpeg')" 2>/dev/null; then
  if command -v brew >/dev/null; then
    echo "[vidforge] installing ffmpeg with Homebrew ..."; brew install ffmpeg
  else
    echo "[vidforge] ffmpeg not found and Homebrew missing. Install Homebrew (https://brew.sh) then: brew install ffmpeg"
    read -r -p "Press Enter to close"; exit 1
  fi
fi

PROJECT="$1"
[ -z "$PROJECT" ] && [ -f last-project.txt ] && PROJECT="$(cat last-project.txt)"
if [ -z "$PROJECT" ]; then
  read -r -p "Project folder (empty = examples/demo): " PROJECT
fi
if [ -z "$PROJECT" ]; then
  PROJECT="$PWD/examples/demo"
  [ -f "$PROJECT/project.json" ] || python3 -m vidforge.cli demo "$PROJECT"
fi
echo "$PROJECT" > last-project.txt
echo "[vidforge] opening $PROJECT"
python3 -m vidforge.cli ui "$PROJECT"
