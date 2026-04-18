"""Shopify GraphQL tools voor de Cadomotus SEO agent."""

import os
import json
import requests

# Shopify via n8n webhook proxy (de directe token auth gaat via n8n)
SHOPIFY_PROXY_URL = os.getenv(
    "SHOPIFY_PROXY_URL",
    "https://maartenklouwen.app.n8n.cloud/webhook/cadomotus-shopify"
)

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
                    "enum": ["CREATED_AT", "UPDATED_AT", "TITLE", "BEST_SELLING"],
                    "default": "CREATED_AT"
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


def _graphql(query: str, variables: dict = None) -> dict:
    body = {"query": query}
    if variables:
        body["variables"] = variables

    resp = requests.post(
        SHOPIFY_PROXY_URL,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    # n8n proxy wrapt response in body.data
    if "body" in data:
        inner = data["body"]
        if "errors" in inner:
            return {"error": inner["errors"]}
        return inner.get("data", inner)

    if "errors" in data:
        return {"error": data["errors"]}
    return data.get("data", data)


def execute_shopify_tool(name: str, input_data: dict) -> str:
    if name == "shopify_get_products":
        limit = min(input_data.get("limit", 20), 50)
        status = input_data.get("status", "ACTIVE")
        sort = input_data.get("sort_by", "CREATED_AT")

        query = """
        query getProducts($limit: Int!, $query: String, $sortKey: ProductSortKeys) {
          products(first: $limit, query: $query, sortKey: $sortKey, reverse: true) {
            nodes {
              id title handle status createdAt
              seo { title description }
              totalInventory
              featuredImage { url altText }
            }
          }
        }
        """
        result = _graphql(query, {
            "limit": limit,
            "query": f"status:{status.lower()}",
            "sortKey": sort,
        })
        return json.dumps(result, indent=2)

    elif name == "shopify_update_seo":
        rtype = input_data["resource_type"]
        rid = input_data["resource_id"]
        seo_fields = {}
        if input_data.get("meta_title"):
            seo_fields["title"] = input_data["meta_title"]
        if input_data.get("meta_description"):
            seo_fields["description"] = input_data["meta_description"]

        if not seo_fields:
            return json.dumps({"error": "Geen meta_title of meta_description opgegeven"})

        mutation_map = {
            "product": ("productUpdate", "ProductInput"),
            "collection": ("collectionUpdate", "CollectionInput"),
            "page": ("pageUpdate", "PageUpdateInput"),
        }
        mutation_name, input_type = mutation_map[rtype]

        mutation = f"""
        mutation updateSeo($input: {input_type}!) {{
          {mutation_name}(input: $input) {{
            userErrors {{ field message }}
          }}
        }}
        """
        result = _graphql(mutation, {
            "input": {"id": rid, "seo": seo_fields}
        })
        return json.dumps(result, indent=2)

    elif name == "shopify_update_translation":
        rid = input_data["resource_id"]
        locale = input_data["locale"]

        translations = []
        if input_data.get("meta_title"):
            translations.append({
                "key": "meta_title",
                "value": input_data["meta_title"],
                "locale": locale,
                "translatableContentDigest": ""  # Shopify vereist dit — wordt hieronder opgehaald
            })
        if input_data.get("meta_description"):
            translations.append({
                "key": "meta_description",
                "value": input_data["meta_description"],
                "locale": locale,
                "translatableContentDigest": ""
            })

        # Eerst digests ophalen
        digest_query = """
        query getDigests($resourceId: ID!) {
          translatableResource(resourceId: $resourceId) {
            translatableContent { key digest locale }
          }
        }
        """
        digest_result = _graphql(digest_query, {"resourceId": rid})
        contents = digest_result.get("translatableResource", {}).get("translatableContent", [])
        digest_map = {c["key"]: c["digest"] for c in contents}

        for t in translations:
            t["translatableContentDigest"] = digest_map.get(t["key"], "")

        mutation = """
        mutation translateSeo($resourceId: ID!, $translations: [TranslationInput!]!) {
          translationsRegister(resourceId: $resourceId, translations: $translations) {
            userErrors { field message }
          }
        }
        """
        result = _graphql(mutation, {
            "resourceId": rid,
            "translations": translations
        })
        return json.dumps(result, indent=2)

    elif name == "shopify_get_collections":
        limit = min(input_data.get("limit", 20), 50)
        query = """
        query getCollections($limit: Int!) {
          collections(first: $limit) {
            nodes {
              id title handle
              seo { title description }
              productsCount { count }
            }
          }
        }
        """
        result = _graphql(query, {"limit": limit})
        return json.dumps(result, indent=2)

    elif name == "shopify_get_translations":
        rid = input_data["resource_id"]
        locale = input_data["locale"]

        query = """
        query getTranslations($resourceId: ID!, $locale: String!) {
          translatableResource(resourceId: $resourceId) {
            translations(locale: $locale) {
              key
              value
            }
          }
        }
        """
        result = _graphql(query, {"resourceId": rid, "locale": locale})
        return json.dumps(result, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})
