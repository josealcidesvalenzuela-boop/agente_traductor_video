import os
import time
from datetime import timedelta
from pathlib import Path

import srt
from faster_whisper import WhisperModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

_console = Console()


def transcribe(video_path: str, language: str | None = None) -> str:
    """Transcribe video/audio to SRT using Faster-Whisper. Returns SRT path."""
    model_name = os.getenv("WHISPER_MODEL", "large-v3")
    t0 = time.time()

    force_cpu = os.getenv("WHISPER_DEVICE", "").lower() == "cpu"
    device, compute_type = ("cpu", "int8") if force_cpu else ("cuda", "float16")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(), console=_console) as prog:
        t_load = prog.add_task(f"Cargando {model_name} [{device}]…", total=None)
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
        except (RuntimeError, OSError):
            if device == "cuda":
                prog.update(t_load, description="CUDA no disponible, cargando en CPU…")
                device, compute_type = "cpu", "int8"
                model = WhisperModel(model_name, device=device, compute_type=compute_type)
            else:
                raise
        prog.update(t_load, description=f"[green]Modelo listo [{device}]")

        lang = None if language in (None, "auto") else language
        segments_iter, info = model.transcribe(video_path, language=lang, beam_size=5)

        t_seg = prog.add_task("Transcribiendo…  0 segmentos", total=None)
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
            prog.update(t_seg, description=f"Transcribiendo…  {len(subs)} segmentos")
        prog.update(t_seg, description=f"[green]{len(subs)} segmentos detectados (idioma={info.language})")

    output_path = Path(video_path).with_suffix(".srt")
    output_path.write_text(srt.compose(subs), encoding="utf-8")
    elapsed = time.time() - t0
    _console.print(f"  → [bold]{output_path.name}[/] ({elapsed:.1f}s)")
    return str(output_path)
