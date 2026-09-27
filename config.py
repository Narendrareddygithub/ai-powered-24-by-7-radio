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


# --- Broadcast target -------------------------------------------------------
# Any RTMP/RTMPS endpoint works — YouTube, Twitch, Kick, or a local MediaMTX
# server (tools/mediamtx). Switching platforms is a .env change, not a code
# change, because every target is the same FFmpeg push.
#
#   YouTube : STREAM_URL=rtmps://a.rtmp.youtube.com:443/live2
#             STREAM_KEY=<YouTube Studio stream key>   (24h activation wait)
#   Twitch  : STREAM_URL=rtmp://live.twitch.tv/app
#             STREAM_KEY=<twitch.tv/settings/stream key>  (2FA required first)
#   Local   : STREAM_URL=rtmp://localhost:1935
#             STREAM_KEY=radio   (MediaMTX has no auth; the key names the path)
#             then watch http://localhost:8888/radio
STREAM_URL = os.getenv("STREAM_URL", "rtmp://localhost:1935").strip()
STREAM_KEY = os.getenv("STREAM_KEY", "").strip()


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
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AndrewMultilingualNeural")
TTS_RATE = "+5%"
TTS_CHUNK_CHARS = 8000  # edge-tts WebSocket drops on very long text


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
    """Raise with an actionable message if a required secret is missing.

    Called by entrypoints that actually need the secrets, so that credential-
    free phases (db, ingest) stay runnable without a populated .env.
    """
    values = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "STREAM_KEY": STREAM_KEY,
    }
    placeholders = {"your_groq_api_key", "your_youtube_stream_key", "your_stream_key"}
    missing = []
    for name in names:
        value = values[name]
        if not value or value in placeholders:
            missing.append(name)
    if missing:
        raise RuntimeError(
            f"Missing credentials in {BASE_DIR / '.env'}: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill in the values."
        )
