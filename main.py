import sys
import time
from datetime import datetime
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


def _make_run_outputs(video: Path, run_id: str) -> dict[str, Path]:
    p, s = video.parent, video.stem
    return {
        "srt":            p / f"{s}_{run_id}.srt",
        "translated_srt": p / f"{s}_{run_id}_translated.srt",
        "tts_dir":        p / f"{s}_{run_id}_tts",
        "dubbed":         p / f"{s}_{run_id}_dubbed.mp4",
    }


def _find_latest_outputs(video: Path) -> dict[str, Path] | None:
    """Return output paths of the most recent run for this video, or None if no prior run exists."""
    dubbed_files = sorted(
        video.parent.glob(f"{video.stem}_*_dubbed.mp4"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not dubbed_files:
        return None
    # Extract run_id from "{stem}_{run_id}_dubbed.mp4"
    inner = dubbed_files[0].stem[len(video.stem) + 1:]   # "20260522_143500_dubbed"
    run_id = inner[: inner.rfind("_dubbed")]               # "20260522_143500"
    return _make_run_outputs(video, run_id) if run_id else None


@app.command("run")
def run(
    video: Path = typer.Argument(..., help="Archivo de video de entrada", exists=True),
    source: str = typer.Option("auto", "--source", "-s", help="Idioma origen (auto=detectar)"),
    target: str = typer.Option("en", "--target", "-t", help="Idioma destino (en, es, fr, de, it, pt, zh, ja, ko, ru, ar)"),
    only: Optional[str] = typer.Option(None, "--only", help="Ejecutar solo una etapa: transcribe | translate | tts | merge"),
    srt: Optional[Path] = typer.Option(None, "--srt", help="SRT existente para saltar la transcripción"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta del video de salida"),
    tone: str = typer.Option("neutral", "--tone", help="Tono de traducción: neutral | formal | informal"),
    domain: str = typer.Option("general", "--domain", help="Dominio del contenido: general | technical | casual"),
    engine: Optional[str] = typer.Option(None, "--engine", help="Motor TTS: edge (nube) | kokoro (local). Default: env TTS_ENGINE o 'edge'"),
    voice: Optional[str] = typer.Option(None, "--voice", help="Voz explícita para el motor seleccionado. Ver: main.py voices"),
    force: bool = typer.Option(False, "--force", "-f", help="Reejecutar etapas aunque los archivos ya existan"),
):
    """Transcribe → Traduce → Sintetiza voz → Dobla el video."""
    t_start = time.time()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    console.print(Panel(f"[bold cyan]agente_traductor_video[/]\n{video.name}  ·  {source} → {target}  ·  run [dim]{run_id}[/]"))

    from pipeline.transcribe import transcribe
    from pipeline.translate import translate
    from pipeline.tts import generate_audio
    from pipeline.merge import merge

    # On resume (no --force), reuse the most recent run's files
    resume = not force and _find_latest_outputs(video)
    out = resume or _make_run_outputs(video, run_id)
    srt_path: str | None = str(srt) if srt else None

    # Etapa 1 — Transcripción
    if only in (None, "transcribe") and srt_path is None:
        console.print("\n[bold yellow]▶ Etapa 1/4[/]  Transcripción (Faster-Whisper)…")
        if resume and out["srt"].exists():
            console.print(f"  [dim]↩ Reutilizando {out['srt'].name} (--force para reejecutar)[/]")
            srt_path = str(out["srt"])
        else:
            srt_path = transcribe(str(video), language=None if source == "auto" else source, output_path=str(out["srt"]))
        if only == "transcribe":
            console.print(f"[green]✓[/] {srt_path}")
            return

    # Etapa 2 — Traducción
    translated_srt: str | None = None
    if only in (None, "translate"):
        console.print("\n[bold yellow]▶ Etapa 2/4[/]  Traducción (Ollama)…")
        if resume and out["translated_srt"].exists():
            console.print(f"  [dim]↩ Reutilizando {out['translated_srt'].name} (--force para reejecutar)[/]")
            translated_srt = str(out["translated_srt"])
        else:
            translated_srt = translate(
                srt_path, source_lang=source, target_lang=target,
                tone=tone, domain=domain, output_path=str(out["translated_srt"]),
            )
        if only == "translate":
            console.print(f"[green]✓[/] {translated_srt}")
            return

    srt_for_tts = translated_srt or srt_path

    # Etapa 3 — Síntesis de voz
    audio_segments: list[tuple[float, str]] | None = None
    if only in (None, "tts"):
        console.print("\n[bold yellow]▶ Etapa 3/4[/]  Síntesis de voz (Edge-TTS)…")
        tts_dir = out["tts_dir"]
        cached_segs = list(tts_dir.glob("seg_*.mp3")) + list(tts_dir.glob("seg_*.wav")) if tts_dir.exists() else []
        if resume and cached_segs:
            console.print(f"  [dim]↩ Reutilizando {tts_dir.name}/ (--force para reejecutar)[/]")
            import srt as srt_lib
            subs = list(srt_lib.parse(Path(srt_for_tts).read_text(encoding="utf-8")))
            ext = "wav" if cached_segs[0].suffix == ".wav" else "mp3"
            audio_segments = [
                (sub.start.total_seconds(), str(tts_dir / f"seg_{sub.index:04d}.{ext}"))
                for sub in subs
            ]
        else:
            audio_segments = generate_audio(srt_for_tts, target_lang=target, voice=voice, engine=engine, output_dir=str(tts_dir))
        if only == "tts":
            console.print(f"[green]✓[/] {len(audio_segments)} segmentos generados")
            return

    # Etapa 4 — Unión audio+video
    if only in (None, "merge"):
        console.print("\n[bold yellow]▶ Etapa 4/4[/]  Unión audio+video (FFmpeg)…")
        dubbed_path = str(output) if output else str(out["dubbed"])
        final = merge(str(video), audio_segments, output_path=dubbed_path)
        elapsed = time.time() - t_start
        console.print(Panel(f"[bold green]✓ Completado en {elapsed:.1f}s[/]\n{final}"))


@app.command()
def voices(
    lang: Optional[str] = typer.Argument(None, help="Filtrar por idioma (ej: es, en-US, fr)"),
    engine: str = typer.Option("edge", "--engine", help="Motor: edge | kokoro"),
):
    """Lista las voces disponibles del motor TTS seleccionado."""
    import asyncio
    from rich.table import Table

    if engine == "kokoro":
        from pipeline.tts import _KokoroEngine

        eng = _KokoroEngine()
        model = eng._get_model()
        names = model.get_voices()
        if lang:
            names = [n for n in names if n.startswith(lang.replace("-", "_").lower())]
        table = Table("Nombre", "Prefijo de idioma", title=f"Voces Kokoro{f' [{lang}]' if lang else ''}")
        for n in names:
            prefix = n.split("_")[0]
            table.add_row(n, prefix)
        console.print(table)
        console.print(f"\n[dim]Uso: --engine kokoro --voice NombreDeVoz[/]  ej: [bold]--engine kokoro --voice {names[0] if names else 'af_bella'}[/]")
    else:
        from pipeline.tts import list_voices
        result = asyncio.run(list_voices(lang))
        table = Table("Nombre", "Género", "Locale", title=f"Voces Edge-TTS{f' [{lang}]' if lang else ''}")
        for v in sorted(result, key=lambda x: x["Locale"]):
            gender = "[cyan]♂[/]" if v["Gender"] == "Male" else "[magenta]♀[/]"
            table.add_row(v["ShortName"], gender, v["Locale"])
        console.print(table)
        console.print(f"\n[dim]Uso: --voice NombreDeVoz[/]  ej: [bold]--voice {result[0]['ShortName'] if result else 'es-ES-AlvaroNeural'}[/]")


if __name__ == "__main__":
    app()
