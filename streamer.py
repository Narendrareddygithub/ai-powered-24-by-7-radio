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


def _build_args(visual: Path, audio: Path, duration: float) -> list[str]:
    """The single FFmpeg push command, as an argv list (never a shell string).

    -loop 1 on the image + -t <duration> bounds the output: a 12-min AAC renders
    a 12-min video, and FFmpeg exits cleanly when the audio runs out.
    """
    return [
        "-loop", "1",
        "-i", str(visual),
        "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-b:v", config.VIDEO_BITRATE,
        "-g", str(config.VIDEO_GOP),
        "-vf", f"scale={config.VIDEO_WIDTH}:{config.VIDEO_HEIGHT}",
        "-r", str(config.VIDEO_FPS),
        "-c:a", "aac",
        "-b:a", config.AUDIO_BITRATE,
        "-ar", config.AUDIO_SAMPLE_RATE,
        "-ac", config.AUDIO_CHANNELS,
        "-f", "flv",
        f"{config.STREAM_URL}/{config.STREAM_KEY}",
    ]


def stream_show(visual: Path, audio: Path, duration: float,
                 on_exit: callable = None) -> subprocess.Popen:
    """Start the FFmpeg push in the background and return the Popen handle.

    ``on_exit`` (if given) runs in the monitor thread after the push ends, so
    the Phase 6 loop can kick off the next cycle without polling.
    """
    key = config.STREAM_KEY
    if not key:
        raise RuntimeError(
            "STREAM_KEY is empty — set it in .env (any value works for the "
            "local MediaMTX target; 'radio' is conventional)."
        )

    args = _build_args(visual, audio, duration)
    print(f"  streaming {audio.name} ({duration / 60:.1f} min) -> {config.STREAM_URL}")

    proc = subprocess.Popen(
        [config.FFMPEG, "-hide_banner", "-loglevel", "warning", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _monitor() -> None:
        _, stderr = proc.communicate()
        tail = [ln for ln in (stderr or "").strip().splitlines() if ln][-3:]
        if proc.returncode != 0:
            print(f"  [stream] ffmpeg exited rc={proc.returncode}")
            for line in tail:
                print(f"  [stream] {line}")
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
