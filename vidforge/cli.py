"""Command line: vidforge {init,demo,build,voices,doctor}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, env, ffmpeg, project as proj


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir)
    (target / "assets").mkdir(parents=True, exist_ok=True)
    pj = target / "project.json"
    if pj.exists() and not args.force:
        print(f"{pj} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    pj.write_text(json.dumps(proj.TEMPLATE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"created {pj}\nput your images in {target / 'assets'} and edit the segments, then:\n"
          f"  vidforge build {pj}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from . import demo
    pj = demo.create(Path(args.dir))
    print(f"demo project created: {pj}\n  vidforge build {pj}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from . import pipeline
    try:
        p = proj.load(args.project, lang=args.lang)
    except proj.ProjectError as e:
        print(f"project error: {e}", file=sys.stderr)
        return 2
    burn = True if args.burn else (False if args.no_burn else None)
    try:
        pipeline.build(p, only_tts=args.only_tts, burn=burn)
    except ffmpeg.FfmpegError as e:
        print(f"\n{e}", file=sys.stderr)
        return 3
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    from .tts import get_provider
    env.load_dotenv()
    provider = get_provider(args.provider)
    for name, desc in provider.list_voices(args.lang):
        print(f"{name:<44} {desc}")
    return 0


def cmd_assets(args: argparse.Namespace) -> int:
    """Fetch pexels:… assets only, so the pictures can be reviewed before a long render."""
    from . import assets
    try:
        p = proj.load(args.project)
    except proj.ProjectError as e:
        print(f"project error: {e}", file=sys.stderr)
        return 2
    env.load_dotenv(p.root)
    assets.resolve_all(p, log=print)
    for s in p.segments:
        print(f"  {s.id:<12} {'video' if s.video else 'image':<5} {s.video or s.image}")
    return 0


def cmd_upload(args: argparse.Namespace) -> int:
    from .upload import youtube
    try:
        p = proj.load(args.project, lang=args.lang)
    except proj.ProjectError as e:
        print(f"project error: {e}", file=sys.stderr)
        return 2
    env.load_dotenv(p.root)
    youtube.upload(p, privacy=args.privacy, publish_at=args.publish_at)
    return 0


def cmd_i18n(args: argparse.Namespace) -> int:
    from . import i18n
    if args.action == "export":
        out = i18n.export(args.project, args.lang)
        n = len(json.loads(out.read_text(encoding="utf-8"))["segments"])
        print(f"wrote {out} ({n} segments to translate). Fill the empty '{args.lang}' strings, then:")
        print(f"  vidforge i18n import {args.project} --lang {args.lang}")
    else:
        written, empty = i18n.import_(args.project, args.lang)
        print(f"imported {written} fields into project.json")
        if empty:
            print(f"still untranslated: {', '.join(empty)}")
        else:
            print(f"  vidforge build {args.project} --lang {args.lang}")
    return 0


def cmd_browser(args: argparse.Namespace) -> int:
    from . import browser
    if args.action == "login":
        browser.login_session(args.sites or None)
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from .browser import chat
    text = chat.ask(args.site, " ".join(args.prompt), timeout=args.timeout)
    print(text)
    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    from .tts import voice_design
    env.load_dotenv()
    if args.action == "design":
        previews = voice_design.design(args.desc, args.text)
        print("previews (play them, then `vidforge voice keep <id> --name … --desc …`):")
        for p in previews:
            print(f"  {p['generated_voice_id']}  {p['audio']}")
    else:
        vid = voice_design.keep(args.id, args.name, args.desc or args.name)
        print(f"voice_id: {vid}   -> put it in project.json as \"voice\" with tts.provider elevenlabs")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """Open the last project (or the project picker) in the browser — the one-command start."""
    from . import ui
    from .ui import recent_projects
    target = args.project
    if not target and not args.picker:
        rec = recent_projects()
        if rec:
            target = rec[0]["path"]
    ui.serve(target, port=args.port, open_browser=True)
    return 0


def cmd_shortcut(_: argparse.Namespace) -> int:
    """Desktop shortcut that runs `vidforge start` (Windows .lnk / macOS .command / Linux .desktop)."""
    import platform
    import subprocess
    desktop = Path.home() / "Desktop"
    if platform.system() == "Windows":
        try:   # the real Desktop may live under OneDrive
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                                 capture_output=True, text=True, timeout=20).stdout.strip()
            if out:
                desktop = Path(out)
        except Exception:  # noqa: BLE001
            pass
    if not desktop.exists():
        desktop = Path.home()
    py = sys.executable
    if platform.system() == "Windows":
        pyw = Path(py).with_name("pythonw.exe")
        exe = str(pyw if pyw.exists() else py)
        lnk = desktop / "vidforge.lnk"
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
              f"$s.TargetPath='{exe}';$s.Arguments='-m vidforge.cli start';$s.WorkingDirectory='{Path.home()}';"
              f"$s.IconLocation='{Path(sys.executable).parent / 'python.exe'},0';$s.Description='vidforge';$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
        print(f"created {lnk}  (double-click to start; it opens your last project)")
    elif platform.system() == "Darwin":
        f = desktop / "vidforge.command"
        f.write_text(f"#!/bin/bash\n'{py}' -m vidforge.cli start\n", encoding="utf-8")
        f.chmod(0o755)
        print(f"created {f}  (first time: right-click → Open)")
    else:
        f = desktop / "vidforge.desktop"
        f.write_text(f"[Desktop Entry]\nType=Application\nName=vidforge\nExec={py} -m vidforge.cli start\nTerminal=false\n", encoding="utf-8")
        f.chmod(0o755)
        print(f"created {f}")
    return 0


def cmd_ui(args: argparse.Namespace) -> int:
    from . import ui
    ui.serve(args.project, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_remotion(args: argparse.Namespace) -> int:
    from . import remotion
    if args.action == "setup":
        remotion.setup()
    elif args.action == "studio":
        remotion.studio()
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    print(f"vidforge {__version__} · python {sys.version.split()[0]}")
    ffmpeg.print_versions()
    try:
        import edge_tts  # noqa: F401
        print("edge-tts: ok")
    except ImportError:
        print("edge-tts: MISSING (pip install edge-tts)")
    import shutil as _sh
    from .remotion import APP_DIR
    node = _sh.which("node")
    print(f"node: {node or 'NOT FOUND (needed only for remotion segments)'}"
          + (" · remotion installed" if (APP_DIR / "node_modules").exists() else " · remotion not installed (vidforge remotion setup)"))
    dotenv = env.load_dotenv()
    print(f".env: {dotenv or 'none found'}")
    import os
    for k, hint in env.KEYS.items():
        print(f"{k}: {'set' if os.environ.get(k) else 'not set'}  — {hint}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):        # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="vidforge", description="script-to-video assembly line")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create an empty project.json + assets/ in DIR")
    s.add_argument("dir")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("demo", help="create a runnable sample project in DIR")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("build", help="render a project")
    s.add_argument("project", help="project.json or its directory")
    s.add_argument("--lang", help="build a language variant (segments' text_<lang>, variants[<lang>]) into build_<lang>/")
    s.add_argument("--only-tts", action="store_true", help="synthesize narration only (proof-listen)")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--burn", action="store_true", help="burn subtitles into the video")
    g.add_argument("--no-burn", action="store_true", help="never burn (only write final.srt)")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("voices", help="list voices of a TTS provider")
    s.add_argument("--provider", default="edge", choices=["edge", "elevenlabs"])
    s.add_argument("--lang", help="edge: locale prefix (en, en-US, zh); elevenlabs: substring filter")
    s.set_defaults(fn=cmd_voices)

    s = sub.add_parser("assets", help="download pexels:… assets of a project without rendering")
    s.add_argument("project")
    s.set_defaults(fn=cmd_assets)

    s = sub.add_parser("upload", help="upload build/final.mp4 + thumbnail + captions to YouTube")
    s.add_argument("project")
    s.add_argument("--lang", help="upload the language variant built with --lang")
    s.add_argument("--privacy", choices=["private", "unlisted", "public"], help="override youtube.privacy")
    s.add_argument("--publish-at", help="schedule, ISO 8601 UTC e.g. 2026-10-01T09:00:00Z (video stays private until then)")
    s.set_defaults(fn=cmd_upload)

    s = sub.add_parser("i18n", help="translation sheet: 'export' writes i18n_<lang>.json, 'import' merges it back")
    s.add_argument("action", choices=["export", "import"])
    s.add_argument("project")
    s.add_argument("--lang", required=True)
    s.set_defaults(fn=cmd_i18n)

    s = sub.add_parser("browser", help="'login': open the dedicated browser profile to log into chat sites once")
    s.add_argument("action", choices=["login"])
    s.add_argument("sites", nargs="*", help="chatgpt claude gemini deepseek grok qwen kimi yiyan (default: all)")
    s.set_defaults(fn=cmd_browser)

    s = sub.add_parser("chat", help="ask a web chat through your logged-in browser and print the answer")
    s.add_argument("site", choices=["chatgpt", "claude", "gemini", "deepseek", "grok", "qwen", "kimi", "yiyan"])
    s.add_argument("prompt", nargs="+")
    s.add_argument("--timeout", type=float, default=240)
    s.set_defaults(fn=cmd_chat)

    s = sub.add_parser("voice", help="design a brand voice from a description (ElevenLabs Voice Design)")
    s.add_argument("action", choices=["design", "keep"])
    s.add_argument("id", nargs="?", help="keep: generated_voice_id from a preview")
    s.add_argument("--desc", default="", help="voice description, e.g. 'deep warm magnetic male narrator, unhurried'")
    s.add_argument("--text", default="", help="sample text (>= 100 chars; default: a narration sample)")
    s.add_argument("--name", default="vidforge narrator")
    s.set_defaults(fn=cmd_voice)

    s = sub.add_parser("start", help="open vidforge: last project, or the project picker")
    s.add_argument("project", nargs="?")
    s.add_argument("--picker", action="store_true", help="always show the project picker")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("shortcut", help="create a desktop shortcut that runs `vidforge start`")
    s.set_defaults(fn=cmd_shortcut)

    s = sub.add_parser("ui", help="local web UI for a project (edit, proof-listen, build)")
    s.add_argument("project")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("remotion", help="animated graphics: 'setup' installs Remotion once, 'studio' opens the editor")
    s.add_argument("action", choices=["setup", "studio"])
    s.set_defaults(fn=cmd_remotion)

    s = sub.add_parser("doctor", help="check ffmpeg / dependencies")
    s.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except RuntimeError as e:          # missing API key, provider HTTP error, ffmpeg failure
        print(f"error: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
