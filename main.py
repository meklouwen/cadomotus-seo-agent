"""Cadomotus SEO Agent — single entrypoint voor Docker.

Start health check server + reply watcher + cron scheduler.
"""

import os
import sys
import time
import threading
import subprocess
from datetime import datetime
from pathlib import Path

# Health check server eerst — zodat Easypanel ziet dat we draaien
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        token_exists = os.path.exists(
            os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")
        )
        body = json.dumps({
            "status": "running",
            "service": "cadomotus-seo-agent",
            "mode": os.getenv("MODE", "full"),
            "google_auth": "ok" if token_exists else "waiting_for_auth",
            "timestamp": datetime.now().isoformat(),
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[health] Server op poort {port}", flush=True)
    server.serve_forever()


def wait_for_token():
    """Wacht tot Google OAuth2 token beschikbaar is."""
    token_path = os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")
    while not os.path.exists(token_path):
        print(
            f"[auth] Google token niet gevonden op {token_path} — wacht 60s.\n"
            f"[auth] Voer auth uit: docker exec <container> python agent.py --auth",
            flush=True,
        )
        time.sleep(60)
    print("[auth] Google token gevonden.", flush=True)


def run_reply_watcher():
    """Start de reply watcher (blokkerend)."""
    wait_for_token()
    print("[watcher] Reply watcher starten...", flush=True)
    try:
        # Import hier zodat module-level imports niet crashen bij startup
        from agent import watch_replies
        watch_replies()
    except Exception as e:
        print(f"[watcher] FOUT: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # Blijf draaien, probeer opnieuw na 60s
        time.sleep(60)
        run_reply_watcher()


def run_cron_scheduler():
    """Simpele cron: vrijdag 07:00 het wekelijkse rapport."""
    import schedule

    def run_report():
        print("[cron] Wekelijks rapport starten...", flush=True)
        try:
            subprocess.run(
                [sys.executable, "agent.py", "--weekly-report"],
                timeout=300,
            )
            print("[cron] Rapport verzonden.", flush=True)
        except Exception as e:
            print(f"[cron] FOUT: {e}", flush=True)

    schedule.every().friday.at("07:00").do(run_report)
    print("[cron] Wekelijks rapport gepland: elke vrijdag 07:00", flush=True)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    print("=== Cadomotus SEO Agent ===", flush=True)
    print(f"Mode: {os.getenv('MODE', 'full')}", flush=True)
    print(f"Python: {sys.version}", flush=True)

    # Zorg dat /data bestaat
    os.makedirs("/data", exist_ok=True)

    mode = os.getenv("MODE", "full")

    # Health check altijd starten
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    if mode == "auth":
        print("[auth] Start OAuth2 flow...", flush=True)
        subprocess.run([sys.executable, "agent.py", "--auth"])
        print("[auth] Klaar. Container blijft draaien.", flush=True)
        # Blijf draaien voor health check
        while True:
            time.sleep(3600)

    elif mode == "report":
        wait_for_token()
        subprocess.run([sys.executable, "agent.py", "--weekly-report"])

    elif mode in ("full", "watch"):
        if mode == "full":
            # Cron scheduler in aparte thread
            cron_thread = threading.Thread(target=run_cron_scheduler, daemon=True)
            cron_thread.start()

        # Reply watcher in main thread (blokkerend)
        run_reply_watcher()

    else:
        print(f"[error] Onbekende mode: {mode}", flush=True)
        # Blijf draaien voor health check
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
