import asyncio
import os
import subprocess
from pathlib import Path

import edge_tts
import ffmpeg
import srt as srt_lib
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from config import TTS_ENGINE

__all__ = ["generate_audio", "list_voices"]

_console = Console()

# ── Voice tables ──────────────────────────────────────────────────────────────

_EDGE_VOICES: dict[str, str] = {
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

_KOKORO_VOICES: dict[str, str] = {
    "en": "af_bella",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "it": "if_sara",
    "pt": "pf_dora",
    "ja": "jf_alpha",
    "zh": "zf_xiaobei",
}

# Kokoro uses its own language code scheme (differs from ISO 639-1)
_KOKORO_LANG: dict[str, str] = {
    "en": "en-us",
    "es": "es",
    "fr": "fr-fr",
    "it": "it",
    "pt": "pt-br",
    "ja": "ja",
    "zh": "zh",
}

_MAX_SPEED = 1.5

# ── Audio helpers ─────────────────────────────────────────────────────────────


def _audio_duration(path: str) -> float:
    return float(ffmpeg.probe(path)["format"]["duration"])


def _adjust_speed(path: str, target_sec: float) -> None:
    """Speed up audio to fit within target_sec; no-op if already fits or ratio > _MAX_SPEED."""
    actual = _audio_duration(path)
    if actual <= target_sec:
        return
    speed = min(actual / target_sec, _MAX_SPEED)
    tmp = path + ".tmp" + Path(path).suffix
    subprocess.run(
        ["ffmpeg", "-y", "-i", path, "-filter:a", f"atempo={speed:.4f}", tmp],
        capture_output=True,
        check=True,
    )
    os.replace(tmp, path)


# ── TTS engines ───────────────────────────────────────────────────────────────


class _EdgeEngine:
    """Cloud TTS via Microsoft Edge — requires internet, outputs MP3."""

    ext = "mp3"

    def default_voice(self, lang: str) -> str:
        return _EDGE_VOICES.get(lang, "en-US-JennyNeural")

    async def synth(self, text: str, voice: str, path: str) -> None:
        await edge_tts.Communicate(text, voice).save(path)


class _KokoroEngine:
    """Local ONNX TTS via Kokoro — no internet after first download, outputs WAV."""

    ext = "wav"
    _instance = None
    _CACHE = Path.home() / ".cache" / "kokoro_onnx"
    _MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    _VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

    @classmethod
    def _download(cls, url: str, dest: Path) -> None:
        if dest.exists():
            return
        import urllib.request
        _console.print(f"[kokoro] Descargando {dest.name}…")
        tmp = Path(str(dest) + ".tmp")
        urllib.request.urlretrieve(url, str(tmp))
        tmp.rename(dest)

    @classmethod
    def _get_model(cls):
        if cls._instance is None:
            from kokoro_onnx import Kokoro
            cls._CACHE.mkdir(parents=True, exist_ok=True)
            model_path = cls._CACHE / "kokoro-v1.0.onnx"
            voices_path = cls._CACHE / "voices-v1.0.bin"
            cls._download(cls._MODEL_URL, model_path)
            cls._download(cls._VOICES_URL, voices_path)
            cls._instance = Kokoro(str(model_path), str(voices_path))
        return cls._instance

    def default_voice(self, lang: str) -> str:
        return _KOKORO_VOICES.get(lang, "af_bella")

    async def synth(self, text: str, voice: str, path: str, lang: str = "en-us") -> None:
        import soundfile as sf
        model = self._get_model()
        loop = asyncio.get_event_loop()
        samples, sr = await loop.run_in_executor(None, lambda: model.create(text, voice=voice, speed=1.0, lang=lang))
        await loop.run_in_executor(None, lambda: sf.write(path, samples, sr))


def _build_engine(name: str) -> _EdgeEngine | _KokoroEngine:
    if name.lower() == "kokoro":
        return _KokoroEngine()
    return _EdgeEngine()


# ── Public API ────────────────────────────────────────────────────────────────


async def list_voices(lang_filter: str | None = None) -> list[dict]:
    """Return Edge-TTS voices, optionally filtered by language prefix (e.g. 'es', 'en-US')."""
    voices = await edge_tts.list_voices()
    if lang_filter:
        voices = [v for v in voices if v["Locale"].lower().startswith(lang_filter.lower())]
    return voices


def generate_audio(
    srt_path: str,
    target_lang: str = "en",
    output_dir: str | None = None,
    voice: str | None = None,
    engine: str | None = None,
) -> list[tuple[float, str]]:
    """Generate one speed-adjusted audio clip per subtitle segment.

    Returns list of (start_sec, audio_path).
    """
    engine_name = engine or TTS_ENGINE
    eng = _build_engine(engine_name)
    selected_voice = voice or eng.default_voice(target_lang)
    kokoro_lang = _KOKORO_LANG.get(target_lang, "en-us")

    path = Path(srt_path)
    subs = list(srt_lib.parse(path.read_text(encoding="utf-8")))
    out_dir = Path(output_dir) if output_dir else path.parent / f"{path.stem}_tts"
    out_dir.mkdir(parents=True, exist_ok=True)

    _console.print(f"  engine={engine_name}  voz={selected_voice}")

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn()) as prog:
        task = prog.add_task(f"Sintetizando [{engine_name}]", total=len(subs))

        async def _run_all() -> None:
            async def _synth_one(sub) -> None:
                seg_path = str(out_dir / f"seg_{sub.index:04d}.{eng.ext}")
                if isinstance(eng, _KokoroEngine):
                    await eng.synth(sub.content, selected_voice, seg_path, lang=kokoro_lang)
                else:
                    await eng.synth(sub.content, selected_voice, seg_path)
                _adjust_speed(seg_path, (sub.end - sub.start).total_seconds())
                prog.advance(task)

            await asyncio.gather(*[_synth_one(sub) for sub in subs])

        asyncio.run(_run_all())

    segments = [(sub.start.total_seconds(), str(out_dir / f"seg_{sub.index:04d}.{eng.ext}")) for sub in subs]
    _console.print(f"  → {out_dir.name}/ ({len(segments)} archivos .{eng.ext})")
    return segments
