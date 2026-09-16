"""Command line: vidforge {init,demo,build,voices,doctor}"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, ffmpeg, project as proj


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
    from .tts import edge
    for v in edge.list_voices(args.lang):
        tags = ",".join(v.get("VoiceTag", {}).get("VoicePersonalities", []))
        print(f"{v['ShortName']:<32} {v['Gender']:<7} {tags}")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    print(f"vidforge {__version__} · python {sys.version.split()[0]}")
    ffmpeg.print_versions()
    try:
        import edge_tts  # noqa: F401
        print("edge-tts: ok")
    except ImportError:
        print("edge-tts: MISSING (pip install edge-tts)")
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

    s = sub.add_parser("voices", help="list edge-tts voices")
    s.add_argument("--lang", help="locale prefix, e.g. en, en-US, zh")
    s.set_defaults(fn=cmd_voices)

    s = sub.add_parser("doctor", help="check ffmpeg / dependencies")
    s.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
