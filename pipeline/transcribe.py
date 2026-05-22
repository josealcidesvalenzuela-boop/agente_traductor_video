import os
import time
from datetime import timedelta
from pathlib import Path

import srt
from faster_whisper import WhisperModel


def transcribe(video_path: str, language: str | None = None) -> str:
    """Transcribe video/audio to SRT using Faster-Whisper. Returns SRT path."""
    model_name = os.getenv("WHISPER_MODEL", "large-v3")
    t0 = time.time()

    force_cpu = os.getenv("WHISPER_DEVICE", "").lower() == "cpu"
    device, compute_type = ("cpu", "int8") if force_cpu else ("cuda", "float16")

    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except (RuntimeError, OSError):
        if device == "cuda":
            print("[transcribe] CUDA no disponible, usando CPU")
            device, compute_type = "cpu", "int8"
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
        else:
            raise

    print(f"[transcribe] model={model_name} device={device}")

    lang = None if language in (None, "auto") else language
    segments_iter, info = model.transcribe(video_path, language=lang, beam_size=5)

    subs = []
    for seg in segments_iter:
        subs.append(
            srt.Subtitle(
                index=len(subs) + 1,
                start=timedelta(seconds=seg.start),
                end=timedelta(seconds=seg.end),
                content=seg.text.strip(),
            )
        )

    output_path = Path(video_path).with_suffix(".srt")
    output_path.write_text(srt.compose(subs), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"[transcribe] {len(subs)} subtítulos detectados (idioma={info.language}) → {output_path} ({elapsed:.1f}s)")
    return str(output_path)
