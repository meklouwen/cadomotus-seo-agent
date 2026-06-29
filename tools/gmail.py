"""Gmail tools via n8n webhook proxy — geen Google OAuth nodig."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .validation import validate_fixes

log = logging.getLogger("cadomotus-agent")

# Lokale kopie van elke verzonden preview voor post-mortem inspectie. Niet in git
# (zie .gitignore advies). Als de directory niet kan worden aangemaakt, wordt
# de save silently overgeslagen — logs blijven dan de enige bron.
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(Path(__file__).resolve().parents[1] / "logs" / "reports")))

# Voorstel-historiek: bijgehouden op fly.io volume (/data) zodat de agent
# per week weet welke pagina's al zijn voorgesteld.
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
HISTORY_FILE = DATA_DIR / "proposal_history.json"
HISTORY_COOLDOWN_WEEKS = int(os.getenv("PROPOSAL_COOLDOWN_WEEKS", "4"))


def _load_history() -> dict:
    """Laad voorstel-historiek vanuit /data/proposal_history.json."""
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("proposal_history laden mislukt: %s", e)
    return {"proposals": []}


def _save_proposal_history(fixes: list, report_date: str) -> None:
    """Sla voorgestelde URLs op in de historiek na een succesvolle verzending."""
    try:
        history = _load_history()
        now = datetime.now(timezone.utc).isoformat()
        for fix in fixes:
            url = fix.get("url", "")
            field = fix.get("field", "")
            if url:
                history["proposals"].append({
                    "url": url,
                    "field": field,
                    "proposed_at": now,
                    "report_date": report_date,
                })
        # Bewaar alleen de laatste 26 weken (½ jaar) — daarna vervalt de historiek
        cutoff_count = 26 * 25  # max 25 fixes × 26 weken = 650 entries
        history["proposals"] = history["proposals"][-cutoff_count:]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("proposal_history opgeslagen: %d entries totaal", len(history["proposals"]))
    except Exception as e:
        log.warning("proposal_history opslaan mislukt: %s", e)

N8N_REPORT_URL = os.getenv(
    "N8N_REPORT_URL",
    "https://maartenklouwen.app.n8n.cloud/webhook/cadomotus-seo-report"
)
N8N_REPLIES_URL = os.getenv(
    "N8N_REPLIES_URL",
    "https://maartenklouwen.app.n8n.cloud/webhook/cadomotus-seo-replies"
)
N8N_REPLY_THREAD_URL = os.getenv(
    "N8N_REPLY_THREAD_URL",
    "https://maartenklouwen.app.n8n.cloud/webhook/cadomotus-seo-reply-thread"
)
REPORT_TO = os.getenv("REPORT_TO", "diederik@cadomotus.com")
REPORT_CC = os.getenv("REPORT_CC", "maarten@thesystem.nl")

GMAIL_TOOLS = [
    {
        "name": "gmail_send_report",
        "description": (
            "Stuur het wekelijkse SEO-rapport. BELANGRIJK: gebruik preview=true voor "
            "de EERSTE versie — die gaat alleen naar maarten@thesystem.nl voor controle. "
            "Pas na expliciete goedkeuring stuur je het rapport met preview=false naar Diederik. "
            "Stuur performance data en fixes mee — de email wordt automatisch "
            "opgemaakt met goedkeur/overslaan knoppen per fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Datum van het rapport (YYYY-MM-DD)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email onderwerp"
                },
                "performance": {
                    "type": "object",
                    "description": "Performance data: clicks, impressions, position, ctr + deltas",
                    "properties": {
                        "clicks": {"type": "integer"},
                        "clicks_delta": {"type": "number"},
                        "impressions": {"type": "integer"},
                        "impressions_delta": {"type": "number"},
                        "position": {"type": "number"},
                        "position_delta": {"type": "number"},
                        "ctr": {"type": "number"},
                        "ctr_delta": {"type": "number"},
                        "alert": {"type": "string"}
                    }
                },
                "fixes": {
                    "type": "array",
                    "description": "Lijst van 20 fixes. Elke fix = 1 pagina met voorstellen voor alle 4 talen. 1 goedkeuring = alle 4 talen bijgewerkt.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Uniek ID voor deze fix"},
                            "url": {"type": "string", "description": "URL van de pagina (primaire EN-URL)"},
                            "field": {
                                "type": "string",
                                "enum": ["meta_title", "meta_description", "image_alt",
                                         "collection_body", "page_body", "product_body"],
                                "description": (
                                    "Wat wordt aangepast. "
                                    "meta_title/meta_description: SEO-velden, meertalig. "
                                    "image_alt: store-wide, één taal. "
                                    "collection_body: collectie-beschrijving. "
                                    "page_body: CMS-pagina body (review per item nodig). "
                                    "product_body: alleen suggestie, niet auto-apply."
                                ),
                            },
                            "resource_id": {"type": "string", "description": "Shopify GID (wordt gebruikt voor alle 4 taal-mutations)"},
                            "resource_type": {"type": "string", "enum": ["product", "collection", "page"], "description": "Type Shopify resource"},
                            "current_values": {
                                "type": "object",
                                "description": "Huidige waarden per taal. Alleen talen waar wat moet veranderen hoeven erin.",
                                "properties": {
                                    "EN": {"type": "string"},
                                    "NL": {"type": "string"},
                                    "DE": {"type": "string"},
                                    "FR": {"type": "string"}
                                }
                            },
                            "proposed_values": {
                                "type": "object",
                                "description": "Voorgestelde nieuwe waarden per taal. Minimaal 2 talen, liefst alle 4.",
                                "properties": {
                                    "EN": {"type": "string"},
                                    "NL": {"type": "string"},
                                    "DE": {"type": "string"},
                                    "FR": {"type": "string"}
                                }
                            },
                            "position": {"type": "number", "description": "GSC positie (primair)"},
                            "ctr": {"type": "number", "description": "GSC CTR (primair)"},
                            "impressions": {"type": "integer", "description": "GSC impressies (primair)"},
                            "estimated_clicks": {"type": "integer", "description": "Geschatte extra clicks/mnd over alle talen"},
                            "primary_keyword": {"type": "string", "description": "Primair zoekwoord voor deze pagina"},
                            "category": {
                                "type": "string",
                                "enum": ["shoe", "bag", "helmet", "inline", "ice", "collection", "page", "blog", "other"],
                                "description": "Categorie van deze pagina — gebruikt voor category-fit validatie."
                            },
                            "product_type": {"type": "string", "description": "Letterlijke Shopify productType (voor audit trail)"}
                        },
                        "required": ["id", "url", "field", "resource_id", "resource_type",
                                     "proposed_values", "category", "primary_keyword"]
                    }
                },
                "text_summary": {
                    "type": "string",
                    "description": "Plain text samenvatting"
                },
                "new_products_html": {
                    "type": "string",
                    "description": "Extra HTML voor nieuwe producten sectie"
                },
                "extra_html": {
                    "type": "string",
                    "description": "Extra HTML content"
                },
                "preview": {
                    "type": "boolean",
                    "description": "Als true (of niet meegegeven): stuur alleen naar maarten@thesystem.nl met [PREVIEW] in subject. Als false: stuur naar Diederik. Default = true voor veiligheid.",
                    "default": True
                }
            },
            "required": ["date", "performance", "fixes"]
        }
    },
    {
        "name": "seo_get_proposal_history",
        "description": (
            "Haal de historiek op van eerder voorgestelde SEO-fixes. "
            "Gebruik dit ALTIJD als eerste stap in het wekelijkse rapport — "
            "pagina's die de afgelopen 4 weken al zijn voorgesteld hebben "
            "een penaltyscore en worden liefst overgeslagen tenzij er echt "
            "geen alternatieven zijn. Zo ziet Diederik elke week vers materiaal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks_back": {
                    "type": "integer",
                    "description": "Hoeveel weken terug om te bekijken (default 8)",
                    "default": 8
                }
            }
        }
    },
    {
        "name": "gmail_check_replies",
        "description": (
            "Check op nieuwe replies van Diederik op SEO-rapport threads. "
            "Geeft ongelezen berichten terug."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "gmail_reply_thread",
        "description": (
            "Reply op een bestaande Gmail thread (bijv. een reply van Diederik op het SEO-rapport). "
            "Houdt de conversation thread intact via Gmail's reply-operation. "
            "Vereist beide: thread_id EN message_id (Gmail message ID — uit gmail_check_replies field 'id'). "
            "Gebruik dit om Diederik's vragen te beantwoorden of voorstellen te bevestigen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Gmail thread ID (uit gmail_check_replies, field 'threadId')"},
                "message_id": {"type": "string", "description": "Gmail message ID (uit gmail_check_replies, field 'id') — VERPLICHT voor reply"},
                "to": {"type": "string", "description": "Email address van ontvanger (meestal diederik@cadomotus.com)"},
                "subject": {"type": "string", "description": "Subject (begin met 'Re: ' als reply)"},
                "body_html": {"type": "string", "description": "HTML body van de reply"},
                "body_text": {"type": "string", "description": "Plain text fallback"}
            },
            "required": ["thread_id", "message_id", "to", "subject", "body_html"]
        }
    }
]


def execute_gmail_tool(name: str, input_data: dict) -> str:
    if name == "gmail_send_report":
        raw_preview = input_data.get("preview", True)
        # Harde boolean-guard: alleen expliciet Python False telt als productie.
        # Strings als "false"/"no"/"" worden als True behandeld (= preview). Dit voorkomt
        # dat een type-coercion (of het model dat "false" als string invult) het rapport
        # per ongeluk naar Diederik stuurt.
        if isinstance(raw_preview, bool):
            is_preview = raw_preview
        else:
            is_preview = True
        subject = input_data.get("subject", "")

        if is_preview:
            to_addr = REPORT_CC
            cc_addr = ""
            subject = f"[PREVIEW] {subject}" if not subject.startswith("[PREVIEW]") else subject
        else:
            to_addr = REPORT_TO
            cc_addr = REPORT_CC

        fixes = input_data.get("fixes", []) or []

        # Pre-flight validatie: blokkeert een slechte preview-mail vóór de n8n POST.
        # Dit is de Python-enforcement bovenop wat het prompt afdwingt.
        validation = validate_fixes(fixes)
        if not validation["valid"]:
            log.warning("VALIDATE_FIXES | invalid | errors=%s", validation["errors"])
            return json.dumps({
                "error": "Pre-flight validatie mislukt — herzie je fixes voor je gmail_send_report opnieuw aanroept.",
                "details": validation["errors"],
                "warnings": validation["warnings"],
                "categories": validation["categories"],
            })
        if validation["warnings"]:
            log.info("VALIDATE_FIXES | ok-with-warnings | %s", validation["warnings"])

        payload = {
            "to": to_addr,
            "cc": cc_addr,
            "date": input_data.get("date", ""),
            "subject": subject,
            "performance": input_data.get("performance", {}),
            "fixes": fixes,
            "text_summary": input_data.get("text_summary", ""),
            "new_products_html": input_data.get("new_products_html", ""),
            "extra_html": input_data.get("extra_html", ""),
            "preview": is_preview,
            "validation_summary": {
                "categories": validation["categories"],
                "count": validation["count"],
                "warnings": validation["warnings"],
            },
        }

        # Sla payload lokaal op voor post-mortem inspectie. Niet-fataal bij falen.
        try:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            mode = "preview" if is_preview else "production"
            out_path = REPORTS_DIR / f"{stamp}-{mode}.json"
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info("REPORT_SAVED | %s", out_path)
        except OSError as e:
            log.warning("REPORT_SAVE_FAILED | %s", e)

        resp = requests.post(N8N_REPORT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        try:
            resp_body = resp.json()
        except ValueError:
            resp_body = {"status": resp.status_code}

        # Sla voor-gestelde URLs op in historiek (alleen bij succesvolle verzending).
        _save_proposal_history(fixes, input_data.get("date", ""))

        return json.dumps({
            "sent_to": to_addr,
            "preview": is_preview,
            "validation": validation,
            "response": resp_body,
        })

    elif name == "gmail_check_replies":
        # Polling-call die elke 5 min draait. Mag NOOIT crashen — als de webhook
        # iets anders dan JSON teruggeeft (lege body, HTML errorpage, 502 van
        # Cloudflare, etc.) loggen we het rustig en doen alsof er geen replies
        # zijn. Een crash hier zou de watcher-loop volgooien met tracebacks.
        payload = {"max_results": input_data.get("max_results", 20)}
        try:
            resp = requests.post(N8N_REPLIES_URL, json=payload, timeout=30)
        except requests.RequestException as e:
            log.warning("gmail_check_replies | netwerkfout: %s", e)
            return "[]"

        if resp.status_code >= 400:
            log.warning("gmail_check_replies | HTTP %d van n8n — geen replies verwerkt",
                        resp.status_code)
            return "[]"

        body = (resp.text or "").strip()
        if not body:
            # Lege body = "geen nieuwe replies" — n8n stuurt dat soms zo terug.
            return "[]"
        try:
            data = resp.json()
        except ValueError:
            log.warning("gmail_check_replies | non-JSON respons (%d bytes): %s …",
                        len(body), body[:120].replace("\n", " "))
            return "[]"

        if isinstance(data, list):
            replies = data
        elif isinstance(data, dict):
            replies = data.get("replies", []) or []
        else:
            replies = []
        return json.dumps(replies, indent=2)

    elif name == "seo_get_proposal_history":
        weeks_back = int(input_data.get("weeks_back", 8))
        history = _load_history()
        proposals = history.get("proposals", [])

        # Bereken hoe lang geleden elk voorstel was gedaan
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(weeks=weeks_back)

        url_counts: dict = {}
        url_last_seen: dict = {}
        url_fields: dict = {}

        for p in proposals:
            try:
                proposed_dt = datetime.fromisoformat(p["proposed_at"].replace("Z", "+00:00"))
            except Exception:
                continue
            if proposed_dt < cutoff:
                continue
            url = p.get("url", "")
            field = p.get("field", "")
            key = f"{url}|{field}"
            url_counts[key] = url_counts.get(key, 0) + 1
            if key not in url_last_seen or proposed_dt > url_last_seen[key]:
                url_last_seen[key] = proposed_dt
            url_fields[key] = (url, field, p.get("report_date", ""))

        recently_proposed = []
        cooldown_cutoff = now - timedelta(weeks=HISTORY_COOLDOWN_WEEKS)
        for key, (url, field, report_date) in url_fields.items():
            last = url_last_seen[key]
            weeks_since = (now - last).days // 7
            in_cooldown = last > cooldown_cutoff
            recently_proposed.append({
                "url": url,
                "field": field,
                "times_proposed": url_counts[key],
                "last_proposed": last.strftime("%Y-%m-%d"),
                "weeks_since_last": weeks_since,
                "in_cooldown": in_cooldown,
            })

        # Sorteer: recentste eerst
        recently_proposed.sort(key=lambda x: x["last_proposed"], reverse=True)

        in_cooldown_count = sum(1 for r in recently_proposed if r["in_cooldown"])
        return json.dumps({
            "recently_proposed": recently_proposed,
            "cooldown_weeks": HISTORY_COOLDOWN_WEEKS,
            "in_cooldown_count": in_cooldown_count,
            "note": (
                f"Pagina's met in_cooldown=true zijn in de afgelopen {HISTORY_COOLDOWN_WEEKS} weken "
                "al voorgesteld. Sla ze over voor nieuwe fixes — kies andere pagina's. "
                "Alleen als je de volledige catalogus hebt uitgeput mag je er één terugpakken."
            ),
        })

    elif name == "gmail_reply_thread":
        payload = {
            "thread_id": input_data["thread_id"],
            "message_id": input_data["message_id"],  # Gmail messageId — VERPLICHT
            "to": input_data["to"],
            "subject": input_data["subject"],
            "body_html": input_data["body_html"],
            "body_text": input_data.get("body_text", ""),
        }
        resp = requests.post(N8N_REPLY_THREAD_URL, json=payload, timeout=30)
        resp.raise_for_status()
        return json.dumps({"sent": True, "to": payload["to"], "thread_id": payload["thread_id"]})

    return json.dumps({"error": f"Unknown tool: {name}"})
