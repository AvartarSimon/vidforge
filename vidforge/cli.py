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
        p = proj.load(args.project)
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
        p = proj.load(args.project)
    except proj.ProjectError as e:
        print(f"project error: {e}", file=sys.stderr)
        return 2
    env.load_dotenv(p.root)
    youtube.upload(p, privacy=args.privacy, publish_at=args.publish_at)
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
    s.add_argument("--privacy", choices=["private", "unlisted", "public"], help="override youtube.privacy")
    s.add_argument("--publish-at", help="schedule, ISO 8601 UTC e.g. 2026-10-01T09:00:00Z (video stays private until then)")
    s.set_defaults(fn=cmd_upload)

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
