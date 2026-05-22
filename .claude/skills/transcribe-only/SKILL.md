---
name: transcribe-only
description: Transcribe a video or audio file to .SRT using Faster-Whisper (local GPU). Usage: /transcribe-only <input_file> [language]
disable-model-invocation: true
---

Run only Stage 1 using `uv run python pipeline/transcribe.py $ARGUMENTS`.

Output: <name>.srt in the same directory as the input file.
Report the Whisper model used, device (cuda/cpu), compute_type, and total transcription time.
