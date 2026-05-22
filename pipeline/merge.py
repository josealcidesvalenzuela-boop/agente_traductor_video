from pathlib import Path

import ffmpeg


def merge(
    video_path: str,
    audio_segments: list[tuple[float, str]],
    output_path: str | None = None,
) -> str:
    """Mix timed audio segments with original video using FFmpeg. Returns output path."""
    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])

    if output_path is None:
        p = Path(video_path)
        output_path = str(p.parent / f"{p.stem}_dubbed.mp4")

    print(f"[merge] {len(audio_segments)} segmentos · duración={duration:.1f}s")

    video_in = ffmpeg.input(video_path)
    # Silent base track for the full video duration
    base_audio = ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi", t=duration)

    streams = [base_audio]
    for start_sec, audio_path in audio_segments:
        delay_ms = int(start_sec * 1000)
        seg = ffmpeg.input(audio_path).audio.filter("adelay", f"{delay_ms}|{delay_ms}")
        streams.append(seg)

    mixed = ffmpeg.filter(streams, "amix", inputs=len(streams), normalize=0)

    out = ffmpeg.output(
        video_in.video,
        mixed,
        output_path,
        vcodec="copy",
        acodec="aac",
    )
    ffmpeg.run(out, overwrite_output=True, quiet=True)

    print(f"[merge] → {output_path}")
    return output_path
