"""config.py — environment loading, constants, path resolution.

Everything the app needs to know about *where* things live and *what* knobs
exist is resolved here. Paths are absolute and derived from this file's
location, so the app runs correctly regardless of the caller's cwd.
"""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env from the project root regardless of cwd. override=False keeps any
# real environment variables (e.g. CI secrets) authoritative.
load_dotenv(BASE_DIR / ".env", override=False)


# --- Credentials ------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()


# --- Broadcast targets (Single target or Dual YouTube + Twitch Simulcast) ---
STREAM_URL = os.getenv("STREAM_URL", "").strip()
STREAM_KEY = os.getenv("STREAM_KEY", "").strip()

YOUTUBE_STREAM_KEY = os.getenv("YOUTUBE_STREAM_KEY", "").strip()
YOUTUBE_STREAM_URL = os.getenv("YOUTUBE_STREAM_URL", "rtmp://a.rtmp.youtube.com/live2").strip()

TWITCH_STREAM_KEY = os.getenv("TWITCH_STREAM_KEY", "").strip()
TWITCH_STREAM_URL = os.getenv("TWITCH_STREAM_URL", "rtmp://live.twitch.tv/app").strip()


def get_stream_targets() -> list[tuple[str, str]]:
    """Return active (platform_name, full_rtmp_url) targets.

    Supports dual simultaneous broadcast to YouTube Live + Twitch.
    """
    targets = []
    if YOUTUBE_STREAM_KEY:
        targets.append(("YouTube Live", f"{YOUTUBE_STREAM_URL.rstrip('/')}/{YOUTUBE_STREAM_KEY}"))
    if TWITCH_STREAM_KEY:
        targets.append(("Twitch", f"{TWITCH_STREAM_URL.rstrip('/')}/{TWITCH_STREAM_KEY}"))

    if not targets and STREAM_KEY:
        url = STREAM_URL or "rtmp://localhost:1935"
        name = "Twitch" if "twitch" in url.lower() else ("YouTube" if "youtube" in url.lower() else "RTMP")
        targets.append((name, f"{url.rstrip('/')}/{STREAM_KEY}"))

    return targets


# --- LLM --------------------------------------------------------------------
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


# --- Signals ----------------------------------------------------------------
MAX_SIGNALS = 15       # signals requested per cycle
MIN_SIGNALS = 3        # minimum signals requested
HN_TOP_COUNT = 50      # expanded over-fetch pool for continuous ingestion


# --- Script -----------------------------------------------------------------
TARGET_WORDS = 1500    # ~10 min of speech
LLM_MAX_TOKENS = 4000
LLM_TEMPERATURE = 0.8


# --- TTS --------------------------------------------------------------------
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
TTS_RATE = "+5%"
TTS_CHUNK_CHARS = 1200  # edge-tts WebSocket payload limit for reliable synthesis


# --- Audio / video encoding -------------------------------------------------
AUDIO_BITRATE = "128k"
AUDIO_SAMPLE_RATE = "44100"
AUDIO_CHANNELS = "2"

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30
VIDEO_BITRATE = "500k"
VIDEO_GOP = 60


# --- Paths ------------------------------------------------------------------
DB_PATH = BASE_DIR / "radio.db"
QUEUE_DIR = BASE_DIR / "queue"
ASSETS_DIR = BASE_DIR / "assets"
STATIC_VISUAL = ASSETS_DIR / "static_visual.jpg"
TOOLS_DIR = BASE_DIR / "tools"
FFMPEG_DIR = TOOLS_DIR / "ffmpeg" / "bin"
MEDIAMTX_DIR = TOOLS_DIR / "mediamtx"
MEDIAMTX_EXE = MEDIAMTX_DIR / "mediamtx.exe"


def _resolve_binary(name: str) -> str:
    """Resolve ffmpeg/ffprobe: system PATH first, project-local portable second.

    The portable escape hatch is what makes this work on a machine with no
    admin rights and no winget/choco (specs §5).
    """
    found = shutil.which(name)
    if found:
        return found

    suffix = ".exe" if os.name == "nt" else ""
    local = FFMPEG_DIR / f"{name}{suffix}"
    if local.exists():
        return str(local)

    raise FileNotFoundError(
        f"{name} not found on PATH and not present at {local}. "
        f"Run the Phase 0 setup step to install the portable build."
    )


FFMPEG = _resolve_binary("ffmpeg")
FFPROBE = _resolve_binary("ffprobe")


def require_credentials(*names: str) -> None:
    """Raise with an actionable message if a required secret is missing."""
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key":
        raise RuntimeError(
            f"Missing GROQ_API_KEY in {BASE_DIR / '.env'}. "
            f"Get a free key at https://console.groq.com and set GROQ_API_KEY in .env"
        )
    targets = get_stream_targets()
    if not targets:
        raise RuntimeError(
            f"No active streaming targets found in {BASE_DIR / '.env'}! "
            f"Set YOUTUBE_STREAM_KEY, TWITCH_STREAM_KEY, or STREAM_KEY in .env"
        )
