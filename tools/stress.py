"""Generate a long synthetic project to measure build time and drift.

    python tools/stress.py out_dir --minutes 30 [--segments 40] [--quality final]
    vidforge build out_dir

Narration is the `silent` provider (length estimated from word count, ~2.6 words/s), so no
network is involved and the run measures rendering alone. Visuals: generated stills (a third
of them portrait, to exercise the blur fill) and a generated test video used as slices.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

WORDS = ("history empire river battle harvest winter city king trade fleet mountain treaty famine "
         "market silver road temple bridge plague council iron grain voyage frontier census "
         "monastery scholar canal siege dynasty merchant harbor caravan census decree").split()


def sentence(rng: random.Random, n: int) -> str:
    w = [rng.choice(WORDS) for _ in range(n)]
    w[0] = w[0].capitalize()
    return " ".join(w) + rng.choice([".", ".", ".", ",", "!"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--segments", type=int, default=40)
    ap.add_argument("--quality", default="final")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    a = ap.parse_args()
    rng = random.Random(7)
    root = Path(a.out); (root / "assets").mkdir(parents=True, exist_ok=True)

    words_total = int(a.minutes * 60 * 2.6)
    per_seg = words_total // a.segments

    # stills: 12 images, a third portrait
    for i in range(12):
        portrait = i % 3 == 0
        size = (1200, 1800) if portrait else (2400, 1350)
        img = Image.new("RGB", size, (30 + i * 15, 60 + (i * 37) % 120, 90 + (i * 53) % 140))
        d = ImageDraw.Draw(img)
        for k in range(0, size[0] + size[1], 120):
            d.line([(k, 0), (0, k)], fill=(255, 255, 255), width=6)
        d.text((60, 60), f"still {i:02d}", fill="white", font_size=110)
        img.save(root / "assets" / f"still{i:02d}.jpg", quality=90)
    # one 20 s test video
    vid = root / "assets" / "clip.mp4"
    if not vid.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30", "-t", "20",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", str(vid)], check=True)

    segments = []
    for i in range(a.segments):
        text = " ".join(sentence(rng, rng.randint(9, 16)) for _ in range(max(1, per_seg // 12)))
        clips = []
        kind = i % 4
        if kind == 0:
            clips = [{"image": f"assets/still{(i * 5) % 12:02d}.jpg", "motion": rng.choice(["zoom_in", "zoom_out", "pan_left", "pan_right"])}]
        elif kind == 1:
            s = rng.uniform(0, 10)
            clips = [{"video": "assets/clip.mp4", "in": round(s, 1), "out": round(s + 6, 1)},
                     {"image": f"assets/still{(i * 7) % 12:02d}.jpg", "motion": "zoom_in"}]
        elif kind == 2:
            clips = [{"image": f"assets/still{(i * 3) % 12:02d}.jpg", "duration": 8, "motion": "pan_right"},
                     {"image": f"assets/still{(i * 3 + 1) % 12:02d}.jpg", "motion": "zoom_out"},
                     {"image": f"assets/still{(i * 3 + 2) % 12:02d}.jpg", "motion": "pan_left"}]
        else:
            clips = [{"video": "assets/clip.mp4", "in": 2, "out": 5}, {"video": "assets/clip.mp4", "in": 12}]
        segments.append({"id": f"s{i + 1:02d}", "label": f"Chapter {i + 1}" if i % 5 == 0 else None, "text": text, "clips": clips})
        if segments[-1]["label"] is None:
            del segments[-1]["label"]

    project = {"title": f"Stress {a.minutes:g} min", "tts": {"provider": "silent"}, "quality": a.quality,
               "width": a.width, "height": a.height, "fps": 30, "thumbnail_text": "STRESS", "segments": segments}
    (root / "project.json").write_text(json.dumps(project, indent=1), encoding="utf-8")
    est = words_total / 2.6 / 60
    print(f"wrote {root / 'project.json'}: {a.segments} segments, ~{est:.1f} min of narration")


if __name__ == "__main__":
    main()
