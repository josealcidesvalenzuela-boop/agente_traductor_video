import os
from pathlib import Path

import ollama
import srt

_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
_BATCH_SIZE = 20


def _translate_batch(texts: list[str], source: str, target: str) -> list[str]:
    numbered = "\n".join(f"{i + 1}|||{t}" for i, t in enumerate(texts))
    prompt = (
        f"Translate each subtitle line from {source} to {target}. "
        "Return ONLY the translations, keeping the N||| number prefix. "
        "Do not alter the numbers or the ||| separator.\n\n"
        f"{numbered}"
    )
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    client = ollama.Client(host=host)
    response = client.chat(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )
    result: list[str | None] = [None] * len(texts)
    for line in response.message.content.strip().splitlines():
        if "|||" in line:
            prefix, _, translation = line.partition("|||")
            try:
                idx = int(prefix.strip()) - 1
                if 0 <= idx < len(texts):
                    result[idx] = translation.strip()
            except ValueError:
                pass
    return [r if r is not None else texts[i] for i, r in enumerate(result)]


def translate(srt_path: str, source_lang: str = "auto", target_lang: str = "en") -> str:
    """Translate SRT preserving all indices and timestamps. Returns translated SRT path."""
    path = Path(srt_path)
    subs = list(srt.parse(path.read_text(encoding="utf-8")))
    total_batches = -(-len(subs) // _BATCH_SIZE)  # ceil division
    print(f"[translate] {len(subs)} subtítulos · {source_lang}→{target_lang} · modelo={_MODEL}")

    for batch_num, i in enumerate(range(0, len(subs), _BATCH_SIZE), 1):
        batch = subs[i : i + _BATCH_SIZE]
        translated = _translate_batch([s.content for s in batch], source_lang, target_lang)
        for sub, text in zip(batch, translated):
            sub.content = text
        print(f"[translate]  lote {batch_num}/{total_batches} ✓")

    output_path = path.with_stem(path.stem + "_translated")
    output_path.write_text(srt.compose(subs), encoding="utf-8")
    print(f"[translate] → {output_path}")
    return str(output_path)
