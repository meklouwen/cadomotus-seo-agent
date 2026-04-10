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
REPORT_TO = os.getenv("REPORT_TO", "diederik@cadomotus.com")
REPORT_CC = os.getenv("REPORT_CC", "maarten@thesystem.nl")

GMAIL_TOOLS = [
    {
        "name": "gmail_send_report",
        "description": (
            "Stuur het wekelijkse SEO-rapport naar Diederik met klikbare knoppen. "
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
                    "description": "Lijst van voorgestelde fixes met knoppen",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Uniek ID voor deze fix"},
                            "url": {"type": "string"},
                            "field": {"type": "string", "description": "meta_title of meta_description"},
                            "current_value": {"type": "string"},
                            "proposed_value": {"type": "string"},
                            "position": {"type": "number"},
                            "ctr": {"type": "number"},
                            "impressions": {"type": "integer"},
                            "estimated_clicks": {"type": "integer"},
                            "resource_id": {"type": "string", "description": "Shopify GID"},
                            "mutation": {"type": "string", "description": "GraphQL mutation"},
                            "variables": {"type": "object"}
                        }
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
                    "default": 5
                }
            }
        }
    }
]


def execute_gmail_tool(name: str, input_data: dict) -> str:
    if name == "gmail_send_report":
        payload = {
            "to": REPORT_TO,
            "cc": REPORT_CC,
            "date": input_data.get("date", ""),
            "subject": input_data.get("subject", ""),
            "performance": input_data.get("performance", {}),
            "fixes": input_data.get("fixes", []),
            "text_summary": input_data.get("text_summary", ""),
            "new_products_html": input_data.get("new_products_html", ""),
            "extra_html": input_data.get("extra_html", ""),
        }
        resp = requests.post(N8N_REPORT_URL, json=payload, timeout=30)
        resp.raise_for_status()
        return json.dumps(resp.json())

    elif name == "gmail_check_replies":
        payload = {
            "max_results": input_data.get("max_results", 5)
        }
        resp = requests.post(N8N_REPLIES_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data.get("replies", []), indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})
