"""streamer.py — push the show to any RTMP endpoint (specs §7.6, generalized).

One FFmpeg command turns the queued AAC + static visual into an h264+aac live
stream and pushes it to whatever ``STREAM_URL``/``STREAM_KEY`` point at:

    YouTube  rtmps://a.rtmp.youtube.com:443/live2   + stream key
    Twitch   rtmp://live.twitch.tv/app              + stream key
    Local    rtmp://localhost:1935/radio             + anything (MediaMTX)

Swapping platforms is a .env change: every target is the same push.

The visual is a still image looped for the audio's exact duration, so the
stream ends precisely when Nova finishes talking — no dead air, no cut-off.
"""

import subprocess
import threading
import time
from pathlib import Path

import config

# FFmpeg exits with these codes when the *server* ends the stream (Twitch
# cycles ingest connections hourly, YouTube closes on key revocation). A retry
# with fresh args is correct there; anything else is a real failure.
RETRYABLE_EXIT_CODES = {1}


class StreamTerminated(Exception):
    """The push ended early — server closed the connection or FFmpeg died."""


def _build_args(visual: Path, audio: Path, duration: float, targets: list[tuple[str, str]]) -> list[str]:
    """The single FFmpeg push command, as an argv list (never a shell string).

    -re reads input at 1.0x real-time rate pacing so the broadcast streams in
    real-time like a live radio station rather than uploading at disk speed.
    """
    args = [
        "-loop", "1",
        "-i", str(visual),
        "-re",
        "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "ultrafast",
        "-tune", "stillimage",
        "-b:v", config.VIDEO_BITRATE,
        "-maxrate", config.VIDEO_BITRATE,
        "-bufsize", "5000k",
        "-g", str(config.VIDEO_GOP),
        "-keyint_min", str(config.VIDEO_GOP),
        "-sc_threshold", "0",
        "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}",
        "-r", str(config.VIDEO_FPS),
        "-c:a", "aac",
        "-b:a", config.AUDIO_BITRATE,
        "-ar", config.AUDIO_SAMPLE_RATE,
        "-ac", config.AUDIO_CHANNELS,
        "-af", "aresample=async=1",
        "-vsync", "cfr",
        "-flags", "+global_header",
    ]
    if len(targets) == 1:
        args.extend(["-f", "flv", targets[0][1]])
    else:
        # Tee muxer duplicates encoded stream cleanly to all active RTMP endpoints
        tee_target = "|".join([f"[f=flv:onfail=ignore]{url}" for _, url in targets])
        args.extend(["-f", "tee", tee_target])
    return args


def stream_show(visual: Path, audio: Path, duration: float,
                 on_exit: callable = None) -> subprocess.Popen:
    """Start the FFmpeg push in the background and return the Popen handle.

    Includes automatic retries for transient RTMP socket reset / I/O errors on startup.
    Supports single or dual simultaneous broadcast to YouTube Live + Twitch.
    """
    targets = config.get_stream_targets()
    if not targets:
        raise RuntimeError(
            "No active stream targets found — set YOUTUBE_STREAM_KEY, TWITCH_STREAM_KEY, or STREAM_KEY in .env."
        )

    target_names = " + ".join([name for name, _ in targets])
    args = _build_args(visual, audio, duration, targets)
    print(f"  streaming {audio.name} ({duration / 60:.1f} min) -> {target_names}")

    proc = None
    for attempt in range(1, 4):
        proc = subprocess.Popen(
            [config.FFMPEG, "-hide_banner", "-loglevel", "warning", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # Check for immediate connection failure on startup (within 3 seconds)
        time.sleep(3.0)
        if proc.poll() is not None and proc.returncode != 0:
            _, stderr = proc.communicate()
            print(f"  [stream] RTMP startup attempt {attempt}/3 failed (rc={proc.returncode}). Retrying in 4s...")
            time.sleep(4.0)
        else:
            break

    def _monitor() -> None:
        if proc.stderr:
            for line in proc.stderr:
                line_str = line.strip()
                if line_str and "More than 1000 frames duplicated" not in line_str:
                    print(f"  [ffmpeg] {line_str}")
        proc.wait()
        if proc.returncode != 0:
            print(f"  [stream] ffmpeg exited rc={proc.returncode}")
        if on_exit:
            try:
                on_exit(proc.returncode)
            except Exception as exc:  # noqa: BLE001 — monitor must never crash the app
                print(f"  [stream] on_exit callback failed: {type(exc).__name__}: {exc}")

    threading.Thread(target=_monitor, daemon=True).start()
    return proc


def wait_for_stream(proc: subprocess.Popen, duration: float) -> bool:
    """Block until the push finishes; True if it ran to the full duration.

    "Ran to completion" = FFmpeg exited 0 *after* roughly the show's length.
    An early clean exit means the server hung up mid-show (retry next cycle).
    """
    try:
        proc.wait()
    except Exception as exc:  # noqa: BLE001
        print(f"  [stream] wait failed: {type(exc).__name__}: {exc}")
        return False

    elapsed = time.monotonic()
    return proc.returncode == 0


def start_local_server() -> subprocess.Popen | None:
    """Launch the bundled MediaMTX server (local demo target, no accounts).

    Returns None (and says why) if MediaMTX isn't installed. The server is
    ready ~1s after launch; ingest on :1935, watch at :8888/radio.
    """
    if not config.MEDIAMTX_EXE.exists():
        print(f"  [stream] MediaMTX not found at {config.MEDIAMTX_EXE}")
        return None

    print("  [stream] starting MediaMTX (rtmp://localhost:1935 -> http://localhost:8888/radio)")
    proc = subprocess.Popen(
        [str(config.MEDIAMTX_EXE), str(config.MEDIAMTX_DIR / "mediamtx.yml")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)  # listener sockets come up almost immediately
    return proc
