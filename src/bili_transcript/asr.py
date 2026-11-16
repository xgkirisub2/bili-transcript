"""Local speech-to-text.

Backends:
- faster-whisper (CUDA when available, otherwise CPU).
- mlx-whisper (Apple Silicon Metal) when running on an Apple Silicon Mac.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

MLX_MODEL_MAP: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
}


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


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64")


def _mlx_available() -> bool:
    if not _is_apple_silicon():
        return False
    try:
        import mlx.core as mx
        import mlx_whisper  # noqa: F401

        return mx.metal.is_available()
    except Exception:
        return False


def _resolve_backend(device: str) -> tuple[str, str, str]:
    """Return (backend, resolved_device, compute_type)."""
    if device == "metal":
        if not _mlx_available():
            raise RuntimeError("Metal 不可用：需要 Apple Silicon 和 bili-transcript[apple]。")
        return "mlx", "metal", "float16"
    if device == "cuda":
        _prepare_cuda_dlls()
        return "faster_whisper", "cuda", "float16"
    if device == "cpu":
        return "faster_whisper", "cpu", "int8"
    if device != "auto":
        raise ValueError(f"不支持的转写设备：{device}")

    # device == "auto"
    if _is_apple_silicon() and _mlx_available():
        return "mlx", "metal", "float16"

    _prepare_cuda_dlls()
    import ctranslate2

    if ctranslate2.get_cuda_device_count() > 0:
        return "faster_whisper", "cuda", "float16"
    return "faster_whisper", "cpu", "int8"


def _transcribe_faster_whisper(
    audio_path: Path,
    model_size: str,
    resolved_device: str,
    compute_type: str,
    language: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
        "backend": "faster-whisper",
        "elapsed_seconds": round(elapsed, 1),
    }


def _transcribe_mlx(
    audio_path: Path,
    model_size: str,
    language: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repo = MLX_MODEL_MAP.get(model_size)
    if repo is None and "/" in model_size:
        repo = model_size
    if repo is None:
        raise ValueError(f"mlx-whisper 不支持模型：{model_size}")

    from contextlib import redirect_stdout

    import mlx.core as mx
    from mlx_whisper import transcribe as mlx_transcribe

    print(
        f"转写中：model={model_size}, device=metal (Apple Silicon MLX), repo={repo}",
        file=sys.stderr,
        flush=True,
    )
    print("首次使用会下载 MLX 模型（约 1.6 GB）。", file=sys.stderr, flush=True)
    started = time.time()

    kwargs: dict[str, Any] = {}
    if language != "auto":
        kwargs["language"] = language
    # Keep progress (and automatic language detection) off CLI JSON stdout.
    with mx.stream(mx.gpu), redirect_stdout(sys.stderr):
        result = mlx_transcribe(
            str(audio_path),
            path_or_hf_repo=repo,
            condition_on_previous_text=False,
            verbose=False,
            **kwargs,
        )

    segments: list[dict[str, Any]] = []
    for seg in result.get("segments", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(float(seg.get("start", 0.0)), 3),
                "end": round(float(seg.get("end", 0.0)), 3),
                "text": text,
            }
        )

    elapsed = time.time() - started
    print(
        f"转写完成：{len(segments)} 段，耗时 {elapsed:.1f} 秒",
        file=sys.stderr,
        flush=True,
    )
    return segments, {
        "language": result.get("language") or language,
        "language_probability": None,
        "duration": None,
        "device": "metal",
        "compute_type": "float16",
        "model": model_size,
        "backend": "mlx-whisper",
        "elapsed_seconds": round(elapsed, 1),
    }


def transcribe(
    audio_path: Path,
    model_size: str = "large-v3-turbo",
    device: str = "auto",
    language: str = "zh",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Transcribe an audio file and return (segments, info)."""
    _configure_hf_mirror()
    backend, resolved_device, compute_type = _resolve_backend(device)
    if backend == "mlx":
        return _transcribe_mlx(audio_path, model_size, language)
    return _transcribe_faster_whisper(
        audio_path, model_size, resolved_device, compute_type, language
    )