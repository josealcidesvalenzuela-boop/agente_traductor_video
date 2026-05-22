import os
from pathlib import Path

import ollama
import srt
from rich.progress import Progress, BarColumn, MofNCompleteColumn, TextColumn, TimeElapsedColumn

_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
_BATCH_SIZE = 20


def _translate_batch(texts: list[str], source: str, target: str, system: str) -> list[str]:
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
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
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


def translate(
    srt_path: str,
    source_lang: str = "auto",
    target_lang: str = "en",
    tone: str = "neutral",
    domain: str = "general",
    output_path: str | None = None,
) -> str:
    """Translate SRT preserving all indices and timestamps. Returns translated SRT path."""
    path = Path(srt_path)
    subs = list(srt.parse(path.read_text(encoding="utf-8")))
    total_batches = -(-len(subs) // _BATCH_SIZE)

    system = (
        f"You are a professional subtitle translator specializing in {domain} content. "
        f"Translate from {source_lang} to {target_lang} using a {tone} tone. "
        "Keep translations concise to fit subtitle display constraints. "
        "Preserve names, technical terms, and formatting."
    )

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn()) as prog:
        task = prog.add_task(f"Traduciendo {source_lang}→{target_lang} [{_MODEL}]", total=total_batches)
        for i in range(0, len(subs), _BATCH_SIZE):
            batch = subs[i : i + _BATCH_SIZE]
            translated = _translate_batch([s.content for s in batch], source_lang, target_lang, system)
            for sub, text in zip(batch, translated):
                sub.content = text
            prog.advance(task)

    out = Path(output_path) if output_path else path.with_stem(path.stem + "_translated")
    out.write_text(srt.compose(subs), encoding="utf-8")
    print(f"  → {out.name}")
    return str(out)
