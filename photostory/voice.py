"""Talking photos: offline text-to-speech with Piper, plus the video's audio track.

Each speaker ("the smiling pumpkin", "the explorer in the bubble helmet") gets a stable
voice picked from a multi-speaker model, so the same speaker sounds the same every week.
Voices are generic synthetic voices; this never imitates real people's voices.

The default model (LibriTTS, 904 speakers, MIT-licensed Piper release) is downloaded
once from GitHub and cached. Install with `pip install ".[voice]"`.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import tarfile
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL_URL = "https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-libritts-high.tar.gz"
# Hand-picked spread of LibriTTS speaker ids (mixed pitch/gender); a speaker label always maps to the same one.
DEFAULT_SPEAKER_IDS = [0, 14, 30, 61, 102, 150, 211, 340, 466, 580, 712, 860]


@dataclass
class Clip:
    pcm: bytes  # 16-bit mono PCM
    rate: int

    @property
    def seconds(self) -> float:
        return len(self.pcm) / 2 / self.rate


class Synth(Protocol):
    def __call__(self, text: str, speaker: str) -> Clip: ...


def speaker_id_for(label: str, palette: list[int]) -> int:
    h = int(hashlib.sha256(label.strip().lower().encode()).hexdigest(), 16)
    return palette[h % len(palette)]


def ensure_model(url: str = DEFAULT_MODEL_URL, cache_dir: str | Path = "~/.cache/photostory/voices") -> Path:
    """Return the path of the .onnx voice model, downloading and unpacking it once."""
    if path := os.getenv("PHOTOSTORY_VOICE_MODEL"):
        return Path(path)
    cache = Path(cache_dir).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    found = sorted(cache.glob("*.onnx"))
    if found:
        return found[0]
    log.info("Downloading voice model (one time): %s", url)
    data = urllib.request.urlopen(url, timeout=300).read()  # noqa: S310 (fixed https URL from config)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            name = Path(m.name).name
            if m.isfile() and (name.endswith(".onnx") or name.endswith(".onnx.json")):
                (cache / name).write_bytes(tar.extractfile(m).read())
    found = sorted(cache.glob("*.onnx"))
    if not found:
        raise RuntimeError("Voice model archive did not contain an .onnx file")
    return found[0]


def piper_synth(model: Path, palette: list[int] | None = None, length_scale: float = 1.0) -> Synth:
    from piper import PiperVoice, SynthesisConfig

    voice = PiperVoice.load(str(model), config_path=str(model) + ".json")
    palette = palette or DEFAULT_SPEAKER_IDS
    multi = (voice.config.num_speakers or 1) > 1

    def synth(text: str, speaker: str) -> Clip:
        cfg = SynthesisConfig(speaker_id=speaker_id_for(speaker, palette) if multi else None, length_scale=length_scale)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(text, w, syn_config=cfg)
        buf.seek(0)
        with wave.open(buf, "rb") as r:
            return Clip(pcm=r.readframes(r.getnframes()), rate=r.getframerate())

    return synth


def silence(seconds: float, rate: int) -> bytes:
    return b"\x00\x00" * max(0, round(seconds * rate))


def build_track(segments: list[tuple[float, Clip | None, float]], rate: int) -> bytes:
    """segments: (scene_seconds, clip, clip_start). Returns 16-bit mono PCM covering all scenes."""
    out = bytearray()
    for seconds, clip, start in segments:
        scene = bytearray(silence(seconds, rate))
        if clip:
            if clip.rate != rate:
                raise ValueError("all clips must share one sample rate")
            off = round(start * rate) * 2
            pcm = clip.pcm[: len(scene) - off]
            scene[off: off + len(pcm)] = pcm
        out += scene
    return bytes(out)


def write_wav(path: Path, pcm: bytes, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def make_synth(model_url: str, cache_dir: str, palette: list[int], length_scale: float) -> Synth | None:
    """A ready synth, or None (with a warning) if Piper or the model isn't available."""
    try:
        return piper_synth(ensure_model(model_url, cache_dir), palette, length_scale)
    except Exception as e:
        log.warning("Talking photos disabled (%s). Install with: pip install '.[voice]'", e)
        return None


SynthFactory = Callable[[], "Synth | None"]
