import os

WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
TTS_ENGINE: str = os.getenv("TTS_ENGINE", "edge")
