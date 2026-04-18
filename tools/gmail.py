"""Gmail tools via n8n webhook proxy — geen Google OAuth nodig."""

import os
import json
import requests

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
                            "field": {"type": "string", "enum": ["meta_title", "meta_description"], "description": "Welk SEO-veld wordt aangepast"},
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
                            "primary_keyword": {"type": "string", "description": "Primair zoekwoord voor deze pagina"}
                        },
                        "required": ["id", "url", "field", "resource_id", "proposed_values"]
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
        is_preview = input_data.get("preview", True)
        subject = input_data.get("subject", "")

        if is_preview:
            to_addr = REPORT_CC
            cc_addr = ""
            subject = f"[PREVIEW] {subject}" if not subject.startswith("[PREVIEW]") else subject
        else:
            to_addr = REPORT_TO
            cc_addr = REPORT_CC

        payload = {
            "to": to_addr,
            "cc": cc_addr,
            "date": input_data.get("date", ""),
            "subject": subject,
            "performance": input_data.get("performance", {}),
            "fixes": input_data.get("fixes", []),
            "text_summary": input_data.get("text_summary", ""),
            "new_products_html": input_data.get("new_products_html", ""),
            "extra_html": input_data.get("extra_html", ""),
            "preview": is_preview,
        }
        resp = requests.post(N8N_REPORT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        return json.dumps({"sent_to": to_addr, "preview": is_preview, "response": resp.json()})

    elif name == "gmail_check_replies":
        payload = {
            "max_results": input_data.get("max_results", 20)
        }
        resp = requests.post(N8N_REPLIES_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data.get("replies", []), indent=2)

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
