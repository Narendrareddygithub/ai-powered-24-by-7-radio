"""main.py — entrypoint for the autonomous 24/7 AI Radio Station.

Run:
    python main.py
"""

import sys
from radio import run_radio_loop

if __name__ == "__main__":
    sys.exit(run_radio_loop())
