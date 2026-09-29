"""audio_synth.py — script text to a broadcast-ready AAC file.

Pipeline (specs §7.5):

    script -> paragraph chunks -> edge-tts MP3s -> FFmpeg concat -> AAC

edge-tts drops long WebSocket payloads, so the script is chunked at paragraph
boundaries under `TTS_CHUNK_CHARS` and synthesized piecewise.

Returns ``(aac_path, duration_seconds)``, or ``(None, None)`` on failure so the
caller skips the cycle rather than airing a partial show.
"""

import asyncio
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import edge_tts

import config


def chunk_script(text: str, max_chars: int = config.TTS_CHUNK_CHARS) -> list[str]:
    """Split `text` into chunks on paragraph boundaries, each <= max_chars.

    Paragraphs are accumulated greedily. A single paragraph longer than
    max_chars is split on sentence boundaries; a single sentence longer than
    that is hard-sliced, so the function always terminates within the limit.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        if len(para) > max_chars:
            flush()
            chunks.extend(_split_oversized(para, max_chars))
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            flush()
            current = para
    flush()
    return chunks


def _split_oversized(paragraph: str, max_chars: int) -> list[str]:
    """Break a too-long paragraph into <= max_chars pieces at sentence ends."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:  # pathological: one giant sentence
            if current:
                pieces.append(current.strip())
                current = ""
            pieces.append(sentence[:max_chars].strip())
            sentence = sentence[max_chars:]
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}" if current else sentence
        else:
            if current:
                pieces.append(current.strip())
            current = sentence
    if current.strip():
        pieces.append(current.strip())
    return pieces


async def _synthesize_chunk(text: str, out_path: Path, voice: str | None = None) -> None:
    """Render one chunk to MP3 via edge-tts streaming."""
    v = voice or config.TTS_VOICE
    communicate = edge_tts.Communicate(
        text, voice=v, rate=config.TTS_RATE, pitch=config.TTS_PITCH
    )
    wrote_audio = False
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
                wrote_audio = True
    if not wrote_audio:
        raise RuntimeError(f"edge-tts returned no audio for chunk ({len(text)} chars, voice={v})")


def _run_ffmpeg(args: list[str], label: str) -> None:
    """Run FFmpeg with list argv (no shell), raising with the stderr tail."""
    result = subprocess.run(
        [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-5:]
        raise RuntimeError(f"{label} failed (rc={result.returncode}): {' | '.join(tail)}")


def probe_duration(path: Path) -> float:
    """Audio duration in seconds, via ffprobe."""
    result = subprocess.run(
        [
            config.FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {(result.stderr or '').strip()[:200]}")
    return float(result.stdout.strip())


def synthesize_audio(script: str) -> tuple[Path | None, float | None]:
    """Render `script` to `queue/session_<timestamp>.aac`.

    Also writes the script alongside as a `.txt` sidecar (specs §7.5 step 5),
    so an aired show can always be traced back to its exact words.
    """
    chunks = chunk_script(script)
    if not chunks:
        print("  [warn] nothing to synthesize — empty script")
        return None, None

    config.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    aac_path = config.QUEUE_DIR / f"session_{stamp}.aac"
    txt_path = config.QUEUE_DIR / f"session_{stamp}.txt"

    fallback_voices = [config.TTS_VOICE, "en-US-BrianNeural", "en-US-GuyNeural", "en-US-EricNeural", "en-US-AriaNeural"]
    # De-duplicate preserving order
    voices_to_try = list(dict.fromkeys(fallback_voices))

    tmp_dir = Path(tempfile.mkdtemp(prefix="radio_tts_"))
    try:
        chunk_paths: list[Path] = []
        for i, chunk in enumerate(chunks, start=1):
            out = tmp_dir / f"chunk_{i:03d}.mp3"
            print(f"  TTS chunk {i}/{len(chunks)} ({len(chunk)} chars)")
            success = False
            for attempt, v in enumerate(voices_to_try, start=1):
                try:
                    asyncio.run(_synthesize_chunk(chunk, out, voice=v))
                    success = True
                    break
                except Exception as exc:  # noqa: BLE001 — retry transient TTS WebSocket / voice errors
                    print(f"  [warn] chunk {i} attempt {attempt}/{len(voices_to_try)} (voice={v}) failed ({type(exc).__name__})")
                    if attempt < len(voices_to_try):
                        import time
                        time.sleep(1.0)
            if not success:
                raise RuntimeError(f"TTS synthesis failed for chunk {i}/{len(chunks)}")
            chunk_paths.append(out)

        combined = tmp_dir / "combined.mp3"
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in chunk_paths), encoding="utf-8"
        )
        _run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy",
             str(combined)],
            "concat",
        )

        _run_ffmpeg(
            ["-i", str(combined),
             "-c:a", "aac", "-b:a", config.AUDIO_BITRATE,
             "-ar", config.AUDIO_SAMPLE_RATE, "-ac", config.AUDIO_CHANNELS,
             str(aac_path)],
            "aac encode",
        )

        txt_path.write_text(script, encoding="utf-8")
        duration = probe_duration(aac_path)
        return aac_path, duration
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def ensure_visual_loop_video(visual: Path | None = None) -> Path:
    """Ensure a 2-second broadcast-spec video loop (720p 15fps 2500k CBR H.264) exists.

    Generating this 2-second video reference template once allows pre_encode_show()
    to remux full show videos in < 1 second via -c:v copy (zero CPU re-encoding).
    """
    if visual is None:
        visual = config.STATIC_VISUAL

    loop_mp4 = config.ASSETS_DIR / "visual_loop_2s.mp4"
    if loop_mp4.exists():
        return loop_mp4

    print(f"  [audio_synth] 🎬 Generating 2-second visual video loop reference ({loop_mp4.name})...")
    loop_flag = ["-ignore_loop", "0"] if str(visual).endswith(".gif") else ["-loop", "1"]
    _run_ffmpeg(
        [
            *loop_flag,
            "-i", str(visual),
            "-t", "2.0",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-b:v", config.VIDEO_BITRATE,
            "-minrate", config.VIDEO_BITRATE,
            "-maxrate", config.VIDEO_BITRATE,
            "-bufsize", config.VIDEO_BITRATE,
            "-nal-hrd", "cbr",
            "-g", str(config.VIDEO_GOP),
            "-keyint_min", str(config.VIDEO_GOP),
            "-sc_threshold", "0",
            "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}",
            "-r", str(config.VIDEO_FPS),
            "-an",
            str(loop_mp4),
        ],
        "generate visual loop video",
    )
    return loop_mp4


def pre_encode_show(aac_path: Path, visual: Path | None = None) -> tuple[Path, float]:
    """Mux visual video loop + AAC audio into a broadcast-ready FLV container file.

    Uses stream_loop with -c:v copy -c:a copy for instant (< 2s) remuxing
    with zero CPU load, avoiding long cold-start build delays on free containers.

    Returns (flv_path, duration_seconds).
    """
    duration = probe_duration(aac_path)
    flv_path = aac_path.with_suffix(".flv")

    loop_mp4 = ensure_visual_loop_video(visual)

    _run_ffmpeg(
        [
            "-stream_loop", "-1",
            "-i", str(loop_mp4),
            "-i", str(aac_path),
            "-t", f"{duration:.3f}",
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "flv",
            str(flv_path),
        ],
        "fast pre-encode show",
    )

    return flv_path, duration



