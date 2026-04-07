"""PageSpeed Insights tool — gratis Core Web Vitals data."""

import json
import requests

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

PAGESPEED_TOOLS = [
    {
        "name": "pagespeed_check",
        "description": (
            "Check Core Web Vitals (LCP, CLS, INP) voor een URL via Google PageSpeed Insights. "
            "Gratis API, geen key nodig. Slechte scores = ranking penalty."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "De volledige URL om te checken"
                },
                "strategy": {
                    "type": "string",
                    "enum": ["mobile", "desktop"],
                    "default": "mobile",
                    "description": "Mobile of desktop (Google rankt op mobile-first)"
                }
            },
            "required": ["url"]
        }
    }
]


def execute_pagespeed_tool(name: str, input_data: dict) -> str:
    if name != "pagespeed_check":
        return json.dumps({"error": f"Unknown tool: {name}"})

    url = input_data["url"]
    strategy = input_data.get("strategy", "mobile")

    resp = requests.get(API_URL, params={
        "url": url,
        "strategy": strategy,
        "category": "performance",
    }, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # Extract de belangrijkste metrics
    lhr = data.get("lighthouseResult", {})
    audits = lhr.get("audits", {})
    categories = lhr.get("categories", {})

    perf_score = categories.get("performance", {}).get("score")
    if perf_score is not None:
        perf_score = int(perf_score * 100)

    def _metric(audit_key):
        audit = audits.get(audit_key, {})
        return {
            "value": audit.get("displayValue", "n/a"),
            "score": audit.get("score"),
            "numeric": audit.get("numericValue"),
        }

    result = {
        "url": url,
        "strategy": strategy,
        "performance_score": perf_score,
        "metrics": {
            "LCP": _metric("largest-contentful-paint"),
            "CLS": _metric("cumulative-layout-shift"),
            "INP": _metric("interaction-to-next-paint"),
            "FCP": _metric("first-contentful-paint"),
            "TBT": _metric("total-blocking-time"),
            "Speed_Index": _metric("speed-index"),
        }
    }
    return json.dumps(result, indent=2)
