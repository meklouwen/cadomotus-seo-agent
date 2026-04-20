"""Cadomotus SEO Agent — Docker entrypoint.

Gmail en Shopify draaien via n8n webhook proxies — geen Google OAuth nodig.
GSC is optioneel (als token beschikbaar is).
"""

import logging
import os
import sys
import threading
import time

import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("cadomotus-main")

log.info("=== Cadomotus SEO Agent STARTUP ===")
log.info("Python: %s", sys.version.split()[0])
log.info("MODE: %s", os.getenv("MODE", "not set"))
log.info("TZ: %s", os.getenv("TZ", "not set"))
log.info("ANTHROPIC_API_KEY set: %s", bool(os.getenv("ANTHROPIC_API_KEY")))

# Veiligheidswaarschuwingen bij startup — leeg betekent niet stuk, maar wel risico.
if not os.getenv("SHOPIFY_PROXY_SECRET", "").strip():
    log.warning("[security] SHOPIFY_PROXY_SECRET is LEEG — n8n webhook is publiek "
                "aanroepbaar als de n8n workflow zelf geen auth-check heeft. "
                "Zet bij voorkeur een random Bearer-token in n8n + Easypanel.")
if not os.getenv("TRIGGER_TOKEN", "").strip():
    log.info("[security] TRIGGER_TOKEN is leeg — handmatige /trigger endpoint is uit. "
             "Cron op vrijdag 07:00 werkt sowieso.")
if not os.getenv("GOOGLE_TOKEN_JSON", "").strip() and not os.getenv("GOOGLE_TOKEN_PATH"):
    log.info("[oauth] Geen GOOGLE_TOKEN_JSON env-var en geen TOKEN_PATH — GSC werkt "
             "alleen als /data/token.json al bestaat (mounted volume met eerder token).")

# Health + manual trigger server
try:
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    import json
    from datetime import datetime

    TRIGGER_TOKEN = os.getenv("TRIGGER_TOKEN", "")

    _trigger_lock = threading.Lock()
    _trigger_running = False

    def _do_trigger():
        global _trigger_running
        with _trigger_lock:
            if _trigger_running:
                return False, "already running"
            _trigger_running = True
        try:
            log.info("[trigger] Manual weekly_report fired")
            from agent import weekly_report
            weekly_report()
            log.info("[trigger] klaar")
            return True, "completed"
        except Exception as e:
            log.exception("[trigger] FOUT: %s", e)
            return False, str(e)
        finally:
            with _trigger_lock:
                _trigger_running = False

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/trigger":
                qs = parse_qs(parsed.query)
                token = qs.get("token", [""])[0]
                if not TRIGGER_TOKEN or token != TRIGGER_TOKEN:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "invalid or missing token"}).encode())
                    return
                # Start in background, return 202 direct (response binnen seconden, run duurt minuten)
                threading.Thread(target=_do_trigger, daemon=True).start()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"triggered": True, "note": "weekly_report draait nu in background, mail komt binnen ~1-3 min"}).encode())
                return

            # Default: health
            body = json.dumps({
                "status": "running",
                "time": str(datetime.now()),
                "trigger_running": _trigger_running,
                "trigger_endpoint_enabled": bool(TRIGGER_TOKEN),
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        def log_message(self, *args):
            pass

    def _serve():
        port = int(os.getenv("PORT", "8080"))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        log.info("[health] Listening on :%d", port)
        if TRIGGER_TOKEN:
            log.info("[trigger] Endpoint enabled: GET /trigger?token=<TRIGGER_TOKEN>")
        server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    log.info("[health] Thread gestart")
except Exception as e:
    log.exception("[health] FOUT: %s", e)

# Data-dir voor token, credentials en report-archief.
# In Easypanel hoort hier een volume gemount te zijn. Lokaal (zonder /data
# write-access) gebruik je de paden uit env-vars — we proberen alleen die te
# maken, niet hard /data. Een crash hier zou de hele container neerhalen.
for _path in {
    os.path.dirname(os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")),
    os.path.dirname(os.getenv("GOOGLE_CREDENTIALS_PATH", "/data/google_credentials.json")),
    os.getenv("REPORTS_DIR", "/data/logs/reports"),
}:
    if not _path:
        continue
    try:
        os.makedirs(_path, exist_ok=True)
        log.info("[init] dir ok: %s", _path)
    except OSError as e:
        log.warning("[init] kon dir %s niet aanmaken: %s — sla over", _path, e)


def run_weekly_report():
    """Genereer en verstuur het wekelijkse rapport."""
    log.info("[cron] Wekelijks rapport starten...")
    try:
        from agent import weekly_report
        weekly_report()
        log.info("[cron] Rapport verzonden.")
    except Exception as e:
        log.exception("[cron] FOUT: %s", e)


def run_reply_watcher():
    """Poll n8n elke 5 minuten op replies van Diederik."""
    log.info("[watcher] Reply watcher gestart.")
    from agent import _check_and_handle_replies, load_system_prompt
    system_prompt = load_system_prompt()

    while True:
        try:
            _check_and_handle_replies(system_prompt)
        except Exception as e:
            log.exception("[watcher] FOUT: %s", e)

        interval = int(os.getenv("REPLY_POLL_INTERVAL", 300))
        log.info("[watcher] Volgende check over %ds...", interval)
        time.sleep(interval)


def main():
    mode = os.getenv("MODE", "full")
    log.info("[main] Mode: %s", mode)

    if mode in ("full", "watch"):
        if mode == "full":
            # Cron: vrijdag 07:00 Europe/Amsterdam (TZ wordt in Dockerfile gezet).
            schedule.every().friday.at("07:00").do(run_weekly_report)
            log.info("[cron] Wekelijks rapport gepland: elke vrijdag 07:00 %s",
                     os.getenv("TZ", "lokale tijd"))

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
        log.warning("[main] Onbekende mode: %s. Idle...", mode)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
