"""
Interfaz web para agente_traductor_video.
Iniciar con: .\traducir.ps1 serve
"""
import asyncio
import json
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import ffmpeg
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse

app = FastAPI(title="agente_traductor_video")

_UPLOAD_DIR = Path("salida") / "uploads"
_SEGMENT_SEC = 600  # 10 minutos

# { job_id: { status, video_path, output_path, progress_queue, last_event, params } }
_jobs: dict[str, dict[str, Any]] = {}


# ── Helpers de video ──────────────────────────────────────────────────────────


def _duration(path: str) -> float:
    return float(ffmpeg.probe(path)["format"]["duration"])


def _split(video: Path, seg_sec: int) -> list[Path]:
    dur = _duration(str(video))
    if dur <= seg_sec:
        return [video]
    parts, i, t = [], 0, 0.0
    while t < dur:
        out = video.parent / f"{video.stem}_part{i:02d}{video.suffix}"
        (
            ffmpeg.input(str(video), ss=t, t=seg_sec)
            .output(str(out), vcodec="copy", acodec="copy")
            .run(overwrite_output=True, quiet=True)
        )
        if out.exists() and out.stat().st_size > 1000:
            parts.append(out)
        t += seg_sec
        i += 1
    return parts


def _concat(parts: list[Path], output: Path) -> None:
    lst = output.parent / "concat_list.txt"
    lst.write_text("\n".join(f"file '{p.resolve()}'" for p in parts), encoding="utf-8")
    (
        ffmpeg.input(str(lst), format="concat", safe=0)
        .output(str(output), vcodec="copy", acodec="copy")
        .run(overwrite_output=True, quiet=True)
    )
    lst.unlink()


# ── Runner del pipeline (hilo de fondo) ──────────────────────────────────────


def _run_job(job_id: str) -> None:
    job = _jobs[job_id]
    q: queue.Queue = job["progress_queue"]
    p = job["params"]
    video: Path = job["video_path"]

    def emit(stage: str, msg: str, pct: int) -> None:
        event = {"stage": stage, "message": msg, "progress": pct}
        job["last_event"] = event
        q.put(event)

    try:
        from pipeline.transcribe import transcribe
        from pipeline.translate import translate
        from pipeline.tts import generate_audio
        from pipeline.merge import merge

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        dur = _duration(str(video))
        emit("init", f"Duración: {dur / 60:.1f} min", 0)

        if dur > _SEGMENT_SEC:
            emit("split", f"Video {dur / 60:.1f} min → particionando en segmentos de 10 min…", 2)
            parts = _split(video, _SEGMENT_SEC)
            emit("split", f"{len(parts)} segmentos listos", 5)
        else:
            parts = [video]

        n = len(parts)
        dubbed: list[Path] = []

        for i, seg in enumerate(parts):
            base = 5 + i * 90 // n
            step = max(1, 90 // n)
            lbl = f"[{i + 1}/{n}] " if n > 1 else ""
            out_dir = Path("salida") / f"{seg.stem}_{run_id}"
            out_dir.mkdir(parents=True, exist_ok=True)

            emit("transcribe", f"{lbl}Transcribiendo con Faster-Whisper…", base)
            srt = transcribe(
                str(seg),
                language=None if p["source"] == "auto" else p["source"],
                output_path=str(out_dir / "transcription.srt"),
            )

            emit("translate", f"{lbl}Traduciendo con Ollama…", base + step // 4)
            tr_srt = translate(
                srt,
                source_lang=p["source"],
                target_lang=p["target"],
                tone=p["tone"],
                domain=p["domain"],
                output_path=str(out_dir / "translated.srt"),
            )

            emit("tts", f"{lbl}Sintetizando voz ({p['engine']})…", base + step // 2)
            audio_segs = generate_audio(
                tr_srt,
                target_lang=p["target"],
                voice=p["voice"] or None,
                engine=p["engine"] or None,
                output_dir=str(out_dir / "tts"),
            )

            emit("merge", f"{lbl}Mezclando audio+video con FFmpeg…", base + 3 * step // 4)
            result = merge(str(seg), audio_segs, output_path=str(out_dir / "dubbed.mp4"))
            dubbed.append(Path(result))

        if len(dubbed) > 1:
            emit("concat", "Concatenando segmentos finales…", 96)
            final_dir = Path("salida") / f"{video.stem}_{run_id}"
            final_dir.mkdir(parents=True, exist_ok=True)
            final = final_dir / "dubbed.mp4"
            _concat(dubbed, final)
        else:
            final = dubbed[0]

        job["output_path"] = final
        job["status"] = "done"
        emit("done", str(final), 100)

    except Exception as exc:
        job["status"] = "error"
        emit("error", str(exc), -1)
    finally:
        q.put(None)


# ── Rutas ─────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.post("/upload")
async def upload(file: UploadFile):
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:8]
    suffix = Path(file.filename or "video.mp4").suffix or ".mp4"
    dest = _UPLOAD_DIR / f"{job_id}{suffix}"
    dest.write_bytes(await file.read())
    dur = _duration(str(dest))
    n = max(1, int(dur // _SEGMENT_SEC) + (1 if dur % _SEGMENT_SEC else 0))
    _jobs[job_id] = {
        "status": "pending",
        "video_path": dest,
        "output_path": None,
        "progress_queue": queue.Queue(),
        "last_event": None,
        "params": {},
    }
    return {
        "job_id": job_id,
        "filename": file.filename,
        "duration": dur,
        "will_split": dur > _SEGMENT_SEC,
        "segments": n,
    }


@app.post("/jobs/{job_id}/start")
async def start_job(job_id: str, request: Request):
    if job_id not in _jobs:
        return Response(status_code=404)
    _jobs[job_id]["params"] = await request.json()
    _jobs[job_id]["status"] = "running"
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return {"status": "started"}


@app.get("/jobs/{job_id}/progress")
async def progress(job_id: str):
    if job_id not in _jobs:
        return Response(status_code=404)

    job = _jobs[job_id]

    # Si el job ya terminó, responder de inmediato sin esperar la queue
    if job["status"] in ("done", "error"):
        async def immediate():
            if job["last_event"]:
                yield f"data: {json.dumps(job['last_event'], ensure_ascii=False)}\n\n"
            yield 'data: {"done":true}\n\n'

        return StreamingResponse(
            immediate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    q: queue.Queue = job["progress_queue"]
    loop = asyncio.get_event_loop()

    async def stream():
        while True:
            try:
                item = await loop.run_in_executor(None, lambda: q.get(timeout=30))
                if item is None:
                    yield 'data: {"done":true}\n\n'
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except asyncio.CancelledError:
                break
            except Exception:
                yield 'data: {"heartbeat":true}\n\n'

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/jobs/{job_id}/video")
async def video(job_id: str):
    if job_id not in _jobs or _jobs[job_id]["status"] != "done":
        return Response(status_code=404)
    path = _jobs[job_id]["output_path"]
    stem = _jobs[job_id]["video_path"].stem
    return FileResponse(str(path), media_type="video/mp4", filename=f"{stem}_dubbed.mp4")


@app.get("/voices")
async def voices(lang: str = "", engine: str = "edge"):
    from pipeline.tts import _EDGE_VOICES, _KOKORO_VOICES

    if engine == "kokoro":
        default = _KOKORO_VOICES.get(lang, "af_bella")
        voice_list = [_KOKORO_VOICES[k] for k in _KOKORO_VOICES if not lang or k == lang]
        return {"default": default, "voices": voice_list or [default], "free_input": False}
    else:
        default = _EDGE_VOICES.get(lang, "en-US-JennyNeural")
        return {"default": default, "voices": [default], "free_input": True}
