---
name: translate-video
description: Run the full 4-stage video dubbing pipeline (transcribe → translate → TTS → merge) on a video file. Usage: /translate-video <input_video> [source_lang] [target_lang]
disable-model-invocation: true
---

Run the full pipeline using `uv run python main.py $ARGUMENTS`.

Stage order:
1. pipeline/transcribe.py — Faster-Whisper → <name>.srt
2. pipeline/translate.py — Ollama → <name>_translated.srt (timestamps unchanged)
3. pipeline/tts.py — TTS engine → per-segment audio files
4. pipeline/merge.py — FFmpeg → <name>_dubbed.mp4

Report the output file path on success, or which stage failed and why on error.
