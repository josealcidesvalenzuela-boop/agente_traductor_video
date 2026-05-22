import sys
import time
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(no_args_is_help=True, help="Pipeline de transcripción, traducción y doblaje de video.")
console = Console()


@app.command()
def run(
    video: Path = typer.Argument(..., help="Archivo de video de entrada", exists=True),
    source: str = typer.Option("auto", "--source", "-s", help="Idioma origen (auto=detectar automáticamente)"),
    target: str = typer.Option("en", "--target", "-t", help="Idioma destino (en, es, fr, de, it, pt, zh, ja, ko, ru, ar)"),
    only: Optional[str] = typer.Option(
        None,
        "--only",
        help="Ejecutar solo una etapa: transcribe | translate | tts | merge",
    ),
    srt: Optional[Path] = typer.Option(None, "--srt", help="SRT existente para saltar la transcripción"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta del video de salida"),
):
    """Transcribe → Traduce → Sintetiza voz → Dobla el video."""
    t_start = time.time()
    console.print(Panel(f"[bold cyan]agente_traductor_video[/]\n{video.name}  ·  {source} → {target}"))

    from pipeline.transcribe import transcribe
    from pipeline.translate import translate
    from pipeline.tts import generate_audio
    from pipeline.merge import merge

    srt_path: str | None = str(srt) if srt else None

    # Etapa 1 — Transcripción
    if only in (None, "transcribe") and srt_path is None:
        console.print("\n[bold yellow]▶ Etapa 1/4[/]  Transcripción (Faster-Whisper)…")
        srt_path = transcribe(str(video), language=None if source == "auto" else source)
        if only == "transcribe":
            console.print(f"[green]✓[/] {srt_path}")
            return

    # Etapa 2 — Traducción
    translated_srt: str | None = None
    if only in (None, "translate"):
        console.print("\n[bold yellow]▶ Etapa 2/4[/]  Traducción (Ollama)…")
        translated_srt = translate(srt_path, source_lang=source, target_lang=target)
        if only == "translate":
            console.print(f"[green]✓[/] {translated_srt}")
            return

    srt_for_tts = translated_srt or srt_path

    # Etapa 3 — Síntesis de voz
    audio_segments: list[tuple[float, str]] | None = None
    if only in (None, "tts"):
        console.print("\n[bold yellow]▶ Etapa 3/4[/]  Síntesis de voz (Edge-TTS)…")
        audio_segments = generate_audio(srt_for_tts, target_lang=target)
        if only == "tts":
            console.print(f"[green]✓[/] {len(audio_segments)} segmentos generados")
            return

    # Etapa 4 — Unión audio+video
    if only in (None, "merge"):
        console.print("\n[bold yellow]▶ Etapa 4/4[/]  Unión audio+video (FFmpeg)…")
        final = merge(str(video), audio_segments, output_path=str(output) if output else None)
        elapsed = time.time() - t_start
        console.print(Panel(f"[bold green]✓ Completado en {elapsed:.1f}s[/]\n{final}"))


if __name__ == "__main__":
    app()
