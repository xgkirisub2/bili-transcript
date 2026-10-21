"""Local speech-to-text with faster-whisper (CUDA when available)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any


def _prepare_cuda_dlls() -> None:
    """Make pip-installed cuBLAS/cuDNN DLLs discoverable on Windows."""
    if os.name != "nt":
        return
    try:
        import glob
        import site
    except Exception:
        return

    candidates: list[str] = []
    for site_dir in site.getsitepackages():
        candidates.extend(glob.glob(os.path.join(site_dir, "nvidia", "*", "bin")))
    for path in candidates:
        try:
            os.add_dll_directory(path)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


def _configure_hf_mirror() -> None:
    """Optionally use a mainland-friendly HuggingFace mirror.

    By default the official HuggingFace endpoint is used. Mainland China users
    can set ``BILI_HF_MIRROR=1`` to opt into hf-mirror.com, or set
    ``HF_ENDPOINT`` explicitly.
    """
    if os.environ.get("BILI_HF_MIRROR") == "1":
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def _resolve_device(device: str) -> tuple[str, str]:
    _prepare_cuda_dlls()
    import ctranslate2

    if device == "auto":
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    if device == "cuda":
        return "cuda", "float16"
    return "cpu", "int8"


def transcribe(
    audio_path: Path,
    model_size: str = "large-v3-turbo",
    device: str = "auto",
    language: str = "zh",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Transcribe an audio file and return (segments, info)."""
    _configure_hf_mirror()
    resolved_device, compute_type = _resolve_device(device)

    print(
        f"转写中：model={model_size}, device={resolved_device}, compute_type={compute_type}",
        file=sys.stderr,
        flush=True,
    )
    if resolved_device == "cuda":
        print("首次使用会下载模型（large-v3-turbo 约 1.6 GB）。", file=sys.stderr, flush=True)

    from faster_whisper import WhisperModel

    started = time.time()
    model = WhisperModel(model_size, device=resolved_device, compute_type=compute_type)

    def run(vad_filter: bool) -> tuple[list[dict[str, Any]], Any]:
        segments_iter, run_info = model.transcribe(
            str(audio_path),
            language=None if language == "auto" else language,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 500} if vad_filter else None,
            condition_on_previous_text=False,
        )
        collected: list[dict[str, Any]] = []
        for segment in segments_iter:
            text = segment.text.strip()
            if not text:
                continue
            collected.append(
                {
                    "start": round(float(segment.start), 3),
                    "end": round(float(segment.end), 3),
                    "text": text,
                }
            )
            if len(collected) % 20 == 0:
                print(
                    f"  已转写 {len(collected)} 段（{segment.end / 60:.1f} 分钟）",
                    file=sys.stderr,
                    flush=True,
                )
        return collected, run_info

    segments, info = run(True)
    if not segments:
        print("VAD 过滤后没有语音，关闭 VAD 重试一次（可能是歌曲或安静人声）。", file=sys.stderr, flush=True)
        segments, info = run(False)

    elapsed = time.time() - started
    print(
        f"转写完成：{len(segments)} 段，耗时 {elapsed:.1f} 秒",
        file=sys.stderr,
        flush=True,
    )
    return segments, {
        "language": getattr(info, "language", language),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "device": resolved_device,
        "compute_type": compute_type,
        "model": model_size,
        "elapsed_seconds": round(elapsed, 1),
    }
