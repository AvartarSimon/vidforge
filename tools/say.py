#!/usr/bin/env python3
"""Speak any text in a saved vidforge voice — without vidforge.

A "designed" voice (VoxCPM2) is not an audio file and not a model: it is a text description plus
the random seed that produced the take you liked. Same description + same seed + same model =
the same voice, on any machine. This script is the whole runtime, so the voice can be used in
other tools (Premiere, CapCut, a podcast, another program) by generating WAV files here.

Setup on the machine that will generate (needs an NVIDIA GPU, or Apple Silicon; on a plain CPU
it runs at roughly 40x realtime, i.e. minutes of compute per sentence):

    pip install voxcpm soundfile
    # first run downloads openbmb/VoxCPM2 (~4.7 GB) into ~/.cache/huggingface

Use:

    python say.py --voice Simon1 --text "今天我们讲一个关于火山的故事。" -o out.wav
    python say.py --voice Simon1 --file script.txt --split -o narration/   # one wav per line
    python say.py --desc "四十岁左右，磁性，低沉，温暖" --seed 776455128 --text "..." -o out.wav

--voice looks in ~/.vidforge/voices/voxcpm/<name>.json (copy that file to move a voice between
machines) or next to this script. With --desc/--seed no profile file is needed at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROFILE_DIRS = [Path.home() / ".vidforge" / "voices" / "voxcpm", Path(__file__).resolve().parent]


def load_profile(name: str) -> dict:
    for d in PROFILE_DIRS:
        p = d / f"{name}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise SystemExit(f"找不到声音 '{name}'。找过：{', '.join(str(d) for d in PROFILE_DIRS)}\n"
                     f"把 <名字>.json 拷到其中一个目录，或直接用 --desc/--seed。")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate speech in a saved VoxCPM2 voice.")
    ap.add_argument("--voice", help="saved profile name, e.g. Simon1")
    ap.add_argument("--desc", help="voice description (instead of --voice)")
    ap.add_argument("--seed", type=int, help="seed that fixes the voice (instead of --voice)")
    ap.add_argument("--text", help="text to speak")
    ap.add_argument("--file", type=Path, help="read the text from a file")
    ap.add_argument("--split", action="store_true", help="one wav per non-empty line of --file")
    ap.add_argument("-o", "--out", default="out.wav", help="output .wav, or a folder with --split")
    args = ap.parse_args()

    if args.voice:
        prof = load_profile(args.voice)
        description, seed = prof["description"], prof.get("seed")
    elif args.desc:
        description, seed = args.desc, args.seed
    else:
        return ap.error("give --voice, or --desc (+ optional --seed)")

    if args.file:
        raw = args.file.read_text(encoding="utf-8")
    elif args.text:
        raw = args.text
    else:
        raw = sys.stdin.read()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()] if args.split else [" ".join(raw.split())]
    if not lines or not lines[0]:
        return ap.error("没有要合成的文字")

    try:
        from voxcpm import VoxCPM
        import soundfile as sf
        import torch
    except ImportError:
        raise SystemExit("先安装：pip install voxcpm soundfile  （首次运行会下载约 4.7 GB 模型）")

    print(f"声音：{description!r}  seed={seed}")
    model = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
    out = Path(args.out)
    if args.split:
        out.mkdir(parents=True, exist_ok=True)
    for i, line in enumerate(lines, 1):
        # Seeding torch's global RNG before every call is what reproduces the voice: the installed
        # voxcpm's generate() takes no seed argument (its README example is out of date).
        if seed is not None:
            torch.manual_seed(seed)
        wav = model.generate(text=f"({description}){line}", cfg_value=2.0, inference_timesteps=10)
        dest = (out / f"{i:03d}.wav") if args.split else out
        sf.write(str(dest), wav, model.tts_model.sample_rate)
        print(f"  [{i}/{len(lines)}] {dest}  ←  {line[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
