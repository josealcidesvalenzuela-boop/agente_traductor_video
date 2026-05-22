import sys
import time
from dataclasses import dataclass
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


# ── Run path management ───────────────────────────────────────────────────────

_OUTPUT_DIR = Path("salida")


@dataclass
class RunPaths:
    run_dir: Path
    srt: Path
    translated_srt: Path
    tts_dir: Path
    dubbed: Path


def _make_run_paths(video: Path, run_id: str) -> RunPaths:
    run_dir = _OUTPUT_DIR / f"{video.stem}_{run_id}"
    return RunPaths(
        run_dir=run_dir,
        srt=run_dir / "transcription.srt",
        translated_srt=run_dir / "translated.srt",
        tts_dir=run_dir / "tts",
        dubbed=run_dir / "dubbed.mp4",
    )


def _find_latest_run(video: Path) -> RunPaths | None:
    """Return paths of the most recent run for this video, or None."""
    if not _OUTPUT_DIR.exists():
        return None
    candidates = sorted(
        [d for d in _OUTPUT_DIR.glob(f"{video.stem}_*") if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    run_id = candidates[0].name[len(video.stem) + 1:]
    return _make_run_paths(video, run_id)


# ── Commands ──────────────────────────────────────────────────────────────────


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
    voice: Optional[str] = typer.Option(None, "--voice", help="Voz explícita para el motor TTS. Ver: main.py voices"),
    force: bool = typer.Option(False, "--force", "-f", help="Reejecutar etapas aunque los archivos ya existan"),
):
    """Transcribe → Traduce → Sintetiza voz → Dobla el video."""
    t_start = time.time()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    from pipeline.transcribe import transcribe
    from pipeline.translate import translate
    from pipeline.tts import generate_audio
    from pipeline.merge import merge

    resume = not force and _find_latest_run(video)
    out = resume or _make_run_paths(video, run_id)
    out.run_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold cyan]agente_traductor_video[/]\n"
        f"{video.name}  ·  {source} → {target}  ·  run [dim]{run_id}[/]\n"
        f"[dim]salida → {out.run_dir}[/]"
    ))
    srt_path: str | None = str(srt) if srt else None

    # Etapa 1 — Transcripción
    if only in (None, "transcribe") and srt_path is None:
        console.print("\n[bold yellow]▶ Etapa 1/4[/]  Transcripción (Faster-Whisper)…")
        if resume and out.srt.exists():
            console.print(f"  [dim]↩ Reutilizando {out.srt.name} (--force para reejecutar)[/]")
            srt_path = str(out.srt)
        else:
            srt_path = transcribe(str(video), language=None if source == "auto" else source, output_path=str(out.srt))
        if only == "transcribe":
            console.print(f"[green]✓[/] {srt_path}")
            return

    # Etapa 2 — Traducción
    translated_srt: str | None = None
    if only in (None, "translate"):
        console.print("\n[bold yellow]▶ Etapa 2/4[/]  Traducción (Ollama)…")
        if resume and out.translated_srt.exists():
            console.print(f"  [dim]↩ Reutilizando {out.translated_srt.name} (--force para reejecutar)[/]")
            translated_srt = str(out.translated_srt)
        else:
            translated_srt = translate(
                srt_path, source_lang=source, target_lang=target,
                tone=tone, domain=domain, output_path=str(out.translated_srt),
            )
        if only == "translate":
            console.print(f"[green]✓[/] {translated_srt}")
            return

    srt_for_tts = translated_srt or srt_path

    # Etapa 3 — Síntesis de voz
    audio_segments: list[tuple[float, str]] | None = None
    if only in (None, "tts"):
        console.print("\n[bold yellow]▶ Etapa 3/4[/]  Síntesis de voz…")
        tts_dir = out.tts_dir
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
        dubbed_path = str(output) if output else str(out.dubbed)
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

        model = _KokoroEngine._get_model()
        names = model.get_voices()
        if lang:
            names = [n for n in names if n.startswith(lang.replace("-", "_").lower())]
        table = Table("Nombre", "Prefijo de idioma", title=f"Voces Kokoro{f' [{lang}]' if lang else ''}")
        for n in names:
            table.add_row(n, n.split("_")[0])
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
