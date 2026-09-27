"""main.py — entrypoint for the autonomous 24/7 AI Radio Station.

Run:
    python main.py
"""

import sys

# Reconfigure stdout and stderr for UTF-8 encoding on Windows console
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from radio import run_radio_loop

if __name__ == "__main__":
    sys.exit(run_radio_loop())
