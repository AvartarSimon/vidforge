"""VoxCPM2 provider — free, local, open-source (Apache-2.0, commercial use OK) alternative to
ElevenLabs Voice Design. Supports 30 languages + 9 Chinese dialects, designs a new voice from a
plain-text description with no reference audio, and runs entirely on your own machine (no key,
no per-character cost). https://github.com/OpenBMB/VoxCPM

Not installed with vidforge — it pulls in PyTorch and a multi-GB model, which most vidforge users
don't want. Set it up once, on the machine that will actually render:
    pip install voxcpm soundfile
Needs roughly an 8GB NVIDIA GPU for good speed, or plain CPU (slower than real-time, which is
fine — vidforge renders narration offline in batch, nothing here needs to be live).

Unlike ElevenLabs there's no server-side voice_id: "keeping" a voice just saves its description
and the random seed used for the preview you liked (`~/.vidforge/voices/voxcpm/<name>.json`) —
the seed *is* what makes every segment of a project reproduce the same-sounding take instead of
a fresh random voice each time. Use it as `"voice": "<saved name>"`, or skip saving entirely and
put `"voice": "(a description)"` straight in project.json.

⚠ Written from OpenBMB/VoxCPM's public README — model.generate(text=..., cfg_value=,
inference_timesteps=, seed=) -> a numpy wav array, model.tts_model.sample_rate for the rate —
not exercised against the real model here (no GPU/install on this machine). If the installed
package's exact API differs, this is the one place to adjust it.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

from .. import ffmpeg
from . import Word

VOICES_DIR = Path.home() / ".vidforge" / "voices" / "voxcpm"
_INLINE = re.compile(r"^\((?P<desc>.+)\)$")


class VoxCPMError(RuntimeError):
    pass


def _load_model():
    try:
        from voxcpm import VoxCPM
    except ImportError:
        raise VoxCPMError(
            "VoxCPM2 isn't installed on this machine. Run (on whichever machine actually "
            "renders — it needs the GPU/CPU, not just vidforge): pip install voxcpm soundfile "
            "— see https://github.com/OpenBMB/VoxCPM"
        ) from None
    return VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)


def _profile_path(name: str) -> Path:
    return VOICES_DIR / f"{re.sub(r'[^\w\-]+', '_', name.strip()) or 'voice'}.json"


def _sample_text(description: str) -> str:
    zh = any("一" <= ch <= "鿿" for ch in description)
    return ("一八一五年四月，在一个多数欧洲人从未听说过的岛上，一座山把自己撕开了。一年之内，六月飘雪，两个大陆的收成全部落空。" if zh else
            "In April 1815, on an island most Europeans had never heard of, a mountain tore itself apart. "
            "Within a year, snow was falling in June and the harvests of two continents had failed.")


def design(description: str, text: str | None = None, out_dir: Path | None = None, n: int = 3) -> list[dict]:
    """-> [{generated_voice_id, audio (Path), duration, seed}] — `n` independent generations at
    different seeds, so you can pick whichever take actually sounds right (VoxCPM2 has no
    separate lightweight "preview" call like ElevenLabs; each one here is a full generation, so
    this is slower than the ElevenLabs equivalent but costs nothing per call)."""
    model = _load_model()
    import soundfile as sf
    sample = (text or "").strip() or _sample_text(description)
    out_dir = Path(out_dir or (Path.home() / ".vidforge" / "voices"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    result = []
    for i in range(n):
        seed = int(hashlib.sha1(f"{description}:{stamp}:{i}".encode()).hexdigest()[:8], 16)
        wav = model.generate(text=f"({description}){sample}", cfg_value=2.0, inference_timesteps=10, seed=seed)
        f = out_dir / f"voxcpm_{stamp}_{i + 1}.wav"
        sf.write(str(f), wav, model.tts_model.sample_rate)
        result.append({"generated_voice_id": f"voxcpm:{seed}", "audio": f, "duration": ffmpeg.duration(f), "seed": seed})
    return result


def keep(generated_voice_id: str, name: str, description: str) -> str:
    """Save {description, seed} under `name`; returns `name` itself (there's no cloud id to
    hand back — the name you gave it IS the reference, same as any other saved voice)."""
    try:
        seed = int(generated_voice_id.split(":", 1)[1])
    except (IndexError, ValueError):
        raise VoxCPMError(f"not a VoxCPM2 preview id: {generated_voice_id!r}") from None
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    _profile_path(name).write_text(json.dumps({"description": description, "seed": seed}, ensure_ascii=False, indent=1), encoding="utf-8")
    return name


def _tokenize(text: str) -> list[str]:
    """Word/character tokens for even-spaced subtitle timing — same rule as the silent provider:
    CJK has no spaces, so fall back to one token per character."""
    tokens = text.split() or [text]
    if len(tokens) == 1 and len(text) > 8 and any("CJK" in unicodedata.name(ch, "") for ch in text):
        tokens = [ch for ch in text if not ch.isspace()]
    return tokens


class VoxCPMProvider:
    name = "voxcpm"

    def __init__(self, rate: str = "+0%", **_: object):
        self.rate = rate     # no documented speed knob in VoxCPM2 yet — kept for provider-contract parity
        self._model = None

    def _model_lazy(self):
        if self._model is None:
            self._model = _load_model()
        return self._model

    def _resolve(self, voice: str) -> tuple[str, int | None]:
        """`voice` is a saved profile name, or a literal "(a description)" used inline with no
        saved seed (so every render sounds like a fresh, differently-seeded take)."""
        voice = (voice or "").strip()
        m = _INLINE.match(voice)
        if m:
            return m.group("desc"), None
        p = _profile_path(voice)
        if p.is_file():
            prof = json.loads(p.read_text(encoding="utf-8"))
            return prof["description"], prof.get("seed")
        raise VoxCPMError(f"no saved VoxCPM2 voice named '{voice}' — `vidforge voice design --provider voxcpm "
                          f"--desc \"...\"` then `voice keep`, or set voice to \"(a description)\" directly.")

    def cache_key(self, text: str, voice: str) -> str:
        return hashlib.sha1(f"{voice}|{text}".encode("utf-8")).hexdigest()[:16]

    def synthesize(self, text: str, voice: str, out_path: Path) -> list[Word]:
        import soundfile as sf
        description, seed = self._resolve(voice)
        model = self._model_lazy()
        kwargs = {"cfg_value": 2.0, "inference_timesteps": 10}
        if seed is not None:
            kwargs["seed"] = seed
        wav = model.generate(text=f"({description}){text}", **kwargs)
        out_path = Path(out_path)
        wav_path = out_path.with_suffix(".wav")
        sf.write(str(wav_path), wav, model.tts_model.sample_rate)
        ffmpeg.run(["-y", "-i", str(wav_path), str(out_path)])       # mux to the project's audio format (mp3)
        wav_path.unlink(missing_ok=True)
        # No forced-alignment API here -> spread words evenly across the *real* rendered length
        # (measured, not estimated) instead of per-word timestamps. Subtitle breaks land close to
        # right at normal narration pace but won't be frame-accurate like edge-tts/ElevenLabs.
        total = ffmpeg.duration(out_path)
        tokens = _tokenize(text)
        step = total / max(1, len(tokens))
        return [Word(text=t, start=i * step, duration=step * 0.92) for i, t in enumerate(tokens)]

    def list_voices(self, lang_prefix: str | None) -> list[tuple[str, str]]:
        VOICES_DIR.mkdir(parents=True, exist_ok=True)
        out = []
        for f in sorted(VOICES_DIR.glob("*.json")):
            try:
                prof = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            desc = prof.get("description", "")
            if lang_prefix and lang_prefix.lower() not in desc.lower():
                continue
            out.append((f.stem, desc[:70]))
        return out
