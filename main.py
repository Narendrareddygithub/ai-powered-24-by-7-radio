"""main.py — entrypoint for the autonomous 24/7 AI Radio Station.

Run:
    python main.py
"""

import os
import sys
import threading
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


from radio import run_radio_loop

if __name__ == "__main__":
    _start_dummy_health_server()
    sys.exit(run_radio_loop())
