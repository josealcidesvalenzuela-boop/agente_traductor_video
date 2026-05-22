import asyncio
import os
import subprocess
from pathlib import Path

import edge_tts
import ffmpeg
import srt as srt_lib
from rich.progress import Progress, BarColumn, MofNCompleteColumn, TextColumn, TimeElapsedColumn

_VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ar": "ar-SA-ZariyahNeural",
}

_MAX_SPEED = 1.5  # cap to keep speech intelligible


def _audio_duration(path: str) -> float:
    probe = ffmpeg.probe(path)
    return float(probe["format"]["duration"])


def _adjust_speed(path: str, target_sec: float) -> None:
    """Speed up audio to fit within target_sec. No-op if already shorter or ratio > _MAX_SPEED."""
    actual = _audio_duration(path)
    if actual <= target_sec:
        return
    speed = min(actual / target_sec, _MAX_SPEED)
    # atempo range is [0.5, 2.0]; chain two filters for speed > 2.0
    if speed <= 2.0:
        af = f"atempo={speed:.4f}"
    else:
        s1 = speed**0.5
        af = f"atempo={s1:.4f},atempo={speed / s1:.4f}"
    tmp = path + ".tmp.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-filter:a", af, tmp],
        capture_output=True,
        check=True,
    )
    os.replace(tmp, path)


async def _synthesize(text: str, voice: str, path: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def generate_audio(
    srt_path: str,
    target_lang: str = "en",
    output_dir: str | None = None,
) -> list[tuple[float, str]]:
    """Generate one speed-adjusted MP3 per subtitle segment. Returns (start_sec, path) list."""
    path = Path(srt_path)
    subs = list(srt_lib.parse(path.read_text(encoding="utf-8")))
    voice = _VOICES.get(target_lang, "en-US-JennyNeural")

    out_dir = Path(output_dir) if output_dir else path.parent / f"{path.stem}_tts"
    out_dir.mkdir(parents=True, exist_ok=True)

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn()) as prog:
        task = prog.add_task(f"Sintetizando voz [{voice}]", total=len(subs))

        async def _run_all() -> None:
            async def _synth_one(sub) -> None:
                seg_path = str(out_dir / f"seg_{sub.index:04d}.mp3")
                await _synthesize(sub.content, voice, seg_path)
                target_sec = (sub.end - sub.start).total_seconds()
                _adjust_speed(seg_path, target_sec)
                prog.advance(task)

            await asyncio.gather(*[_synth_one(sub) for sub in subs])

        asyncio.run(_run_all())

    segments = [
        (sub.start.total_seconds(), str(out_dir / f"seg_{sub.index:04d}.mp3"))
        for sub in subs
    ]
    print(f"  → {out_dir.name}/ ({len(segments)} archivos)")
    return segments
