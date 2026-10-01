"""Command line: vidforge {init,demo,build,voices,doctor}"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
        status = browser.login_session(args.sites or None)
        print()
        for name, ok in status.items():
            print(f"  {'已登录' if ok else '未登录 ⚠'}  {name}")
        if not all(status.values()):
            print("\n未登录的站点再运行一次 `vidforge browser login <站点>` 单独登录。")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    from .browser import chat
    text = chat.ask(args.site, " ".join(args.prompt), timeout=args.timeout)
    print(text)
    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    mod = __import__(f"vidforge.tts.{'voice_design' if args.provider == 'elevenlabs' else 'voxcpm'}", fromlist=["x"])
    env.load_dotenv()
    if args.action == "design":
        previews = mod.design(args.desc, args.text)
        print("previews (play them, then `vidforge voice keep <id> --name … --desc … --provider "
              f"{args.provider}`):")
        for p in previews:
            print(f"  {p['generated_voice_id']}  {p['audio']}")
    else:
        vid = mod.keep(args.id, args.name, args.desc or args.name)
        print(f"voice: {vid}   -> put it in project.json as \"voice\" with tts.provider {args.provider}")
    return 0


def cmd_me(args: argparse.Namespace) -> int:
    """Your footage library (~/.vidforge/me, or <project>/assets/me): scan tags/durations, or
    relabel one take. `me` clips/overlays in project.json pick from here by tag at build time."""
    from . import me
    root = Path(args.project).resolve() if args.project else None
    lib = me.MeLibrary(me.library_dir(root))
    if args.action == "scan":
        items = lib.scan()
        if not items:
            print(f"素材库是空的：{lib.folder}\n把视频放进去，文件名即标签，例如 backyard_glasses_talking_01.mp4")
            return 0
        print(f"{lib.folder}（{len(items)} 个）:")
        for i in sorted(items, key=lambda x: x["name"]):
            tags = ", ".join(i.get("tags", [])) or "(无标签)"
            dur = f"{i['duration']:.1f}s" if i.get("duration") else "?"
            print(f"  {i['name']:<40} {dur:>7}  {'说话' if i.get('talking') else '沉默':<4}  用过{i.get('uses', 0)}次  [{tags}]")
        return 0
    # tag
    if not args.name:
        raise SystemExit("`vidforge me tag <文件名> --tags a,b [--talking true|false]`")
    lib.scan()
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    talking = {"true": True, "false": False}.get((args.talking or "").lower())
    lib.set_tags(args.name, tags, talking)
    print(f"已更新 {args.name}：标签 {tags or '(清空)'}" + (f"，talking={talking}" if talking is not None else ""))
    return 0


def cmd_brand(args: argparse.Namespace) -> int:
    """The channel's own look: name, slogan, colours, logo, opener and end card."""
    from . import brand as kitmod
    kit = kitmod.load()

    if args.action == "show":
        print(json.dumps(kitmod.asdict(kit), ensure_ascii=False, indent=1))
        print(f"\n配置文件：{kitmod.BRAND_FILE}")
        return 0

    if args.action == "slogans":
        for line in kitmod.suggest_slogans(kit.name):
            print("  " + line)
        return 0

    if args.action == "init":
        for field_name in ("name", "slogan", "en_name", "mark", "bg", "fg", "accent",
                           "subscribe", "next_hint", "sting"):
            value = getattr(args, field_name, None)
            if value:
                setattr(kit, field_name, value)
        if not kit.name:
            raise SystemExit("`vidforge brand init --name <频道名> [--slogan ...]`")
        if not kitmod.contrast_ok(kit.bg, kit.fg):
            print("⚠ 前景色在背景上对比度不足 4.5:1，片尾的字会糊")
        logos = kitmod.write_logos(kit)
        path = kitmod.save(kit)
        print(f"品牌配置：{path}")
        for f in logos:
            print(f"  标志：{f}")
        print("\n换一个标志样式：vidforge brand init --name %s --mark line" % kit.name)
        return 0

    if args.action == "sting":
        out = Path(args.out) if args.out else kitmod.BRAND_DIR / f"sting-{args.style}.m4a"
        kitmod.sting(out, style=args.style, seconds=args.seconds)
        kit.sting = str(out)
        kitmod.save(kit)
        print(f"音频标识：{out}（{args.style}，{args.seconds:.1f}s，纯合成音，无版权问题）")
        return 0

    # preview
    if not kit.name:
        raise SystemExit("先跑 `vidforge brand init --name <频道名>`")
    out_dir = Path(args.out) if args.out else kitmod.BRAND_DIR / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    opener = kitmod.render_opener(kit, out_dir, args.width, args.height, args.fps)
    if kit.sting:
        opener = kitmod.with_audio(opener, Path(kit.sting), out_dir / "intro.mp4", kit.intro_seconds)
    card = kitmod.render_endcard(kit, out_dir, args.width, args.height, args.fps)
    print(f"片头：{opener}\n片尾：{card}")
    return 0


def cmd_data(args: argparse.Namespace) -> int:
    """Public datasets -> a chart segment. `search` finds an indicator code, `chart` renders one."""
    from .data import bar_props, big_number_props, compare_props, line_props, worldbank
    if args.action == "search":
        for hit in worldbank.search(args.query or "", limit=args.limit):
            print(f"  {hit['id']:<24} {hit['name']}")
        return 0

    if not args.indicator:
        raise SystemExit("`vidforge data chart --indicator <代码> --countries CHN,USA`（代码用 `data search` 找）")
    countries = [c.strip() for c in (args.countries or "CHN").replace("，", ",").split(",") if c.strip()]
    series = worldbank.fetch(args.indicator, countries, args.start, args.end)
    builders = {
        "line": lambda: line_props(series, args.title or ""),
        "bar": lambda: bar_props(series, args.title or "", args.year),
        "big": lambda: big_number_props(series, args.label or None, args.title or ""),
        "compare": lambda: compare_props(series, *(args.label or "").split(",")[:2], args.year, args.title or ""),
    }
    if args.chart == "compare" and len((args.label or "").split(",")) < 2:
        raise SystemExit("compare 需要 --label 中国,美国")
    props = builders[args.chart]()
    composition = {"line": "LineChart", "bar": "BarChart", "big": "BigNumber", "compare": "Compare"}[args.chart]
    clip = {"remotion": {"composition": composition, "props": props}}
    if not args.project:
        print(json.dumps(clip, ensure_ascii=False, indent=1))
        return 0

    root = Path(args.project).resolve()
    path = root / "project.json" if root.is_dir() else root
    if not path.is_file():
        raise SystemExit(f"找不到项目：{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    target = next((sg for sg in raw["segments"] if sg["id"] == args.segment), None) if args.segment else None
    if args.segment and target is None:
        raise SystemExit(f"项目里没有段落 {args.segment}")
    if target is None:
        raw["segments"].append({"id": f"chart-{args.indicator.lower().replace('.', '-')}",
                                "text": args.text or "", "clips": [clip]})
    else:
        target.setdefault("clips", []).append(clip)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"已加入 {path.name}：{composition} · {series.source}")
    return 0


def cmd_video(args: argparse.Namespace) -> int:
    """Tools that take a clip and give a clip back, independent of any project.
    `heads` covers every face with a picture (or an animated head) that follows it; `face` turns a
    photo into a head that talks along with an audio file."""
    from .video import heads
    src = Path(args.input).resolve()
    if not src.is_file():
        raise SystemExit(f"找不到视频：{src}")
    if args.action == "face":
        from .video import face
        if not args.audio:
            raise SystemExit("`vidforge video face <图片> --audio <音频> [-o head.mp4]`")
        out = Path(args.out) if args.out else src.with_name(src.stem + "_talking.mp4")
        r = face.talk(src, Path(args.audio).resolve(), out, provider=args.provider, crop=not args.no_crop)
        print(f"完成：{r}")
        return 0
    if args.action == "detect":
        out = Path(args.out) if args.out else src.with_name(src.stem + "_faces.png")
        heads.preview_frame(src, out, at=args.at)
        print(f"检测结果（红框=会被盖住）：{out}")
        return 0
    out = Path(args.out) if args.out else src.with_name(src.stem + "_covered.mp4")
    image = Path(args.image).resolve() if args.image else None
    if image and not image.is_file():
        raise SystemExit(f"找不到遮挡图片：{image}")
    r = heads.cover(src, out, image=image, scale=args.scale, y_offset=args.y_offset, every=args.every,
                    cover_video=Path(args.cover_video).resolve() if args.cover_video else None)
    print(f"完成：{r['out']}（{r['faces']} 张脸，{r['covered']}/{r['frames']} 帧）")
    return 0


def cmd_category(args: argparse.Namespace) -> int:
    """Named per-topic-vertical presets (platforms, reference sources, banned keywords, defaults)
    — see vidforge/categories.py for why these are plain JSON files, not a database."""
    from . import categories as cat_mod
    if args.action == "list":
        cats = cat_mod.list_categories()
        if not cats:
            print(f"还没有分类。{cat_mod.DIR} 是空的。"); return 0
        for c in cats:
            print(f"  {c['id']:<24} {c['name']}")
        return 0
    if args.action == "show":
        c = cat_mod.load(args.arg or "")
        if not c:
            raise SystemExit(f"没有这个分类：{args.arg}")
        print(json.dumps(c, indent=2, ensure_ascii=False)); return 0
    if args.action == "path":
        print(cat_mod.DIR / f"{args.arg}.json" if args.arg else cat_mod.DIR); return 0
    if args.action == "delete":
        cat_mod.delete(args.arg or ""); print("已删除"); return 0
    if args.action == "export":
        out = Path(args.arg or "vidforge-categories.json")
        out.write_text(json.dumps(cat_mod.export_all(), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"已导出到 {out}"); return 0
    if args.action == "import":
        data = json.loads(Path(args.arg).read_text(encoding="utf-8"))
        saved = cat_mod.import_bundle(data, merge=not args.replace)
        print(f"{'替换为' if args.replace else '合并了'} {len(saved)} 个分类"); return 0
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    """Open the last project (or the project picker) in the browser — the one-command start.

    This is the desktop-shortcut entry point, launched with `pythonw.exe` (no console window),
    so an unhandled exception here would otherwise just vanish — double-click, nothing visibly
    happens, no way to tell why. Any failure gets written to a log file and shown in a native
    message box instead of disappearing silently."""
    from . import ui
    from .ui import recent_projects
    try:
        target = args.project
        if not target and not args.picker:
            rec = recent_projects()
            if rec:
                target = rec[0]["path"]
                # The remembered project may have been deleted, moved, or be on a drive that is
                # not plugged in. Opening the picker is always better than refusing to start.
                if not (Path(target) / "project.json").is_file():
                    target = None
        ui.serve(target, port=args.port, open_browser=True)
        return 0
    except BaseException as e:  # noqa: BLE001
        import traceback
        log_dir = Path.home() / ".vidforge" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"start-error-{int(time.time())}.log"
        log_file.write_text(traceback.format_exc(), encoding="utf-8")
        msg = f"vidforge 启动失败：\n\n{e}\n\n详情见：\n{log_file}"
        # The message box exists for the desktop shortcut, which runs under pythonw with no
        # console to print to. Where there is a console, printing is visible and does not block —
        # a modal dialog in a terminal or a CI run just sits there waiting for a click.
        headless = not sys.stderr or not sys.stderr.isatty()
        if sys.platform == "win32" and headless and not os.environ.get("VIDFORGE_NO_DIALOG"):
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "vidforge", 0x10)  # MB_ICONERROR
            except Exception:  # noqa: BLE001
                pass
        else:
            print(msg, file=sys.stderr)
        return 1


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
    # Bare `vidforge` opens the app. A tool whose normal use is "open it and work" should not
    # demand a subcommand before it will do the obvious thing.
    sub = ap.add_subparsers(dest="cmd", required=False)

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

    s = sub.add_parser("voice", help="design a brand voice from a description (ElevenLabs, paid, or VoxCPM2, free/local)")
    s.add_argument("action", choices=["design", "keep"])
    s.add_argument("id", nargs="?", help="keep: generated_voice_id from a preview")
    s.add_argument("--provider", choices=["elevenlabs", "voxcpm"], default="elevenlabs")
    s.add_argument("--desc", default="", help="voice description, e.g. 'deep warm magnetic male narrator, unhurried'")
    s.add_argument("--text", default="", help="sample text (>= 100 chars; default: a narration sample)")
    s.add_argument("--name", default="vidforge narrator")
    s.set_defaults(fn=cmd_voice)

    s = sub.add_parser("me", help="your footage library: 'scan' lists takes/tags, 'tag' relabels one")
    s.add_argument("action", choices=["scan", "tag"])
    s.add_argument("name", nargs="?", help="tag: the file name inside the library folder")
    s.add_argument("--project", help="use <project>/assets/me instead of the global ~/.vidforge/me")
    s.add_argument("--tags", help="tag: comma-separated tags, e.g. backyard,glasses")
    s.add_argument("--talking", choices=["true", "false"], help="tag: mark as a speaking take or silent B-roll")
    s.set_defaults(fn=cmd_me)

    s = sub.add_parser("brand", help="channel look: name, slogan, logo, 1s opener, end card, audio mark")
    s.add_argument("action", choices=["init", "show", "preview", "sting", "slogans"])
    s.add_argument("--name", help="频道名，出现在片头片尾")
    s.add_argument("--slogan", help="一句话，别超过 12 个字")
    s.add_argument("--en-name", dest="en_name", help="副标题/英文名，可选")
    s.add_argument("--mark", choices=["ticks", "line", "axis"], help="内置标志样式")
    s.add_argument("--bg", help="背景色 #RRGGBB")
    s.add_argument("--fg", help="主文字色")
    s.add_argument("--accent", help="强调色（标志上的那一笔、订阅按钮）")
    s.add_argument("--subscribe", help="片尾按钮上的字")
    s.add_argument("--next-hint", dest="next_hint", help="片尾的「下期：…」")
    s.add_argument("--style", default="rise", choices=["rise", "settle", "two"], help="sting: 音效走向")
    s.add_argument("--seconds", type=float, default=1.4, help="sting: 时长")
    s.add_argument("--out", help="sting/preview: 输出位置")
    s.add_argument("--width", type=int, default=1920)
    s.add_argument("--height", type=int, default=1080)
    s.add_argument("--fps", type=int, default=30)
    s.set_defaults(fn=cmd_brand)

    s = sub.add_parser("data", help="public datasets as charts: 'search' finds an indicator, 'chart' builds one")
    s.add_argument("action", choices=["search", "chart"])
    s.add_argument("query", nargs="?", help="search: words to look for, e.g. population")
    s.add_argument("--limit", type=int, default=15)
    s.add_argument("--indicator", help="chart: World Bank indicator code, e.g. NY.GDP.MKTP.CD")
    s.add_argument("--countries", default="CHN", help="chart: ISO3 codes, e.g. CHN,USA,JPN")
    s.add_argument("--start", type=int, help="chart: first year")
    s.add_argument("--end", type=int, help="chart: last year")
    s.add_argument("--chart", choices=["line", "bar", "big", "compare"], default="line")
    s.add_argument("--title", help="chart: heading (defaults to the indicator's own name)")
    s.add_argument("--label", help="big: which country · compare: two, e.g. 中国,美国")
    s.add_argument("--year", type=float, help="bar/compare: which year (default: the latest)")
    s.add_argument("--project", help="write the chart into this project instead of printing it")
    s.add_argument("--segment", help="add it to this segment (default: a new segment at the end)")
    s.add_argument("--text", help="narration for the new segment")
    s.set_defaults(fn=cmd_data)

    s = sub.add_parser("video", help="clip tools: 'heads' covers every face with a picture that follows it")
    s.add_argument("action", choices=["heads", "detect", "face"],
                   help="heads: render the covered clip · detect: one frame showing what was found · "
                        "face: animate a photo to talk along with an audio file")
    s.add_argument("input", help="the video file (or, for `face`, the photo)")
    s.add_argument("-o", "--out", help="output file (default: alongside the input)")
    s.add_argument("--image", help="picture to paste over each face (PNG with transparency is best); omit for a blurred disc")
    s.add_argument("--scale", type=float, default=1.5, help="cover size as a multiple of the face box (default 1.5)")
    s.add_argument("--y-offset", dest="y_offset", type=float, default=-0.08, help="move the cover up by this fraction of its size")
    s.add_argument("--every", type=int, default=1, help="detect every Nth frame (2-3 is much faster on long clips)")
    s.add_argument("--at", type=float, default=0.0, help="detect: which second to look at")
    s.add_argument("--cover-video", dest="cover_video",
                   help="heads: an animated head to paste instead of a still (换头: keeps your body and gestures)")
    s.add_argument("--audio", help="face: the narration that drives the head")
    s.add_argument("--provider", default="motion", choices=["motion", "cmd"],
                   help="face: motion = built-in puppet (no GPU) · cmd = the model set in PHOTO_TALK_CMD")
    s.add_argument("--no-crop", dest="no_crop", action="store_true", help="face: do not auto-crop the photo to the head")
    s.set_defaults(fn=cmd_video)

    s = sub.add_parser("category", help="topic-vertical presets (platforms/sources/banned keywords/defaults): plain JSON files, not a database")
    s.add_argument("action", choices=["list", "show", "path", "delete", "export", "import"])
    s.add_argument("arg", nargs="?", help="show/path/delete: category id · export/import: file path")
    s.add_argument("--replace", action="store_true", help="import: replace all categories instead of merging")
    s.set_defaults(fn=cmd_category)

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
    if not getattr(args, "fn", None):
        return cmd_start(argparse.Namespace(project=None, picker=False, port=8765))
    try:
        return args.fn(args)
    except RuntimeError as e:          # missing API key, provider HTTP error, ffmpeg failure
        print(f"error: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
