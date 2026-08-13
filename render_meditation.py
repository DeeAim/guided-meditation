#!/usr/bin/env python3
"""
Render a guided-meditation Markdown script to WAV.

Current backend:
    - Kokoro-82M

Designed so additional backends (for example Chatterbox Nano/Turbo)
can be added without changing the script parser or audio assembler.

Script syntax:
    # Heading                 -> not spoken
    Normal paragraph text.   -> spoken
    [pause 4s]               -> exactly 4 seconds of digital silence

Example:
    python render_meditation.py scripts/test.md \
        --backend kokoro \
        --voice af_nicole \
        --speed 0.90 \
        --output output/test-af_nicole.wav
"""

from __future__ import annotations

import argparse
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import soundfile as sf


SAMPLE_RATE_KOKORO = 24_000
PAUSE_RE = re.compile(
    r"^\s*\[\s*pause\s+([0-9]+(?:\.[0-9]+)?)\s*s(?:ec(?:onds?)?)?\s*\]\s*$",
    re.IGNORECASE,
)


@dataclass
class ScriptItem:
    kind: str  # "speech" or "silence"
    text: str | None = None
    seconds: float | None = None


@dataclass
class RenderedItem:
    index: int
    kind: str
    path: str
    duration_seconds: float
    text: str | None = None
    requested_pause_seconds: float | None = None


class TTSBackend(ABC):
    """Common interface for interchangeable speech engines."""

    sample_rate: int

    @abstractmethod
    def synthesize(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        """Return mono float audio and sample rate."""
        raise NotImplementedError


class KokoroBackend(TTSBackend):
    """Kokoro-82M implementation."""

    sample_rate = SAMPLE_RATE_KOKORO
    SUPPORTED_LANG_CODES = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}

    def __init__(self, lang_code: str = "auto") -> None:
        self.requested_lang_code = lang_code
        self._pipelines: dict[str, object] = {}

    def _lang_for_voice(self, voice: str) -> str:
        if self.requested_lang_code != "auto":
            return self.requested_lang_code

        if not voice:
            raise ValueError("Voice cannot be empty.")

        lang_code = voice[0].lower()
        if lang_code not in self.SUPPORTED_LANG_CODES:
            raise ValueError(
                f"Could not infer Kokoro language from voice '{voice}'. "
                "Pass --lang-code explicitly."
            )
        return lang_code

    def _pipeline(self, lang_code: str):
        if lang_code not in self._pipelines:
            try:
                from kokoro import KPipeline
            except ImportError as exc:
                raise RuntimeError(
                    "Kokoro is not installed. Run: pip install -r requirements.txt"
                ) from exc

            print(f"Loading Kokoro pipeline for lang_code='{lang_code}'...")
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code,
                repo_id="hexgrad/Kokoro-82M",
            )

        return self._pipelines[lang_code]

    def synthesize(self, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
        lang_code = self._lang_for_voice(voice)
        pipeline = self._pipeline(lang_code)

        chunks: list[np.ndarray] = []

        # Kokoro may return more than one generated chunk for a longer passage.
        generator = pipeline(text, voice=voice, speed=speed)

        for result in generator:
            # Kokoro 0.9.x examples support tuple unpacking:
            # (graphemes, phonemes, audio)
            try:
                _, _, audio = result
            except (TypeError, ValueError):
                # Also support result-like objects exposing `.audio`.
                audio = getattr(result, "audio", None)
                if audio is None:
                    raise RuntimeError(
                        "Unexpected Kokoro result format; could not locate audio."
                    )

            # Torch tensors and numpy arrays both work through np.asarray
            # after moving tensor data to CPU when necessary.
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio_np = np.asarray(audio, dtype=np.float32).reshape(-1)

            if audio_np.size:
                chunks.append(audio_np)

        if not chunks:
            raise RuntimeError(f"Kokoro produced no audio for: {text!r}")

        return np.concatenate(chunks), SAMPLE_RATE_KOKORO


def build_backend(name: str, lang_code: str) -> TTSBackend:
    name = name.lower()

    if name == "kokoro":
        return KokoroBackend(lang_code=lang_code)

    # Future backends can be added here without touching parsing/assembly.
    # Example:
    # if name == "chatterbox-nano":
    #     return ChatterboxNanoBackend(...)
    # if name == "chatterbox-turbo":
    #     return ChatterboxTurboBackend(...)

    raise ValueError(
        f"Unknown backend '{name}'. Currently implemented: kokoro"
    )


def parse_script(path: Path) -> list[ScriptItem]:
    """
    Parse Markdown into speech/silence items.

    Rules:
    - Markdown ATX headings (#, ##, ...) are production labels and are not spoken.
    - [pause Ns] becomes exact silence.
    - Consecutive nonblank narration lines are merged into one speech block.
    - Blank lines end a speech block.
    """
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    items: list[ScriptItem] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(line.strip() for line in paragraph).strip()
            if text:
                items.append(ScriptItem(kind="speech", text=text))
            paragraph.clear()

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            continue

        if re.match(r"^#{1,6}\s+", stripped):
            flush_paragraph()
            continue

        pause_match = PAUSE_RE.match(stripped)
        if pause_match:
            flush_paragraph()
            seconds = float(pause_match.group(1))
            if seconds < 0:
                raise ValueError("Pause length cannot be negative.")
            items.append(ScriptItem(kind="silence", seconds=seconds))
            continue

        paragraph.append(stripped)

    flush_paragraph()

    if not items:
        raise ValueError(f"No narration or pause markers found in {path}")

    return items


def silence(seconds: float, sample_rate: int) -> np.ndarray:
    frames = int(round(seconds * sample_rate))
    return np.zeros(frames, dtype=np.float32)


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or "render"


def render(
    script_path: Path,
    backend_name: str,
    voice: str,
    speed: float,
    output_path: Path,
    segments_dir: Path,
    manifests_dir: Path,
    lang_code: str,
) -> Path:
    if speed <= 0:
        raise ValueError("--speed must be greater than 0.")

    items = parse_script(script_path)
    backend = build_backend(backend_name, lang_code)

    segments_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    final_parts: list[np.ndarray] = []
    rendered_items: list[RenderedItem] = []
    sample_rate = backend.sample_rate

    print(f"Script:  {script_path}")
    print(f"Backend: {backend_name}")
    print(f"Voice:   {voice}")
    print(f"Speed:   {speed}")
    print()

    for index, item in enumerate(items, start=1):
        if item.kind == "speech":
            assert item.text is not None
            print(f"[{index:03}] Speech: {item.text}")

            audio, sr = backend.synthesize(item.text, voice=voice, speed=speed)

            if sr != sample_rate:
                raise RuntimeError(
                    f"Sample-rate mismatch: expected {sample_rate}, received {sr}"
                )

            segment_path = segments_dir / f"{index:03d}_speech.wav"
            sf.write(segment_path, audio, sample_rate, subtype="PCM_16")
            final_parts.append(audio)

            rendered_items.append(
                RenderedItem(
                    index=index,
                    kind="speech",
                    path=str(segment_path),
                    duration_seconds=len(audio) / sample_rate,
                    text=item.text,
                )
            )

        elif item.kind == "silence":
            assert item.seconds is not None

            sr = sample_rate
            pause_audio = silence(item.seconds, sr)

            print(f"[{index:03}] Pause:  {item.seconds:g}s")

            segment_path = segments_dir / f"{index:03d}_pause_{item.seconds:g}s.wav"
            sf.write(segment_path, pause_audio, sr, subtype="PCM_16")
            final_parts.append(pause_audio)

            rendered_items.append(
                RenderedItem(
                    index=index,
                    kind="silence",
                    path=str(segment_path),
                    duration_seconds=len(pause_audio) / sr,
                    requested_pause_seconds=item.seconds,
                )
            )
        else:
            raise RuntimeError(f"Unsupported script item: {item.kind}")

    if not final_parts:
        raise RuntimeError("Nothing was rendered.")

    # Speech and silence are kept at the backend's declared sample rate.
    final_audio = np.concatenate(final_parts).astype(np.float32, copy=False)

    # Safety against accidental clipping from a backend.
    peak = float(np.max(np.abs(final_audio))) if final_audio.size else 0.0
    if peak > 1.0:
        print(f"Warning: peak {peak:.3f} exceeds 1.0; normalizing to prevent clipping.")
        final_audio = final_audio / peak * 0.999

    sf.write(output_path, final_audio, sample_rate, subtype="PCM_16")

    manifest_name = (
        f"{safe_name(script_path.stem)}-{safe_name(backend_name)}-"
        f"{safe_name(voice)}.json"
    )
    manifest_path = manifests_dir / manifest_name

    manifest = {
        "script": str(script_path),
        "backend": backend_name,
        "voice": voice,
        "speed": speed,
        "sample_rate": sample_rate,
        "output": str(output_path),
        "duration_seconds": len(final_audio) / sample_rate,
        "items": [asdict(item) for item in rendered_items],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("Done.")
    print(f"Output:   {output_path}")
    print(f"Duration: {len(final_audio) / sample_rate:.2f}s")
    print(f"Manifest: {manifest_path}")

    return output_path


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a guided-meditation Markdown script to WAV."
    )
    parser.add_argument("script", type=Path, help="Path to meditation Markdown file")
    parser.add_argument(
        "--backend",
        default="kokoro",
        help="TTS backend (currently: kokoro)",
    )
    parser.add_argument(
        "--voice",
        default="af_nicole",
        help="Backend voice name, e.g. af_nicole or bf_isabella",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.90,
        help="Speech speed multiplier passed to the TTS backend (default: 0.90)",
    )
    parser.add_argument(
        "--lang-code",
        default="auto",
        help="Kokoro language code. 'auto' infers it from the voice prefix.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Final WAV path. Default: output/<script>-<voice>.wav",
    )
    parser.add_argument(
        "--segments-dir",
        type=Path,
        default=Path("segments"),
        help="Directory for rendered speech/pause segments",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=Path("manifests"),
        help="Directory for JSON render manifests",
    )
    return parser


def main() -> None:
    args = make_parser().parse_args()

    script_path: Path = args.script
    if not script_path.exists():
        raise SystemExit(f"Script not found: {script_path}")

    output_path = args.output
    if output_path is None:
        output_path = Path("output") / (
            f"{safe_name(script_path.stem)}-{safe_name(args.voice)}.wav"
        )

    try:
        render(
            script_path=script_path,
            backend_name=args.backend,
            voice=args.voice,
            speed=args.speed,
            output_path=output_path,
            segments_dir=args.segments_dir,
            manifests_dir=args.manifests_dir,
            lang_code=args.lang_code,
        )
    except Exception as exc:
        raise SystemExit(f"Render failed: {exc}") from exc


if __name__ == "__main__":
    main()