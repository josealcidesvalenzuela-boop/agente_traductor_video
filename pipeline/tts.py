import asyncio
from pathlib import Path

import edge_tts
import srt as srt_lib

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


async def _synthesize(text: str, voice: str, path: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def generate_audio(
    srt_path: str,
    target_lang: str = "en",
    output_dir: str | None = None,
) -> list[tuple[float, str]]:
    """Generate one MP3 per subtitle segment. Returns list of (start_seconds, audio_path)."""
    path = Path(srt_path)
    subs = list(srt_lib.parse(path.read_text(encoding="utf-8")))
    voice = _VOICES.get(target_lang, "en-US-JennyNeural")

    out_dir = Path(output_dir) if output_dir else path.parent / f"{path.stem}_tts"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[tts] {len(subs)} segmentos · voz={voice}")

    async def _run_all() -> None:
        tasks = [
            _synthesize(sub.content, voice, str(out_dir / f"seg_{sub.index:04d}.mp3"))
            for sub in subs
        ]
        await asyncio.gather(*tasks)

    asyncio.run(_run_all())

    segments = [
        (sub.start.total_seconds(), str(out_dir / f"seg_{sub.index:04d}.mp3"))
        for sub in subs
    ]
    print(f"[tts] → {out_dir} ({len(segments)} archivos)")
    return segments
