"""Cadomotus SEO Agent — Docker entrypoint."""

import sys
import os
import time
import threading
import traceback

print("=== Cadomotus SEO Agent STARTUP ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)
print(f"Files: {os.listdir('.')}", flush=True)
print(f"MODE: {os.getenv('MODE', 'not set')}", flush=True)
print(f"ANTHROPIC_API_KEY set: {bool(os.getenv('ANTHROPIC_API_KEY'))}", flush=True)

# Health check server — start EERST
try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    from datetime import datetime

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "running", "time": str(datetime.now())})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        def log_message(self, *args):
            pass

    def _serve():
        port = int(os.getenv("PORT", "8080"))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"[health] Listening on :{port}", flush=True)
        server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    print("[health] Thread gestart", flush=True)
except Exception as e:
    print(f"[health] FOUT: {e}", flush=True)
    traceback.print_exc()

# Data dir
try:
    os.makedirs("/data", exist_ok=True)
    print("[data] /data dir ok", flush=True)
except Exception as e:
    print(f"[data] Kan /data niet aanmaken: {e}", flush=True)

# Main loop — blijf gewoon draaien
print("[main] Agent actief. Wacht op Google token...", flush=True)

token_path = os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")

while True:
    if os.path.exists(token_path):
        print("[main] Token gevonden! Agent tools laden...", flush=True)
        try:
            from agent import watch_replies
            watch_replies()
        except Exception as e:
            print(f"[main] Agent FOUT: {e}", flush=True)
            traceback.print_exc()
            time.sleep(60)
    else:
        print(f"[main] Wacht op token: {token_path}", flush=True)
        time.sleep(60)
