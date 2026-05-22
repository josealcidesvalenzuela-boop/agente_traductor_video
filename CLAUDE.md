# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Local video dubbing pipeline with 4 stages:
1. **Transcribe** — Faster-Whisper (local GPU) converts video audio to `.SRT`
2. **Translate** — Ollama (local LLM) translates the `.SRT` preserving all timestamps
3. **TTS** — Edge-TTS (cloud) or Kokoro-ONNX (local) synthesizes the translated text to audio
4. **Merge** — FFmpeg combines the dubbed audio with the original video

## Stack

- **Language**: Python 3.11+
- **Package manager**: `uv` — use `uv run`, `uv add`, `uv sync` instead of `pip` or `python` directly
- **Key deps**: `faster-whisper`, `ollama`, `edge-tts`, `kokoro-onnx`, `ffmpeg-python`, `srt`
- **External tools**: FFmpeg must be installed and on PATH (`ffmpeg -version` to verify), Ollama must be running (`ollama serve`)

## Project Structure

```
agente_traductor_video/
├── pipeline/
│   ├── __init__.py      # Windows CUDA DLL path setup
│   ├── transcribe.py    # Stage 1: Faster-Whisper → .srt
│   ├── translate.py     # Stage 2: Ollama → translated .srt
│   ├── tts.py           # Stage 3: Edge-TTS / Kokoro → audio segments
│   └── merge.py         # Stage 4: FFmpeg → final dubbed video
├── config.py            # All env var defaults (single source of truth)
├── main.py              # CLI entrypoint (Typer) + RunPaths dataclass
├── pyproject.toml
├── .env.example
└── salida/              # Generated output (gitignored)
    └── video_YYYYMMDD_HHMMSS/
        ├── transcription.srt
        ├── translated.srt
        ├── tts/
        └── dubbed.mp4
```

## Commands

```bash
uv run python main.py <video> [source_lang] [target_lang]  # full pipeline
uv run python pipeline/transcribe.py <video> [lang]        # transcribe only
uv run pytest                                               # run tests
uv run ruff format .                                        # format
uv run ruff check .                                         # lint
```

## GPU / Faster-Whisper

Always use `device="cuda"` and `compute_type="float16"` for GPU inference. Fall back to `device="cpu"` and `compute_type="int8"` only when CUDA is unavailable. Default model: `large-v3` (overridable via `WHISPER_MODEL` env var).

## Ollama

Ollama must be running locally before the translate stage. Default endpoint: `http://localhost:11434` (overridable via `OLLAMA_HOST`). Preferred models: `qwen2.5-coder` or `llama3.1` — pull with `ollama pull <model>` before first use.

## SRT Convention

The translate stage must preserve **exact SRT block indices and timestamp lines** — only the subtitle text lines change. Never modify the numeric index or `HH:MM:SS,mmm --> HH:MM:SS,mmm` lines.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `WHISPER_MODEL` | `large-v3` | Faster-Whisper model size |
| `OLLAMA_MODEL` | `qwen2.5-coder` | Ollama model |
| `TTS_ENGINE` | `edge` | `edge` (cloud) or `kokoro` (local) |

## Testing

`uv run pytest` — unit tests per pipeline stage using fixture `.srt` files. Test each stage in isolation before testing the full pipeline.
