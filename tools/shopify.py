"""Shopify GraphQL tools voor de Cadomotus SEO agent."""

import hashlib
import json
import logging
import os
import time
from functools import wraps

import requests

log = logging.getLogger("cadomotus-agent")

# Shopify via n8n webhook proxy (de directe token auth gaat via n8n)
SHOPIFY_PROXY_URL = os.getenv(
    "SHOPIFY_PROXY_URL",
    "https://maartenklouwen.app.n8n.cloud/webhook/cadomotus-shopify"
)
# Optionele shared secret die n8n kan valideren (Authorization: Bearer ...).
# Als leeg: geen auth (zelfde gedrag als voorheen — auth moet dan IP-allowlist zijn).
SHOPIFY_PROXY_SECRET = os.getenv("SHOPIFY_PROXY_SECRET", "").strip()

# DRY_RUN: als true wordt GEEN echte mutation uitgevoerd, alleen payload teruggegeven.
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")

# Lengte-grenzen voor SEO-velden. Warn = log-only, fail = mutation geweigerd.
META_TITLE_IDEAL = (50, 60)
META_TITLE_HARD = (40, 70)
META_DESC_IDEAL = (140, 160)
META_DESC_HARD = (120, 175)

SHOPIFY_TOOLS = [
    {
        "name": "shopify_get_products",
        "description": (
            "Haal producten op uit Shopify met SEO-data (meta title, description). "
            "Gebruik om te checken welke producten SEO missen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Aantal producten (max 50, standaard 20)",
                    "default": 20
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["CREATED_AT", "UPDATED_AT", "TITLE", "INVENTORY_TOTAL",
                             "PRODUCT_TYPE", "PUBLISHED_AT", "VENDOR"],
                    "default": "UPDATED_AT",
                    "description": "Shopify ProductSortKeys. BEST_SELLING bestaat NIET in deze API; gebruik UPDATED_AT/INVENTORY_TOTAL als bestseller-proxy of haal meerdere sorts op."
                },
                "status": {
                    "type": "string",
                    "enum": ["ACTIVE", "DRAFT", "ARCHIVED"],
                    "default": "ACTIVE"
                }
            }
        }
    },
    {
        "name": "shopify_update_seo",
        "description": (
            "Update de SEO meta title en/of description van een product, collectie of pagina. "
            "Dit is de primaire fix-tool. Vereist goedkeuring van Diederik."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["product", "collection", "page"],
                    "description": "Type resource"
                },
                "resource_id": {
                    "type": "string",
                    "description": "Shopify GID (bijv. gid://shopify/Product/123)"
                },
                "meta_title": {
                    "type": "string",
                    "description": "Nieuwe meta title (50-60 tekens)"
                },
                "meta_description": {
                    "type": "string",
                    "description": "Nieuwe meta description (140-160 tekens)"
                }
            },
            "required": ["resource_type", "resource_id"]
        }
    },
    {
        "name": "shopify_update_translation",
        "description": (
            "Update een vertaling (NL/DE/FR) van SEO-velden via de Translations API. "
            "EN is de bron en wordt via shopify_update_seo aangepast."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "Shopify GID van het resource"
                },
                "locale": {
                    "type": "string",
                    "enum": ["nl", "de", "fr"],
                    "description": "Doeltaal"
                },
                "meta_title": {"type": "string"},
                "meta_description": {"type": "string"}
            },
            "required": ["resource_id", "locale"]
        }
    },
    {
        "name": "shopify_get_collections",
        "description": "Haal collecties op met SEO-data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "shopify_get_translations",
        "description": (
            "Haal vertalingen op voor een Shopify resource (product, collectie, pagina). "
            "Geeft de vertaalde meta_title en meta_description terug per taal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "Shopify GID (bijv. gid://shopify/Product/123)"
                },
                "locale": {
                    "type": "string",
                    "enum": ["nl", "de", "fr"],
                    "description": "Taal om op te halen"
                }
            },
            "required": ["resource_id", "locale"]
        }
    }
]


def _validate_seo_length(meta_title: str = "", meta_description: str = "") -> dict:
    """Controleer meta-lengtes. Warnings loggen we, errors blokkeren de mutation."""
    warnings, errors = [], []
    if meta_title:
        n = len(meta_title.strip())
        lo_i, hi_i = META_TITLE_IDEAL
        lo_h, hi_h = META_TITLE_HARD
        if n < lo_h or n > hi_h:
            errors.append(f"meta_title {n} tekens buiten hard limit {lo_h}-{hi_h}")
        elif n < lo_i or n > hi_i:
            warnings.append(f"meta_title {n} tekens buiten ideaal {lo_i}-{hi_i}")
    if meta_description:
        n = len(meta_description.strip())
        lo_i, hi_i = META_DESC_IDEAL
        lo_h, hi_h = META_DESC_HARD
        if n < lo_h or n > hi_h:
            errors.append(f"meta_description {n} tekens buiten hard limit {lo_h}-{hi_h}")
        elif n < lo_i or n > hi_i:
            warnings.append(f"meta_description {n} tekens buiten ideaal {lo_i}-{hi_i}")
    return {"warnings": warnings, "errors": errors}


def _http_post_with_retry(url: str, payload: dict, max_attempts: int = 4, base_delay: float = 1.0):
    """POST met exponential backoff bij 429/5xx en timeout. Nodig omdat Shopify
    (via de n8n-proxy) bij bursts 429 kan teruggeven — één fout zou anders de hele
    wekelijkse run in de afvalbak gooien."""
    headers = {"Content-Type": "application/json"}
    if SHOPIFY_PROXY_SECRET:
        headers["Authorization"] = f"Bearer {SHOPIFY_PROXY_SECRET}"

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            delay = base_delay * (2 ** (attempt - 1))
            log.warning("Shopify proxy timeout/connection (poging %d/%d), retry over %.1fs",
                        attempt, max_attempts, delay)
            time.sleep(delay)
            continue

        if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
            delay = base_delay * (2 ** (attempt - 1))
            log.warning("Shopify proxy HTTP %d (poging %d/%d), retry over %.1fs",
                        resp.status_code, attempt, max_attempts, delay)
            time.sleep(delay)
            continue

        return resp

    # Alle retries op — laatste exception doorgooien voor zichtbaarheid.
    if last_exc:
        raise last_exc
    raise requests.HTTPError(f"Shopify proxy onbereikbaar na {max_attempts} pogingen")


def _graphql(query: str, variables: dict = None) -> dict:
    """Voer een GraphQL query/mutation uit via de n8n-proxy.

    Response-envelope: n8n retourneert meestal `{"body": {"data": {...}}}` of
    `{"body": {"errors": [...]}}`. Soms direct `{"data": {...}}`. Bij proxy-falen
    kan het ook `{"body": null}`, een leeg object of zelfs geen JSON zijn. Elke
    variant moet voorspelbaar een dict opleveren — geen stille `None` die later
    `.get()` crasht.
    """
    body = {"query": query}
    if variables:
        body["variables"] = variables

    t0 = time.time()
    try:
        resp = _http_post_with_retry(SHOPIFY_PROXY_URL, body)
    except Exception as e:
        log.error("SHOPIFY_HTTP | fatal | %s", e)
        return {"error": f"Shopify proxy onbereikbaar: {e}"}

    elapsed_ms = int((time.time() - t0) * 1000)

    if resp.status_code >= 400:
        log.error("SHOPIFY_HTTP | status=%d | elapsed_ms=%d", resp.status_code, elapsed_ms)
        return {"error": f"Shopify proxy HTTP {resp.status_code}", "status_code": resp.status_code}

    # Response body parsen met guard — n8n kan bij fouten HTML of lege body sturen.
    try:
        data = resp.json()
    except ValueError:
        log.error("SHOPIFY_HTTP | non-json body | elapsed_ms=%d", elapsed_ms)
        return {"error": "Shopify proxy gaf geen geldige JSON terug"}

    if not isinstance(data, dict):
        return {"error": f"Shopify proxy response geen object: {type(data).__name__}"}

    # Unwrap de n8n-envelope. body kan dict, None of afwezig zijn.
    inner = data.get("body") if "body" in data else data
    if inner is None:
        return {"error": "Shopify proxy gaf lege body terug (mogelijk 204/502)."}
    if not isinstance(inner, dict):
        return {"error": "Shopify proxy body is geen object"}

    if inner.get("errors"):
        log.warning("SHOPIFY_GRAPHQL_ERRORS | %s", json.dumps(inner["errors"])[:300])
        return {"error": inner["errors"]}

    result = inner.get("data", inner)

    # userErrors staan één niveau dieper (per mutation). Escaleer ze naar log-warnings
    # zodat falende mutations niet stil doorglippen.
    if isinstance(result, dict):
        for key, val in result.items():
            if isinstance(val, dict) and val.get("userErrors"):
                log.warning("SHOPIFY_USER_ERRORS | mutation=%s | errors=%s",
                            key, json.dumps(val["userErrors"])[:300])

    return result


def _shopify_call(tool_name: str, func, input_data: dict):
    """Gemeenschappelijke instrumentatie rond elke tool-call: hash-logging,
    elapsed_ms, foutafhandeling. Geeft het (string) resultaat terug."""
    t0 = time.time()
    ihash = hashlib.md5(json.dumps(input_data, sort_keys=True, default=str).encode()).hexdigest()[:10]
    try:
        result = func()
    except Exception as e:
        log.error("SHOPIFY_CALL | tool=%s | input=%s | status=exception | err=%s",
                  tool_name, ihash, str(e)[:160])
        return json.dumps({"error": f"{tool_name} faalde: {e}"})

    if not isinstance(result, str):
        result = json.dumps(result, indent=2, default=str)

    rhash = hashlib.md5(result.encode()).hexdigest()[:10]
    elapsed_ms = int((time.time() - t0) * 1000)
    log.info("SHOPIFY_CALL | tool=%s | input=%s | response=%s | elapsed_ms=%d",
             tool_name, ihash, rhash, elapsed_ms)
    return result


# Hoeveel characters van product.description we meesturen — langere beschrijvingen
# zouden het context-budget leegtrekken zonder SEO-meerwaarde. De eerste ~600
# karakters bevatten bij Cadomotus vrijwel altijd merk, categorie en USP.
DESCRIPTION_TRUNC = 600


def _truncate_descriptions(products: list) -> list:
    """Zorg dat geen enkele beschrijving het context-budget laat ontsporen."""
    for p in products or []:
        desc = p.get("description")
        if isinstance(desc, str) and len(desc) > DESCRIPTION_TRUNC:
            p["description"] = desc[:DESCRIPTION_TRUNC] + " …[trunc]"
    return products


def execute_shopify_tool(name: str, input_data: dict) -> str:
    if name == "shopify_get_products":
        # Limit per page (Shopify max 50). Totaal cap via max_total.
        per_page = min(input_data.get("limit", 50), 50)
        status = input_data.get("status", "ACTIVE")
        sort = input_data.get("sort_by", "CREATED_AT")
        max_total = min(input_data.get("max_total", per_page), 200)
        after_cursor = input_data.get("after")

        query = """
        query getProducts($limit: Int!, $query: String, $sortKey: ProductSortKeys, $after: String) {
          products(first: $limit, query: $query, sortKey: $sortKey, reverse: true, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id title handle status createdAt updatedAt
              productType vendor tags
              description
              seo { title description }
              totalInventory
              featuredImage { url altText }
              collections(first: 20, sortKey: TITLE) { nodes { handle title } }
              priceRangeV2 { minVariantPrice { amount currencyCode } }
            }
          }
        }
        """

        def run():
            all_nodes: list = []
            cursor = after_cursor
            page_info = {"hasNextPage": False, "endCursor": None}
            pages_fetched = 0
            while True:
                res = _graphql(query, {
                    "limit": per_page,
                    "query": f"status:{status.lower()}",
                    "sortKey": sort,
                    "after": cursor,
                })
                if "error" in res:
                    return res
                products = res.get("products", {})
                nodes = products.get("nodes", []) or []
                all_nodes.extend(nodes)
                pages_fetched += 1
                page_info = products.get("pageInfo", {}) or {}
                cursor = page_info.get("endCursor")
                # Doorpaginatie alleen als caller expliciet meer vraagt via max_total.
                if (
                    not page_info.get("hasNextPage")
                    or len(all_nodes) >= max_total
                    or pages_fetched >= 5  # safety
                ):
                    break
            _truncate_descriptions(all_nodes)
            return {
                "products": {"nodes": all_nodes[:max_total], "pageInfo": page_info},
                "fetched": len(all_nodes),
            }

        return _shopify_call("shopify_get_products", run, input_data)

    elif name == "shopify_update_seo":
        rtype = input_data.get("resource_type")
        rid = input_data.get("resource_id")
        meta_title = input_data.get("meta_title")
        meta_description = input_data.get("meta_description")

        if rtype not in ("product", "collection", "page"):
            return json.dumps({"error": f"resource_type moet product/collection/page zijn, niet {rtype!r}"})
        if not rid:
            return json.dumps({"error": "resource_id ontbreekt"})
        if not (meta_title or meta_description):
            return json.dumps({"error": "Geen meta_title of meta_description opgegeven"})

        # Lengte-validatie vóór de API-call.
        lengths = _validate_seo_length(meta_title or "", meta_description or "")
        if lengths["errors"]:
            return json.dumps({"error": "SEO-lengte buiten toegelaten bereik", "details": lengths["errors"]})
        for w in lengths["warnings"]:
            log.warning("SEO_LEN | %s | %s | %s", rtype, rid, w)

        def run():
            # Page heeft GEEN `seo` op PageInput (Shopify Admin API 2024-10).
            # SEO voor pages gaat via metafields `global.title_tag` + `global.description_tag`.
            if rtype == "page":
                metafields = []
                if meta_title:
                    metafields.append({
                        "namespace": "global", "key": "title_tag",
                        "type": "single_line_text_field", "value": meta_title,
                    })
                if meta_description:
                    metafields.append({
                        "namespace": "global", "key": "description_tag",
                        "type": "single_line_text_field", "value": meta_description,
                    })
                if DRY_RUN:
                    return {"dry_run": True, "operation": "pageUpdate", "would_set_metafields": metafields, "id": rid}
                mutation = """
                mutation updatePageSeo($input: PageInput!) {
                  pageUpdate(input: $input) {
                    userErrors { field message }
                  }
                }
                """
                return _graphql(mutation, {"input": {"id": rid, "metafields": metafields}})

            # Product/collection: `seo: { title, description }` op de resource-input.
            seo_fields = {}
            if meta_title:
                seo_fields["title"] = meta_title
            if meta_description:
                seo_fields["description"] = meta_description

            mutation_map = {
                "product": ("productUpdate", "ProductInput"),
                "collection": ("collectionUpdate", "CollectionInput"),
            }
            mutation_name, input_type = mutation_map[rtype]

            if DRY_RUN:
                return {"dry_run": True, "operation": mutation_name,
                        "would_update": {"id": rid, "seo": seo_fields}}

            mutation = f"""
            mutation updateSeo($input: {input_type}!) {{
              {mutation_name}(input: $input) {{
                userErrors {{ field message }}
              }}
            }}
            """
            return _graphql(mutation, {"input": {"id": rid, "seo": seo_fields}})

        return _shopify_call("shopify_update_seo", run, input_data)

    elif name == "shopify_update_translation":
        rid = input_data.get("resource_id")
        locale = input_data.get("locale")
        meta_title = input_data.get("meta_title")
        meta_description = input_data.get("meta_description")

        if not locale or not isinstance(locale, str):
            return json.dumps({"error": "locale ontbreekt of is geen string."})
        if not rid:
            return json.dumps({"error": "resource_id ontbreekt"})
        # Guard: EN hoort via shopify_update_seo (brondata). Dekt ook underscore-variant.
        normalized = locale.strip().lower().replace("_", "-")
        if normalized == "en" or normalized.startswith("en-"):
            return json.dumps({
                "error": "EN hoort via shopify_update_seo te gaan (brondata), niet via "
                         "shopify_update_translation. Gebruik de juiste tool."
            })

        lengths = _validate_seo_length(meta_title or "", meta_description or "")
        if lengths["errors"]:
            return json.dumps({"error": "SEO-lengte buiten toegelaten bereik", "details": lengths["errors"]})
        for w in lengths["warnings"]:
            log.warning("SEO_LEN | translation | %s | %s | %s", locale, rid, w)

        translations = []
        if meta_title:
            translations.append({"key": "meta_title", "value": meta_title,
                                 "locale": locale, "translatableContentDigest": ""})
        if meta_description:
            translations.append({"key": "meta_description", "value": meta_description,
                                 "locale": locale, "translatableContentDigest": ""})
        if not translations:
            return json.dumps({"error": "Geen meta_title of meta_description opgegeven."})

        def run():
            digest_query = """
            query getDigests($resourceId: ID!) {
              translatableResource(resourceId: $resourceId) {
                translatableContent { key digest locale }
              }
            }
            """
            digest_result = _graphql(digest_query, {"resourceId": rid})
            if "error" in digest_result:
                return {"error": "Kon source-digests niet ophalen", "details": digest_result["error"]}
            contents = (digest_result.get("translatableResource") or {}).get("translatableContent", []) or []
            digest_map: dict = {}
            for c in contents:
                key = c.get("key")
                if key and key not in digest_map and c.get("digest"):
                    digest_map[key] = c["digest"]

            missing = [t["key"] for t in translations if not digest_map.get(t["key"])]
            if missing:
                return {
                    "error": f"Geen source-digest voor keys {missing} — translation niet geregistreerd. "
                             "Mogelijk bestaat de resource niet of heeft geen translatable content voor dit veld.",
                    "resource_id": rid, "locale": locale,
                }

            for t in translations:
                t["translatableContentDigest"] = digest_map[t["key"]]

            if DRY_RUN:
                return {"dry_run": True, "operation": "translationsRegister",
                        "would_register": {"resourceId": rid, "translations": translations}}

            mutation = """
            mutation translateSeo($resourceId: ID!, $translations: [TranslationInput!]!) {
              translationsRegister(resourceId: $resourceId, translations: $translations) {
                userErrors { field message }
              }
            }
            """
            return _graphql(mutation, {"resourceId": rid, "translations": translations})

        return _shopify_call("shopify_update_translation", run, input_data)

    elif name == "shopify_get_collections":
        limit = min(input_data.get("limit", 50), 50)

        def run():
            query = """
            query getCollections($limit: Int!) {
              collections(first: $limit, sortKey: UPDATED_AT, reverse: true) {
                nodes {
                  id title handle description
                  updatedAt templateSuffix
                  seo { title description }
                  productsCount { count }
                  image { url altText }
                }
              }
            }
            """
            res = _graphql(query, {"limit": limit})
            if isinstance(res, dict):
                collections = (res.get("collections") or {}).get("nodes") or []
                # Kort de collection-description in (HTML-vrij, max 400 chars).
                for c in collections:
                    desc = c.get("description")
                    if isinstance(desc, str) and len(desc) > 400:
                        c["description"] = desc[:400] + " …[trunc]"
            return res

        return _shopify_call("shopify_get_collections", run, input_data)

    elif name == "shopify_get_translations":
        rid = input_data.get("resource_id")
        locale = input_data.get("locale")
        if not rid or not locale:
            return json.dumps({"error": "resource_id en locale zijn verplicht"})

        def run():
            # Haal én de bestaande vertalingen (key,value) én de source-digests op.
            # Door digest-vergelijking kunnen we afleiden of een translation 'outdated' is:
            # als `translation.translations[].translatableContentDigest` afwijkt van de
            # bron-digest voor die key, is de bron sinds de vertaling gewijzigd.
            query = """
            query getTranslations($resourceId: ID!, $locale: String!) {
              translatableResource(resourceId: $resourceId) {
                translatableContent { key digest locale }
                translations(locale: $locale) { key value outdated }
              }
            }
            """
            res = _graphql(query, {"resourceId": rid, "locale": locale})
            if not isinstance(res, dict) or "error" in res:
                return res
            # Verrijk: voeg per translation een `source_digest` toe voor debugging.
            tr_resource = res.get("translatableResource") or {}
            contents = tr_resource.get("translatableContent") or []
            source_digests = {c["key"]: c.get("digest") for c in contents if c.get("key")}
            for t in tr_resource.get("translations") or []:
                t["source_digest"] = source_digests.get(t.get("key"))
            return res

        return _shopify_call("shopify_get_translations", run, input_data)

    return json.dumps({"error": f"Unknown tool: {name}"})
