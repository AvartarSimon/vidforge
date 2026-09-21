@echo off
rem vidforge launcher (Windows). Double-click, or drop a project folder onto it.
rem 1) python + vidforge installed?  2) ffmpeg?  3) open the wizard for the project.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (
  echo [vidforge] Python not found. Install from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and run again.
  pause & exit /b 1
)
python -c "import vidforge" 2>nul || (
  echo [vidforge] installing vidforge ...
  python -m pip install -e . || (pause & exit /b 1)
)
python -c "import playwright.sync_api" 2>nul || (
  echo [vidforge] installing playwright for browser features ^(no browser download, uses Edge/Chrome^) ...
  python -m pip install "playwright>=1.45"
)
python -c "from vidforge import ffmpeg; ffmpeg.find_binary('ffmpeg')" 2>nul || (
  echo [vidforge] ffmpeg not found. Installing with winget ...
  winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
  echo [vidforge] ffmpeg installed - please close this window and double-click again so PATH refreshes.
  pause & exit /b 0
)

set "PROJECT=%~1"
if "%PROJECT%"=="" (
  if exist "%~dp0last-project.txt" set /p PROJECT=<"%~dp0last-project.txt"
)
if "%PROJECT%"=="" (
  set /p PROJECT=Project folder (empty = create examples\demo via 'vidforge demo'):
)
if "%PROJECT%"=="" (
  set "PROJECT=%~dp0examples\demo"
  if not exist "%PROJECT%\project.json" python -m vidforge.cli demo "%PROJECT%"
)
echo %PROJECT%> "%~dp0last-project.txt"
echo [vidforge] opening %PROJECT%
python -m vidforge.cli ui "%PROJECT%"
pause
