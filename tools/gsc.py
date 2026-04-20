"""Google Search Console tools voor de Cadomotus SEO agent."""

import json
import logging
import os
from datetime import datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools._google_auth import get_google_credentials

log = logging.getLogger("cadomotus-agent")

SITE_URL = os.getenv("GOOGLE_SITE_URL", "sc-domain:cadomotus.com")

GSC_TOOLS = [
    {
        "name": "gsc_search_analytics",
        "description": (
            "Haal zoekprestaties op uit Google Search Console. "
            "Geeft clicks, impressies, CTR en positie per pagina of query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Startdatum YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "Einddatum YYYY-MM-DD"
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["page", "query", "date", "country", "device"]},
                    "description": "Dimensies om op te splitsen"
                },
                "row_limit": {
                    "type": "integer",
                    "description": "Max aantal rijen (standaard 100)",
                    "default": 100
                },
                "url_filter": {
                    "type": "string",
                    "description": "Filter op specifieke URL (contains)"
                },
                "query_filter": {
                    "type": "string",
                    "description": "Filter op specifieke zoekterm (contains)"
                }
            },
            "required": ["start_date", "end_date", "dimensions"]
        }
    },
    {
        "name": "gsc_quick_wins",
        "description": (
            "Vind de top 20 pagina's die bijna bovenaan staan maar te weinig clicks krijgen. "
            "Positie 4-15 met CTR onder 3%. Dit zijn de makkelijkste SEO-verbeteringen — "
            "gebruik deze data om sterke fixes te genereren met geschatte impact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Aantal dagen terugkijken (standaard 30)",
                    "default": 30
                },
                "min_impressions": {
                    "type": "integer",
                    "description": "Minimum impressies (standaard 20)",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "gsc_index_status",
        "description": "Check of een specifieke URL geïndexeerd is door Google.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "De volledige URL om te checken"
                }
            },
            "required": ["url"]
        }
    }
]


def _get_service():
    creds = get_google_credentials()
    return build("searchconsole", "v1", credentials=creds)


def execute_gsc_tool(name: str, input_data: dict) -> str:
    try:
        service = _get_service()
    except Exception as e:
        log.warning("GSC_UNAVAILABLE | %s", str(e)[:160])
        return json.dumps({
            "error": "GSC niet gekoppeld",
            "detail": str(e),
            "rows": [],
            "wins": [],
            "note": "Rapport draait door zonder GSC-data — gebruik shopify_get_products, "
                    "shopify_get_collections en shopify_get_translations als bron.",
        })

    try:
        return _execute_gsc(service, name, input_data)
    except HttpError as e:
        log.warning("GSC_HTTP_ERROR | status=%s | %s", getattr(e, "status_code", "?"), str(e)[:200])
        return json.dumps({
            "error": "GSC API-fout",
            "status": getattr(e, "status_code", None),
            "detail": str(e)[:300],
            "rows": [],
            "wins": [],
            "note": "GSC-call is mislukt maar het rapport moet doorlopen op andere bronnen.",
        })
    except Exception as e:
        log.exception("GSC_UNEXPECTED | %s", e)
        return json.dumps({
            "error": "Onverwachte GSC-fout",
            "detail": str(e)[:300],
            "rows": [],
            "wins": [],
        })


def _execute_gsc(service, name: str, input_data: dict) -> str:
    if name == "gsc_search_analytics":
        body = {
            "startDate": input_data["start_date"],
            "endDate": input_data["end_date"],
            "dimensions": input_data["dimensions"],
            "rowLimit": input_data.get("row_limit", 100),
        }
        filters = []
        if input_data.get("url_filter"):
            filters.append({
                "dimension": "page",
                "operator": "contains",
                "expression": input_data["url_filter"]
            })
        if input_data.get("query_filter"):
            filters.append({
                "dimension": "query",
                "operator": "contains",
                "expression": input_data["query_filter"]
            })
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]

        result = service.searchanalytics().query(
            siteUrl=SITE_URL, body=body
        ).execute()
        return json.dumps(result.get("rows", []), indent=2)

    elif name == "gsc_quick_wins":
        days = input_data.get("days", 30)
        min_imp = input_data.get("min_impressions", 20)
        end = datetime.now() - timedelta(days=1)
        start = end - timedelta(days=days)

        body = {
            "startDate": start.strftime("%Y-%m-%d"),
            "endDate": end.strftime("%Y-%m-%d"),
            "dimensions": ["page", "query"],
            "rowLimit": 500,
        }
        result = service.searchanalytics().query(
            siteUrl=SITE_URL, body=body
        ).execute()

        wins = []
        for row in result.get("rows", []):
            pos = row.get("position", 0)
            ctr = row.get("ctr", 0)
            imp = row.get("impressions", 0)
            if 4 <= pos <= 15 and ctr < 0.03 and imp >= min_imp:
                target_ctr = 0.08 if pos <= 7 else 0.05
                extra_clicks = int(imp * (target_ctr - ctr))
                wins.append({
                    "page": row["keys"][0],
                    "query": row["keys"][1],
                    "position": round(pos, 1),
                    "ctr": round(ctr * 100, 2),
                    "impressions": imp,
                    "estimated_extra_clicks": extra_clicks
                })

        wins.sort(key=lambda x: x["estimated_extra_clicks"], reverse=True)
        return json.dumps(wins[:20], indent=2)

    elif name == "gsc_index_status":
        result = service.urlInspection().index().inspect(body={
            "inspectionUrl": input_data["url"],
            "siteUrl": SITE_URL,
        }).execute()
        inspection = result.get("inspectionResult", {})
        index_status = inspection.get("indexStatusResult", {})
        return json.dumps({
            "verdict": index_status.get("verdict"),
            "coverageState": index_status.get("coverageState"),
            "lastCrawlTime": index_status.get("lastCrawlTime"),
            "crawledAs": index_status.get("crawledAs"),
        }, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})
