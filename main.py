"""main.py — entrypoint for the autonomous 24/7 AI Radio Station.

Run:
    python main.py
"""

import os
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# Reconfigure stdout and stderr for UTF-8 encoding on Windows console
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _start_dummy_health_server():
    port = int(os.getenv("PORT", "10000"))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"24/7 AI Radio Station Running OK\n")

        def log_message(self, format, *args):
            pass  # Silent logs for health pings

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"  [health] Background status listener active on port {port}")
    except Exception as exc:
        print(f"  [health] Note: Could not bind health port {port}: {exc}")


def _start_keepalive_pinger():
    """Self-ping the health endpoint every 5 minutes to prevent Render free-tier sleep."""
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    port = int(os.getenv("PORT", "10000"))

    def _ping_loop():
        while True:
            time.sleep(300)  # Every 5 minutes
            try:
                target = render_url or f"http://localhost:{port}"
                urllib.request.urlopen(f"{target}/", timeout=5)
            except Exception:
                pass  # Best-effort; don't crash on network hiccup

    threading.Thread(target=_ping_loop, daemon=True).start()


from radio import run_radio_loop

if __name__ == "__main__":
    _start_dummy_health_server()
    _start_keepalive_pinger()
    sys.exit(run_radio_loop())
