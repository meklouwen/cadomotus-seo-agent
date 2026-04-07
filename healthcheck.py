"""Simpele HTTP health check server voor Easypanel."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from datetime import datetime


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        token_exists = os.path.exists(
            os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")
        )
        body = json.dumps({
            "status": "running",
            "service": "cadomotus-seo-agent",
            "google_auth": "ok" if token_exists else "waiting",
            "timestamp": datetime.now().isoformat(),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass  # Geen spam in logs


def start_health_server(port=8080):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health check server op poort {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    start_health_server()
