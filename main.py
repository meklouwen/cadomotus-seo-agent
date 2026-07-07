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
    DATA_DIR = os.getenv("DATA_DIR", "/data")

    _trigger_lock = threading.Lock()
    _trigger_running = False

    # Bulk audit state (alt-tags + links)
    _audit_lock = threading.Lock()
    _audit_running = False
    _audit_status: dict = {"status": "idle"}

    # Full SEO audit state
    _full_audit_lock = threading.Lock()
    _full_audit_running = False
    _full_audit_status: dict = {"status": "idle"}

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

    def _do_full_audit():
        global _full_audit_running
        with _full_audit_lock:
            if _full_audit_running:
                return
            _full_audit_running = True
        try:
            log.info("[full] Volledige SEO-audit gestart in achtergrond-thread")
            from tools.full_seo_crawl import run_full_seo_audit
            run_full_seo_audit(data_dir=DATA_DIR, status_ref=_full_audit_status)
            log.info("[full] Volledige SEO-audit klaar")
        except Exception as e:
            log.exception("[full] FOUT: %s", e)
            _full_audit_status.update({"status": "error", "error": str(e)})
        finally:
            with _full_audit_lock:
                _full_audit_running = False

    def _do_bulk_audit():
        global _audit_running
        with _audit_lock:
            if _audit_running:
                return
            _audit_running = True
        try:
            log.info("[bulk] Bulk audit gestart in achtergrond-thread")
            from tools.bulk_audit import run_bulk_audit
            run_bulk_audit(data_dir=DATA_DIR, status_ref=_audit_status)
            log.info("[bulk] Bulk audit klaar")
        except Exception as e:
            log.exception("[bulk] FOUT: %s", e)
            _audit_status.update({"status": "error", "error": str(e)})
        finally:
            with _audit_lock:
                _audit_running = False

    def _check_token(qs: dict) -> bool:
        token = qs.get("token", [""])[0]
        return bool(TRIGGER_TOKEN) and token == TRIGGER_TOKEN

    def _send_json(handler, status: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def _send_html(handler, content: bytes):
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)

    _TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "review.html")

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            # ── /trigger ─────────────────────────────────────────────
            if parsed.path == "/trigger":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                threading.Thread(target=_do_trigger, daemon=True).start()
                _send_json(self, 202, {"triggered": True,
                    "note": "weekly_report draait in background"})
                return

            # ── /review  (HTML pagina) ────────────────────────────────
            if parsed.path == "/review":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                try:
                    with open(_TEMPLATE_PATH, "rb") as f:
                        _send_html(self, f.read())
                except FileNotFoundError:
                    _send_json(self, 500, {"error": "review.html niet gevonden"})
                return

            # ── /review/data  (JSON audit resultaten) ────────────────
            if parsed.path == "/review/data":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                audit_path = os.path.join(DATA_DIR, "bulk_audit.json")
                if not os.path.exists(audit_path):
                    _send_json(self, 404, {"error": "Audit-data nog niet beschikbaar. "
                        "Trigger eerst via GET /review/audit?token=..."})
                    return
                try:
                    with open(audit_path, "rb") as f:
                        raw = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as e:
                    _send_json(self, 500, {"error": str(e)})
                return

            # ── /review/audit  (start bulk crawl) ────────────────────
            if parsed.path == "/review/audit":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                with _audit_lock:
                    if _audit_running:
                        _send_json(self, 409, {"error": "Audit al bezig",
                            "status": _audit_status})
                        return
                threading.Thread(target=_do_bulk_audit, daemon=True).start()
                _send_json(self, 202, {"triggered": True,
                    "note": "Bulk audit gestart (~15-20 min). Poll /review/status voor voortgang."})
                return

            # ── /review/status  (voortgang, geen token vereist) ──────
            if parsed.path == "/review/status":
                _send_json(self, 200, {**_audit_status, "audit_running": _audit_running})
                return

            # ── /full/audit  (start volledige SEO-crawl) ─────────────
            if parsed.path == "/full/audit":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                with _full_audit_lock:
                    if _full_audit_running:
                        _send_json(self, 409, {"error": "Volledige audit al bezig",
                            "status": _full_audit_status})
                        return
                threading.Thread(target=_do_full_audit, daemon=True).start()
                _send_json(self, 202, {"triggered": True,
                    "note": "Volledige SEO-audit gestart (~30-45 min). Poll /full/status."})
                return

            # ── /full/status  (geen token vereist) ────────────────────
            if parsed.path == "/full/status":
                _send_json(self, 200, {**_full_audit_status, "running": _full_audit_running})
                return

            # ── /full/data  (volledig audit JSON) ─────────────────────
            if parsed.path == "/full/data":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                audit_path = os.path.join(DATA_DIR, "full_audit.json")
                if not os.path.exists(audit_path):
                    _send_json(self, 404, {"error": "Nog geen volledige audit beschikbaar. "
                        "Trigger via GET /full/audit?token=..."})
                    return
                try:
                    with open(audit_path, "rb") as f:
                        raw = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception as e:
                    _send_json(self, 500, {"error": str(e)})
                return

            # ── / health ─────────────────────────────────────────────
            _send_json(self, 200, {
                "status": "running",
                "time": str(datetime.now()),
                "trigger_running": _trigger_running,
                "audit_running": _audit_running,
                "trigger_endpoint_enabled": bool(TRIGGER_TOKEN),
            })

        def do_POST(self):
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            # ── /review/apply  (Shopify alt-fix uitvoeren) ───────────
            if parsed.path == "/review/apply":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception as e:
                    _send_json(self, 400, {"error": f"Ongeldige JSON body: {e}"})
                    return

                selected_alts = body.get("selected_alts", [])
                applied = 0
                errors = []

                if selected_alts:
                    from tools.shopify import execute_shopify_tool
                    for item in selected_alts:
                        try:
                            result_str = execute_shopify_tool("shopify_update_image_alt", {
                                "product_id": item["product_id"],
                                "image_id":   item["image_id"],
                                "alt_text":   (item.get("alt_text") or item.get("suggested_alt") or "").strip(),
                            })
                            result = json.loads(result_str)
                            if "error" in result:
                                errors.append({"image_id": item["image_id"], "error": result["error"]})
                            else:
                                applied += 1
                        except Exception as e:
                            errors.append({"image_id": item.get("image_id"), "error": str(e)})

                    # Persisteer applied status in bulk_audit.json
                    audit_path = os.path.join(DATA_DIR, "bulk_audit.json")
                    if os.path.exists(audit_path):
                        try:
                            with open(audit_path, "r", encoding="utf-8") as f:
                                audit_data = json.load(f)
                            applied_ids = {item["image_id"] for item in selected_alts
                                          if item["image_id"] not in [e.get("image_id") for e in errors]}
                            for img in audit_data.get("missing_alt", []):
                                if img.get("image_id") in applied_ids:
                                    img["status"] = "applied"
                            with open(audit_path, "w", encoding="utf-8") as f:
                                json.dump(audit_data, f, indent=2, ensure_ascii=False)
                        except Exception as e:
                            log.warning("[bulk] Kon audit.json niet updaten: %s", e)

                log.info("[bulk] Apply: %d alt-tags bijgewerkt, %d fouten", applied, len(errors))
                _send_json(self, 200, {
                    "applied": applied,
                    "errors":  errors,
                    "note":    f"{applied} alt-tags bijgewerkt in Shopify",
                })
                return

            # ── /full/upload  (upload lokaal gegenereerde audit-data) ─
            if parsed.path == "/full/upload":
                if not _check_token(qs):
                    _send_json(self, 401, {"error": "invalid or missing token"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length)
                    data = json.loads(raw.decode("utf-8"))
                    audit_path = os.path.join(DATA_DIR, "full_audit.json")
                    with open(audit_path, "wb") as f:
                        f.write(raw)
                    # Update _full_audit_status zodat /full/status correct is
                    _full_audit_status.update({
                        "status": "done",
                        "phase": "done",
                        "crawled_at": data.get("crawled_at", ""),
                        "total_issues": data.get("total_issues", 0),
                        "pages_crawled": data.get("pages_crawled", 0),
                        "summary_by_type": data.get("summary_by_type", {}),
                    })
                    log.info("[full] Upload ontvangen: %d issues, %d paginas",
                             data.get("total_issues", 0), data.get("pages_crawled", 0))
                    _send_json(self, 200, {
                        "ok": True,
                        "total_issues": data.get("total_issues", 0),
                        "pages_crawled": data.get("pages_crawled", 0),
                    })
                except Exception as e:
                    _send_json(self, 400, {"error": str(e)})
                return

            _send_json(self, 404, {"error": "Route niet gevonden"})

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
