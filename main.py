"""Cadomotus SEO Agent — Docker entrypoint.

Gmail en Shopify draaien via n8n webhook proxies — geen Google OAuth nodig.
GSC is optioneel (als token beschikbaar is).
"""

import sys
import os
import time
import threading
import traceback
import schedule

print("=== Cadomotus SEO Agent STARTUP ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"MODE: {os.getenv('MODE', 'not set')}", flush=True)
print(f"ANTHROPIC_API_KEY set: {bool(os.getenv('ANTHROPIC_API_KEY'))}", flush=True)

# Health check server
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
os.makedirs("/data", exist_ok=True)


def run_weekly_report():
    """Genereer en verstuur het wekelijkse rapport."""
    print("[cron] Wekelijks rapport starten...", flush=True)
    try:
        from agent import weekly_report
        weekly_report()
        print("[cron] Rapport verzonden.", flush=True)
    except Exception as e:
        print(f"[cron] FOUT: {e}", flush=True)
        traceback.print_exc()


def run_reply_watcher():
    """Poll n8n elke 5 minuten op replies van Diederik."""
    print("[watcher] Reply watcher gestart.", flush=True)
    from agent import _check_and_handle_replies, load_system_prompt
    system_prompt = load_system_prompt()

    while True:
        try:
            _check_and_handle_replies(system_prompt)
        except Exception as e:
            print(f"[watcher] FOUT: {e}", flush=True)
            traceback.print_exc()

        interval = int(os.getenv("REPLY_POLL_INTERVAL", 300))
        print(f"[watcher] Volgende check over {interval}s...", flush=True)
        time.sleep(interval)


def main():
    mode = os.getenv("MODE", "full")
    print(f"[main] Mode: {mode}", flush=True)

    if mode in ("full", "watch"):
        if mode == "full":
            # Cron: vrijdag 07:00
            schedule.every().friday.at("07:00").do(run_weekly_report)
            print("[cron] Wekelijks rapport gepland: elke vrijdag 07:00", flush=True)

            # Cron checker in aparte thread
            def cron_loop():
                while True:
                    schedule.run_pending()
                    time.sleep(60)
            cron_thread = threading.Thread(target=cron_loop, daemon=True)
            cron_thread.start()

        # Reply watcher in main thread
        run_reply_watcher()

    elif mode == "report":
        run_weekly_report()

    else:
        print(f"[main] Onbekende mode: {mode}. Idle...", flush=True)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
