#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import soundfile as sf
import yaml

PAUSE_RE = re.compile(r"^\s*\[\s*pause\s+([0-9]+(?:\.[0-9]+)?)\s*s(?:ec(?:onds?)?)?\s*\]\s*$", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
ROUGH_TOKEN_RE = re.compile(r"\w+(?:['’\-]\w+)*|[^\w\s]", re.UNICODE)


@dataclass
class ScriptItem:
    kind: str
    text: Optional[str] = None
    seconds: Optional[float] = None


@dataclass
class AudioResult:
    audio: np.ndarray
    sample_rate: int
    metadata: dict[str, Any]


@dataclass
class RenderedItem:
    index: int
    kind: str
    path: str
    duration_seconds: float
    text: Optional[str] = None
    requested_pause_seconds: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None


class TTSBackend(ABC):
    supports_native_speed = False

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings

    @abstractmethod
    def synthesize(self, text: str, voice: Optional[str], speed: float) -> AudioResult:
        raise NotImplementedError

    def synthesize_contextual(self, target: str, before: list[str], after: list[str], voice: Optional[str], speed: float, context_settings: dict[str, Any]) -> AudioResult:
        return self.synthesize(target, voice=voice, speed=speed)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-") or "render"


def reference_voice_label(reference_audio: Optional[str | Path]) -> Optional[str]:
    """
    Convert a Chatterbox reference filename into a compact output label.

    Examples:
      meditation-female-cori-samuel.wav -> cori-samuel
      meditation-male-chris_vocals.wav  -> chris_vocals
      meditation-male-clive-catterall.wav -> clive-catterall

    If the filename does not have at least three hyphen-separated parts,
    use the whole stem.
    """
    if not reference_audio:
        return None
    stem = Path(str(reference_audio)).stem
    parts = stem.split("-")
    return "-".join(parts[2:]) if len(parts) >= 3 else stem


def rough_token_count(text: str) -> int:
    return len(ROUGH_TOKEN_RE.findall(text))


def to_mono_float(audio: Any) -> np.ndarray:
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim <= 1:
        return arr.reshape(-1)
    if arr.shape[0] <= 8:
        arr = np.mean(arr, axis=0)
    else:
        arr = np.mean(arr, axis=-1)
    return np.asarray(arr, dtype=np.float32).reshape(-1)


def resolve_device(requested: str) -> str:
    requested = (requested or "auto").lower()
    if requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


class KokoroBackend(TTSBackend):
    supports_native_speed = True
    sample_rate = 24000
    supported_lang_codes = {"a", "b", "e", "f", "h", "i", "j", "p", "z"}

    def __init__(self, settings: dict[str, Any]) -> None:
        super().__init__(settings)
        self.repo_id = settings.get("repo_id", "hexgrad/Kokoro-82M")
        self.requested_lang_code = str(settings.get("lang_code", "auto"))
        self.device = resolve_device(str(settings.get("device", "auto")))
        self._pipelines: dict[str, Any] = {}

        # Cache custom weighted voice tensors so they are only built once
        # per render process.
        self._voice_blends: dict[str, Any] = {}

    @staticmethod
    def _voice_components(voice: Optional[str]) -> list[tuple[str, float]]:
        """
        Parse Kokoro voice specifications.

        Supported:
            af_heart
            af_heart,af_bella
            af_heart:8,af_bella:2
            af_heart:0.8,af_bella:0.2
            af_heart:70,af_bella:20,am_fenrir:10

        Weights are automatically normalized, so:
            8:2 == 80:20 == 0.8:0.2
        """
        if not voice:
            raise ValueError("Kokoro requires a voice name.")

        components: list[tuple[str, float]] = []

        for raw_part in str(voice).split(","):
            raw_part = raw_part.strip()
            if not raw_part:
                continue

            if ":" in raw_part:
                name, weight_text = raw_part.rsplit(":", 1)
                name = name.strip()

                try:
                    weight = float(weight_text.strip())
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid Kokoro voice weight in '{raw_part}'. "
                        "Example: af_heart:8,af_bella:2"
                    ) from exc
            else:
                name = raw_part
                weight = 1.0

            if not name:
                raise ValueError(f"Invalid Kokoro voice specification: '{raw_part}'")

            if weight < 0:
                raise ValueError(
                    f"Kokoro voice weights cannot be negative: '{raw_part}'"
                )

            components.append((name, weight))

        if not components:
            raise ValueError("Kokoro requires at least one voice name.")

        total_weight = sum(weight for _, weight in components)

        if total_weight <= 0:
            raise ValueError("At least one Kokoro voice weight must be greater than 0.")

        # Normalize automatically.
        return [
            (name, weight / total_weight)
            for name, weight in components
        ]


    def _voice_parts(self, voice: Optional[str]) -> list[str]:
        return [name for name, _ in self._voice_components(voice)]


    def _voice_mix_metadata(self, voice: Optional[str]) -> dict[str, float]:
        return {
            name: weight
            for name, weight in self._voice_components(voice)
        }


    def _voice_pack(self, pipeline: Any, voice: Optional[str]):
        """
        Build the Kokoro voice tensor.

        A single voice uses its original pack.

        Multiple voices are combined using normalized weighted interpolation.
        """
        components = self._voice_components(voice)

        if len(components) == 1:
            name, _ = components[0]
            return pipeline.load_voice(name)

        # Canonical normalized cache key.
        cache_key = ",".join(
            f"{name}:{weight:.8f}"
            for name, weight in components
        )

        if cache_key in self._voice_blends:
            return self._voice_blends[cache_key]

        blended = None

        for name, weight in components:
            pack = pipeline.load_voice(name)

            weighted_pack = pack * weight

            if blended is None:
                blended = weighted_pack
            else:
                blended = blended + weighted_pack

        self._voice_blends[cache_key] = blended
        return blended

    def _lang_for_voice(self, voice: Optional[str]) -> str:
        if self.requested_lang_code != "auto":
            return self.requested_lang_code

        parts = self._voice_parts(voice)
        codes = {part[0].lower() for part in parts}

        unknown = [code for code in codes if code not in self.supported_lang_codes]
        if unknown:
            raise ValueError(f"Cannot infer Kokoro language from voice '{voice}'.")

        if len(codes) != 1:
            raise ValueError(
                "Kokoro blended voices must use the same language pipeline. "
                f"Received: {', '.join(parts)}"
            )
        return next(iter(codes))

    def _pipeline(self, voice: Optional[str]):
        lang_code = self._lang_for_voice(voice)
        if lang_code not in self._pipelines:
            try:
                from kokoro import KPipeline
            except ImportError as exc:
                raise RuntimeError("Kokoro is not installed in this Python environment.") from exc
            print(f"Loading Kokoro: lang_code='{lang_code}', device='{self.device}', repo_id='{self.repo_id}'...")
            self._pipelines[lang_code] = KPipeline(lang_code=lang_code, repo_id=self.repo_id, device=self.device)
        return self._pipelines[lang_code]

    def _token_count(self, text: str, voice: Optional[str]) -> int:
        pipeline = self._pipeline(voice)
        if getattr(pipeline, "lang_code", None) not in {"a", "b"}:
            return rough_token_count(text)
        try:
            _, tokens = pipeline.g2p(text)
            return len(pipeline.tokens_to_ps(tokens))
        except Exception:
            return rough_token_count(text)

    def synthesize(self, text: str, voice: Optional[str], speed: float) -> AudioResult:
        pipeline = self._pipeline(voice)

        # Build either the original single voice tensor or our custom
        # weighted blend tensor.
        voice_pack = self._voice_pack(pipeline, voice)

        parts: list[np.ndarray] = []
        counts: list[int] = []

        for result in pipeline(
            text,
            voice=voice_pack,
            speed=speed,
            split_pattern=None
        ):
            audio = getattr(result, "audio", None)
            if audio is None:
                try:
                    _, _, audio = result
                except Exception as exc:
                    raise RuntimeError("Unexpected Kokoro result format.") from exc
            a = to_mono_float(audio)
            if a.size:
                parts.append(a)
            counts.append(len(getattr(result, "phonemes", "") or ""))
        if not parts:
            raise RuntimeError(f"Kokoro produced no audio for: {text!r}")
        return AudioResult(
            np.concatenate(parts),
            self.sample_rate,
            {
                "backend": "kokoro",
                "kokoro_tokens": sum(counts),
                "contextual": False,
                "voice_mix": self._voice_mix_metadata(voice),
            },
        )

    def _build_context(self, target: str, before: list[str], after: list[str], voice: Optional[str], cfg: dict[str, Any]) -> tuple[str, int, int]:
        target_tokens = int(cfg.get("target_tokens", 150))
        max_tokens = int(cfg.get("max_tokens", 200))
        selected_before: list[str] = []
        selected_after: list[str] = []
        left = list(reversed(before))
        right = list(after)
        li = ri = 0

        def assemble():
            prefix = " ".join(reversed(selected_before)).strip()
            suffix = " ".join(selected_after).strip()
            full = " ".join(p for p in (prefix, target.strip(), suffix) if p).strip()
            start = len(prefix) + (1 if prefix else 0)
            return full, start

        full, start = assemble()
        count = self._token_count(full, voice)
        while count < target_tokens and (li < len(left) or ri < len(right)):
            candidates = []
            if li < len(left): candidates.append(("left", left[li]))
            if ri < len(right): candidates.append(("right", right[ri]))
            best = None
            best_count = None
            for side, candidate in candidates:
                old_b, old_a = list(selected_before), list(selected_after)
                (selected_before if side == "left" else selected_after).append(candidate)
                candidate_full, _ = assemble()
                c = self._token_count(candidate_full, voice)
                selected_before[:] = old_b
                selected_after[:] = old_a
                if c <= max_tokens and (best_count is None or abs(target_tokens - c) < abs(target_tokens - best_count)):
                    best, best_count = (side, candidate), c
            if best is None:
                break
            side, candidate = best
            if side == "left":
                selected_before.append(candidate); li += 1
            else:
                selected_after.append(candidate); ri += 1
            full, start = assemble()
            count = self._token_count(full, voice)
        return full, start, count

    @staticmethod
    def _crop_target(result: Any, target: str, expected_start: int, sample_rate: int, pad_ms: float) -> Optional[np.ndarray]:
        tokens = getattr(result, "tokens", None)
        audio = getattr(result, "audio", None)
        graphemes = getattr(result, "graphemes", "")
        if not tokens or audio is None or not graphemes:
            return None
        target = target.strip()
        positions = [m.start() for m in re.finditer(re.escape(target), graphemes)]
        if not positions:
            return None
        target_start = min(positions, key=lambda p: abs(p - expected_start))
        target_end = target_start + len(target)
        cursor = 0
        selected: list[tuple[float, float]] = []
        for token in tokens:
            rendered = (getattr(token, "text", "") or "") + (getattr(token, "whitespace", "") or "")
            s, e = cursor, cursor + len(rendered)
            cursor = e
            if e <= target_start or s >= target_end:
                continue
            sts, ets = getattr(token, "start_ts", None), getattr(token, "end_ts", None)
            if sts is not None and ets is not None:
                selected.append((float(sts), float(ets)))
        if not selected:
            return None
        a = to_mono_float(audio)
        pad = max(0.0, pad_ms / 1000.0)
        s = max(0, int(math.floor(max(0.0, selected[0][0] - pad) * sample_rate)))
        e = min(len(a), int(math.ceil(min(len(a) / sample_rate, selected[-1][1] + pad) * sample_rate)))
        return None if e <= s else a[s:e]

    def synthesize_contextual(self, target: str, before: list[str], after: list[str], voice: Optional[str], speed: float, context_settings: dict[str, Any]) -> AudioResult:
        if not bool(context_settings.get("enabled", True)):
            return self.synthesize(target, voice, speed)
        direct_tokens = self._token_count(target, voice)
        threshold = int(context_settings.get("short_segment_threshold", 20))
        if direct_tokens >= threshold:
            result = self.synthesize(target, voice, speed)
            result.metadata["direct_target_tokens"] = direct_tokens
            return result
        full, target_start, context_tokens = self._build_context(target, before, after, voice, context_settings)
        if context_tokens < int(context_settings.get("min_tokens", 100)):
            result = self.synthesize(target, voice, speed)
            result.metadata.update({"direct_target_tokens": direct_tokens, "context_attempt_tokens": context_tokens, "context_reason": "not_enough_neighbor_context"})
            return result
        pipeline = self._pipeline(voice)
        voice_pack = self._voice_pack(pipeline, voice)
        generated = list(
            pipeline(
                full,
                voice=voice_pack,
                speed=speed,
                split_pattern=None
            )
        )
        if len(generated) != 1:
            result = self.synthesize(target, voice, speed)
            result.metadata.update({"direct_target_tokens": direct_tokens, "context_attempt_tokens": context_tokens, "context_reason": "kokoro_internal_chunking"})
            return result
        cropped = self._crop_target(generated[0], target, target_start, self.sample_rate, float(context_settings.get("crop_pad_ms", 60)))
        if cropped is None or not cropped.size:
            result = self.synthesize(target, voice, speed)
            result.metadata.update({"direct_target_tokens": direct_tokens, "context_attempt_tokens": context_tokens, "context_reason": "timestamp_crop_failed"})
            return result
        return AudioResult(cropped, self.sample_rate, {"backend": "kokoro", "contextual": True, "direct_target_tokens": direct_tokens, "context_tokens": context_tokens, "crop_pad_ms": float(context_settings.get("crop_pad_ms", 60))})


class ChatterboxBackend(TTSBackend):
    supports_native_speed = False

    def __init__(self, settings: dict[str, Any], nano: bool) -> None:
        super().__init__(settings)
        self.nano = nano
        self.device = resolve_device(str(settings.get("device", "auto")))
        self.reference_audio = settings.get("reference_audio")
        self.generation = settings.get("generation", {}) or {}

        # Conservative long-form defaults. These are intentionally below the
        # model tokenizer's technical 1024-token limit because long Turbo
        # generations are substantially less reliable in practice.
        self.chunking = {
            "enabled": True,
            "target_tokens": 45,
            "max_tokens": 65,
            "max_chars": 300,
            **(settings.get("chunking", {}) or {}),
        }

        self._model = None
        self._prepared_reference: Optional[str] = None

    @property
    def backend_name(self):
        return "chatterbox-nano" if self.nano else "chatterbox-turbo"

    def _load_model(self):
        if self._model is None:
            try:
                from chatterbox.tts_turbo import ChatterboxTurboTTS
            except ImportError as exc:
                raise RuntimeError("Chatterbox is not installed in this Python environment.") from exc
            print(f"Loading {'Chatterbox Nano' if self.nano else 'Chatterbox Turbo'} on device='{self.device}'...")
            self._model = ChatterboxTurboTTS.from_pretrained(device=self.device, nano=self.nano)
        return self._model

    def text_token_count(self, text: str) -> int:
        """Count tokens with the exact tokenizer used by Chatterbox Turbo/Nano."""
        model = self._load_model()
        encoded = model.tokenizer(
            text,
            return_tensors="pt",
            padding=False,
            truncation=False,
        )
        return int(encoded.input_ids.shape[-1])

    def synthesize(self, text: str, voice: Optional[str], speed: float) -> AudioResult:
        model = self._load_model()
        reference_audio = self.reference_audio
        if voice and voice not in {"default", "builtin"} and Path(str(voice)).exists():
            reference_audio = str(voice)
        kwargs = {
            "repetition_penalty": float(self.generation.get("repetition_penalty", 1.2)),
            "min_p": float(self.generation.get("min_p", 0.0)),
            "top_p": float(self.generation.get("top_p", 0.95)),
            "temperature": float(self.generation.get("temperature", 0.8)),
            "top_k": int(self.generation.get("top_k", 1000)),
        }
        if reference_audio:
            ref = Path(str(reference_audio))
            if not ref.exists():
                raise FileNotFoundError(f"Reference audio not found: {ref}")

            # Prepare the reference once and reuse the conditionals for every
            # chunk. This is faster and keeps long-form rendering consistent.
            resolved_ref = str(ref.resolve())
            if self._prepared_reference != resolved_ref:
                model.prepare_conditionals(str(ref))
                self._prepared_reference = resolved_ref

        try:
            # Once conditionals are prepared, generate() does not need to
            # re-read/re-encode the reference WAV for every text chunk.
            wav = model.generate(text, **kwargs)
        except AssertionError as exc:
            raise RuntimeError("Chatterbox needs usable built-in conditionals or a >5 second reference WAV.") from exc

        return AudioResult(
            to_mono_float(wav),
            int(model.sr),
            {
                "backend": self.backend_name,
                "reference_audio": str(reference_audio) if reference_audio else None,
                "reference_label": reference_voice_label(reference_audio),
                "text_tokens": self.text_token_count(text),
                "characters": len(text),
                "generation": kwargs,
                "contextual": False,
            },
        )


def build_backend(name: str, settings: dict[str, Any]) -> TTSBackend:
    if name == "kokoro": return KokoroBackend(settings)
    if name == "chatterbox-nano": return ChatterboxBackend(settings, nano=True)
    if name == "chatterbox-turbo": return ChatterboxBackend(settings, nano=False)
    raise ValueError(f"Unknown backend '{name}'.")


def load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping.")
    return data


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        result[k] = deep_merge(result[k], v) if isinstance(result.get(k), dict) and isinstance(v, dict) else v
    return result


def resolve_preset(config: dict[str, Any], name: Optional[str]) -> dict[str, Any]:
    defaults = config.get("defaults", {}) or {}
    presets = config.get("presets", {}) or {}
    name = name or defaults.get("preset")
    if not name or name not in presets:
        raise ValueError(f"Unknown preset '{name}'. Available: {', '.join(sorted(presets))}")
    resolved = deep_merge(defaults, presets[name] or {})
    resolved["preset_name"] = name
    return resolved


def parse_script(path: Path) -> list[ScriptItem]:
    items: list[ScriptItem] = []
    paragraph: list[str] = []
    def flush():
        if paragraph:
            text = " ".join(x.strip() for x in paragraph).strip()
            paragraph.clear()
            if text: items.append(ScriptItem("speech", text=text))
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            flush(); continue
        if re.match(r"^#{1,6}\s+", stripped):
            flush(); continue
        m = PAUSE_RE.match(stripped)
        if m:
            flush(); items.append(ScriptItem("silence", seconds=float(m.group(1)))); continue
        paragraph.append(stripped)
    flush()
    if not items: raise ValueError(f"No narration found in {path}")
    return items


def detect_script_profile(items: list[ScriptItem]) -> str:
    speech = [i for i in items if i.kind == "speech" and i.text]
    pauses = [i for i in items if i.kind == "silence"]
    if not speech: return "prose"
    short_ratio = sum(rough_token_count(i.text or "") < 25 for i in speech) / len(speech)
    pause_ratio = len(pauses) / max(1, len(speech))
    return "pause-heavy" if len(pauses) >= 2 and short_ratio >= 0.5 and pause_ratio >= 0.35 else "prose"


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in SENTENCE_RE.split(text.strip()) if p.strip()]


def pack_prose_text(text: str, target_tokens: int, max_tokens: int, count_fn=rough_token_count) -> list[str]:
    sentences = split_sentences(text)
    chunks, current = [], []
    for sentence in sentences:
        candidate = " ".join(current + [sentence])
        if current and count_fn(candidate) > max_tokens:
            chunks.append(" ".join(current)); current = [sentence]
        else:
            current.append(sentence)
        if count_fn(" ".join(current)) >= target_tokens:
            chunks.append(" ".join(current)); current = []
    if current: chunks.append(" ".join(current))
    return [c.strip() for c in chunks if c.strip()]


def optimize_prose_items(items: list[ScriptItem], target_tokens: int, max_tokens: int, count_fn=rough_token_count) -> list[ScriptItem]:
    out: list[ScriptItem] = []
    run: list[str] = []
    def flush():
        if not run: return
        combined = " ".join(run); run.clear()
        out.extend(ScriptItem("speech", text=c) for c in pack_prose_text(combined, target_tokens, max_tokens, count_fn=count_fn))
    for item in items:
        if item.kind == "speech" and item.text: run.append(item.text)
        else: flush(); out.append(item)
    flush(); return out



def _split_long_unit_for_chatterbox(
    text: str,
    count_fn,
    max_tokens: int,
    max_chars: int,
) -> list[str]:
    """
    Split a sentence that is itself too large. Prefer clause punctuation;
    fall back to word packing only when necessary.
    """
    text = text.strip()
    if not text:
        return []
    if count_fn(text) <= max_tokens and len(text) <= max_chars:
        return [text]

    clauses = [
        part.strip()
        for part in re.split(r"(?<=[,;])\s+", text)
        if part.strip()
    ]

    # If punctuation did not create useful clauses, fall back to words.
    if len(clauses) <= 1:
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        for word in words:
            candidate = " ".join(current + [word]).strip()
            if current and (count_fn(candidate) > max_tokens or len(candidate) > max_chars):
                chunks.append(" ".join(current).strip())
                current = [word]
            else:
                current.append(word)
        if current:
            chunks.append(" ".join(current).strip())
        return chunks

    chunks: list[str] = []
    current: list[str] = []
    for clause in clauses:
        candidate = " ".join(current + [clause]).strip()
        if current and (count_fn(candidate) > max_tokens or len(candidate) > max_chars):
            chunks.append(" ".join(current).strip())
            current = [clause]
        else:
            current.append(clause)

    if current:
        chunks.append(" ".join(current).strip())

    # Recursively handle any unusually large remaining clause.
    final: list[str] = []
    for chunk in chunks:
        if count_fn(chunk) > max_tokens or len(chunk) > max_chars:
            final.extend(_split_long_unit_for_chatterbox(chunk, count_fn, max_tokens, max_chars))
        else:
            final.append(chunk)
    return final


def pack_chatterbox_text(
    text: str,
    count_fn,
    target_tokens: int = 45,
    max_tokens: int = 65,
    max_chars: int = 300,
) -> list[str]:
    """
    Sentence-aligned long-form chunking for Chatterbox Turbo/Nano.

    The tokenizer's technical limit is much larger, but long single calls can
    hallucinate/repeat/cut off. We therefore target short, self-contained
    chunks and use both tokenizer tokens and a character ceiling.
    """
    units: list[str] = []
    for sentence in split_sentences(text):
        units.extend(
            _split_long_unit_for_chatterbox(
                sentence,
                count_fn=count_fn,
                max_tokens=max_tokens,
                max_chars=max_chars,
            )
        )

    chunks: list[str] = []
    current: list[str] = []

    for unit in units:
        candidate = " ".join(current + [unit]).strip()
        candidate_tokens = count_fn(candidate)

        if current and (candidate_tokens > max_tokens or len(candidate) > max_chars):
            chunks.append(" ".join(current).strip())
            current = [unit]
        else:
            current.append(unit)

        current_text = " ".join(current).strip()
        if current_text and count_fn(current_text) >= target_tokens:
            chunks.append(current_text)
            current = []

    if current:
        chunks.append(" ".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def optimize_chatterbox_items(
    items: list[ScriptItem],
    backend: "ChatterboxBackend",
) -> list[ScriptItem]:
    """
    Re-chunk all Chatterbox speech between explicit [pause Ns] boundaries.

    Exact user pauses are never removed or crossed.
    """
    cfg = backend.chunking
    if not bool(cfg.get("enabled", True)):
        return items

    target_tokens = int(cfg.get("target_tokens", 45))
    max_tokens = int(cfg.get("max_tokens", 65))
    max_chars = int(cfg.get("max_chars", 300))

    out: list[ScriptItem] = []
    run: list[str] = []

    def flush_run() -> None:
        if not run:
            return
        combined = " ".join(run).strip()
        run.clear()
        for chunk in pack_chatterbox_text(
            combined,
            count_fn=backend.text_token_count,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            max_chars=max_chars,
        ):
            out.append(ScriptItem("speech", text=chunk))

    for item in items:
        if item.kind == "speech" and item.text:
            run.append(item.text)
        else:
            flush_run()
            out.append(item)

    flush_run()
    return out


def collect_neighbor_speech(items: list[ScriptItem], idx: int, limit: int = 8) -> tuple[list[str], list[str]]:
    before, after = [], []
    i = idx - 1
    while i >= 0 and len(before) < limit:
        if items[i].kind == "speech" and items[i].text: before.insert(0, items[i].text)
        i -= 1
    i = idx + 1
    while i < len(items) and len(after) < limit:
        if items[i].kind == "speech" and items[i].text: after.append(items[i].text)
        i += 1
    return before, after


def silence(seconds: float, sr: int) -> np.ndarray:
    return np.zeros(int(round(seconds * sr)), dtype=np.float32)


def ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg not found. Install it with: sudo apt update && sudo apt install -y ffmpeg")
    return ffmpeg


def build_atempo_filter(speed: float) -> str:
    if speed <= 0: raise ValueError("Speed must be > 0")
    factors, remaining = [], speed
    while remaining < 0.5: factors.append(0.5); remaining /= 0.5
    while remaining > 2.0: factors.append(2.0); remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={f:.8f}" for f in factors)


def ffmpeg_time_stretch(audio: np.ndarray, sr: int, speed: float) -> np.ndarray:
    if abs(speed - 1.0) < 1e-6: return audio
    with tempfile.TemporaryDirectory(prefix="meditation-atempo-") as tmp:
        inp, out = Path(tmp)/"in.wav", Path(tmp)/"out.wav"
        sf.write(inp, audio, sr, subtype="PCM_16")
        subprocess.run([ensure_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(inp), "-af", build_atempo_filter(speed), "-ar", str(sr), "-ac", "1", str(out)], check=True)
        stretched, out_sr = sf.read(out, dtype="float32")
        if out_sr != sr: raise RuntimeError("Unexpected FFmpeg sample rate")
        return to_mono_float(stretched)


def normalize_wav(inp: Path, out: Path, sr: int, cfg: dict[str, Any]) -> None:
    filt = f"loudnorm=I={float(cfg.get('target_lufs', -19.0))}:TP={float(cfg.get('true_peak_db', -1.5))}:LRA={float(cfg.get('lra', 11.0))}"
    subprocess.run([ensure_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(inp), "-af", filt, "-ar", str(sr), "-ac", "1", str(out)], check=True)


def render(script_path: Path, config_path: Path, preset_name: Optional[str], backend_override: Optional[str], voice_override: Optional[str], speed_override: Optional[float], reference_audio_override: Optional[Path], script_profile_override: Optional[str], normalize_override: Optional[bool], output_override: Optional[Path]) -> Path:
    config = load_config(config_path)
    preset = resolve_preset(config, preset_name)
    backend_name = str(backend_override or preset.get("backend", "kokoro"))
    voice = voice_override if voice_override is not None else preset.get("voice")
    speed = float(speed_override if speed_override is not None else preset.get("speed", 1.0))
    backend_settings = dict((config.get("backends", {}) or {}).get(backend_name, {}) or {})
    if reference_audio_override is not None: backend_settings["reference_audio"] = str(reference_audio_override)
    elif preset.get("reference_audio") is not None: backend_settings["reference_audio"] = preset.get("reference_audio")
    backend = build_backend(backend_name, backend_settings)

    raw_items = parse_script(script_path)
    profile = script_profile_override or preset.get("script_profile") or config.get("defaults", {}).get("script_profile", "auto")
    if profile == "auto": profile = detect_script_profile(raw_items)
    if profile not in {"prose", "pause-heavy"}: raise ValueError("script profile must be auto, prose, or pause-heavy")
    if profile == "prose" and backend_name == "kokoro":
        pcfg = config.get("script_profiles", {}).get("prose", {}) or {}
        items = optimize_prose_items(
            raw_items,
            int(pcfg.get("target_tokens", 150)),
            int(pcfg.get("max_tokens", 200)),
            count_fn=lambda text: backend._token_count(text, voice),
        )
    else:
        items = raw_items

    # Chatterbox has a different long-form sweet spot from Kokoro. Apply
    # Chatterbox-specific tokenizer-aware chunking regardless of script profile,
    # while preserving every explicit [pause Ns] boundary.
    if backend_name in {"chatterbox-nano", "chatterbox-turbo"}:
        items = optimize_chatterbox_items(items, backend)

    paths = config.get("paths", {}) or {}
    segments_root, manifests_root, output_root = Path(paths.get("segments", "segments")), Path(paths.get("manifests", "manifests")), Path(paths.get("output", "output"))
    effective_reference = backend_settings.get("reference_audio")
    if backend_name in {"chatterbox-nano", "chatterbox-turbo"} and effective_reference:
        output_voice_label = reference_voice_label(effective_reference)
    else:
        output_voice_label = str(voice) if voice else None

    run_slug = (
        f"{safe_name(script_path.stem)}-"
        f"{safe_name(preset['preset_name'])}-"
        f"{safe_name(backend_name)}"
        + (f"-{safe_name(output_voice_label)}" if output_voice_label else "")
    )
    segments_dir = segments_root / run_slug
    for p in (segments_dir, manifests_root, output_root): p.mkdir(parents=True, exist_ok=True)
    output_path = output_override or output_root / f"{run_slug}.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context_cfg = config.get("script_profiles", {}).get("pause-heavy", {}).get("kokoro_context", {}) or {}

    rendered: list[RenderedItem] = []
    parts: list[np.ndarray] = []
    sr: Optional[int] = None
    print(f"Script:         {script_path}")
    print(f"Preset:         {preset['preset_name']}")
    print(f"Backend:        {backend_name}")
    print(f"Voice:          {voice or '(backend default)'}")
    if effective_reference:
        print(f"Reference:      {effective_reference}")
        print(f"Reference label:{' ' if output_voice_label else ''}{output_voice_label or '(none)'}")
    if backend_name in {"chatterbox-nano", "chatterbox-turbo"}:
        print(
            "CB chunking:    "
            f"target={backend.chunking.get('target_tokens', 45)} tokens, "
            f"max={backend.chunking.get('max_tokens', 65)} tokens, "
            f"max_chars={backend.chunking.get('max_chars', 300)}"
        )
    print(f"Speed:          {speed}")
    print(f"Script profile: {profile}\n")

    for index, item in enumerate(items, 1):
        if item.kind == "silence":
            pause_sr = sr or 24000
            audio = silence(float(item.seconds or 0), pause_sr)
            seg = segments_dir / f"{index:03d}_pause_{item.seconds:g}s.wav"
            sf.write(seg, audio, pause_sr, subtype="PCM_16")
            parts.append(audio)
            rendered.append(RenderedItem(index, "silence", str(seg), len(audio)/pause_sr, requested_pause_seconds=float(item.seconds or 0)))
            print(f"[{index:03}] Pause: {item.seconds:g}s")
            continue

        if not item.text: continue
        print(f"[{index:03}] Speech: {item.text}")
        if profile == "pause-heavy" and backend_name == "kokoro":
            before, after = collect_neighbor_speech(items, index-1)
            result = backend.synthesize_contextual(item.text, before, after, voice, speed, context_cfg)
        else:
            result = backend.synthesize(item.text, voice, speed)
        audio = result.audio
        if sr is None: sr = result.sample_rate
        if result.sample_rate != sr: raise RuntimeError(f"Sample-rate changed: {sr} -> {result.sample_rate}")
        if not backend.supports_native_speed and abs(speed - 1.0) > 1e-6:
            audio = ffmpeg_time_stretch(audio, sr, speed)
            result.metadata["post_time_stretch"] = speed
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1.0:
            audio = audio / peak * 0.999
            result.metadata["peak_safety_normalized"] = True
        seg = segments_dir / f"{index:03d}_speech.wav"
        sf.write(seg, audio, sr, subtype="PCM_16")
        parts.append(audio)
        rendered.append(RenderedItem(index, "speech", str(seg), len(audio)/sr, text=item.text, metadata=result.metadata))

    sr = sr or 24000
    if not parts: raise RuntimeError("Nothing rendered")
    final_audio = np.concatenate(parts).astype(np.float32, copy=False)
    raw_out = output_path.with_name(output_path.stem + ".raw.wav")
    sf.write(raw_out, final_audio, sr, subtype="PCM_16")

    norm_name = preset.get("normalization", config.get("defaults", {}).get("normalization", "voiceover"))
    norm_cfg = (config.get("normalization", {}) or {}).get(norm_name, {}) or {}
    norm_enabled = bool(norm_cfg.get("enabled", True)) if normalize_override is None else normalize_override
    if norm_enabled:
        print(f"\nNormalizing: {norm_name} ({norm_cfg.get('target_lufs', -19)} LUFS)")
        normalize_wav(raw_out, output_path, sr, norm_cfg)
        if not bool(config.get("defaults", {}).get("keep_raw_master", False)): raw_out.unlink(missing_ok=True)
    else:
        raw_out.replace(output_path)

    manifest = manifests_root / f"{run_slug}.json"
    manifest.write_text(json.dumps({"version": 2, "script": str(script_path), "config": str(config_path), "preset": preset["preset_name"], "backend": backend_name, "voice": voice, "output_voice_label": output_voice_label, "reference_audio": effective_reference, "speed": speed, "script_profile": profile, "sample_rate": sr, "normalization": {"name": norm_name, "enabled": norm_enabled, **norm_cfg}, "output": str(output_path), "duration_seconds_before_final_loudnorm": len(final_audio)/sr, "items": [asdict(x) for x in rendered]}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDone.\nOutput:   {output_path}\nManifest: {manifest}\nDuration before final loudnorm: {len(final_audio)/sr:.2f}s")
    return output_path


def main():
    p = argparse.ArgumentParser(description="Guided meditation TTS renderer v2")
    p.add_argument("script", type=Path)
    p.add_argument("--config", type=Path, default=Path("config/voice.yaml"))
    p.add_argument("--preset")
    p.add_argument("--backend", choices=["kokoro", "chatterbox-nano", "chatterbox-turbo"])
    p.add_argument("--voice")
    p.add_argument("--speed", type=float)
    p.add_argument("--reference-audio", type=Path)
    p.add_argument("--script-profile", choices=["auto", "prose", "pause-heavy"])
    p.add_argument("--output", type=Path)
    g = p.add_mutually_exclusive_group(); g.add_argument("--normalize", action="store_true", dest="normalize"); g.add_argument("--no-normalize", action="store_false", dest="normalize"); p.set_defaults(normalize=None)
    a = p.parse_args()
    if not a.script.exists(): raise SystemExit(f"Script not found: {a.script}")
    try:
        render(a.script, a.config, a.preset, a.backend, a.voice, a.speed, a.reference_audio, a.script_profile, a.normalize, a.output)
    except Exception as exc:
        raise SystemExit(f"Render failed: {exc}") from exc


if __name__ == "__main__":
    main()
