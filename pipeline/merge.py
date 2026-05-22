from pathlib import Path

import ffmpeg
from rich.console import Console

_console = Console()


def merge(
    video_path: str,
    audio_segments: list[tuple[float, str]],
    output_path: str | None = None,
) -> str:
    """Mix timed audio segments over the original video track. Returns output path."""
    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])

    if output_path is None:
        p = Path(video_path)
        output_path = str(p.parent / f"{p.stem}_dubbed.mp4")

    _console.print(f"  {len(audio_segments)} segmentos · duración={duration:.1f}s")

    video_in = ffmpeg.input(video_path)
    base_audio = ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi", t=duration)
    streams = [base_audio]
    for start_sec, audio_path in audio_segments:
        delay_ms = int(start_sec * 1000)
        streams.append(ffmpeg.input(audio_path).audio.filter("adelay", f"{delay_ms}|{delay_ms}"))

    mixed = ffmpeg.filter(streams, "amix", inputs=len(streams), normalize=0)
    ffmpeg.run(
        ffmpeg.output(video_in.video, mixed, output_path, vcodec="copy", acodec="aac"),
        overwrite_output=True,
        quiet=True,
    )

    _console.print(f"  → [bold]{Path(output_path).name}[/]")
    return output_path
