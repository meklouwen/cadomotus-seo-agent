"""Bulk SEO audit: alle productafbeeldingen zonder alt-tekst + dode/redirect links."""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from tools.shopify import _graphql

log = logging.getLogger("cadomotus-bulk-audit")

CADOMOTUS_BASE = "https://cadomotus.com"

EN_SITEMAPS = [
    "https://cadomotus.com/sitemap_products_1.xml",
    "https://cadomotus.com/sitemap_collections_1.xml",
    "https://cadomotus.com/sitemap_pages_1.xml",
    "https://cadomotus.com/sitemap_blogs_1.xml",
    "https://cadomotus.com/sitemap_articles_1.xml",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CadomotusSEOBot/1.0; +https://thesystem.nl)",
    "Accept": "text/html,application/xhtml+xml",
}

LOC_RE = re.compile(r"<loc>(https://cadomotus\.com(?!/(?:fr|de|nl)/)[^<]*)</loc>")

# media connection returns gid://shopify/MediaImage/... IDs (required for fileUpdate mutation).
# images connection returns deprecated gid://shopify/ProductImage/... IDs (productImageUpdate removed in 2024-04).
PRODUCT_IMAGES_QUERY = """
query getProductMedia($cursor: String) {
  products(first: 50, query: "status:active", after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title handle
      media(first: 50) {
        nodes {
          ... on MediaImage {
            id
            image { url altText }
          }
        }
      }
    }
  }
}
"""


# ─────────────────────────────────────────────────────────────
# A: Shopify Admin API — alle product images ophalen
# ─────────────────────────────────────────────────────────────

def _suggest_alt(title: str, index: int) -> str:
    suffix = " | Cádomotus"
    base = title if index == 0 else f"{title} – detail {index}"
    full = base + suffix
    if len(full) <= 125:
        return full
    return base[: 125 - len(suffix)] + suffix


def get_images_missing_alt() -> list:
    """Query alle actieve producten + images via Shopify API. Retourneer images zonder alt."""
    log.info("[bulk] Ophalen product-images via Shopify API...")
    all_missing = []
    cursor = None
    page = 0

    while True:
        res = _graphql(PRODUCT_IMAGES_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[bulk] Shopify error: %s", res["error"])
            break

        products_data = res.get("products", {}) or {}
        nodes = products_data.get("nodes", []) or []

        for product in nodes:
            product_id = product.get("id", "")
            product_title = product.get("title", "")
            product_handle = product.get("handle", "")
            # media connection returns MediaImage nodes with nested image object
            media_nodes = (product.get("media") or {}).get("nodes", []) or []
            # Filter to only MediaImage type (skip Video, ExternalVideo, Model3d)
            images = [m for m in media_nodes if m.get("id", "").startswith("gid://shopify/MediaImage/")]

            for idx, media in enumerate(images):
                img = media.get("image") or {}
                alt = (img.get("altText") or "").strip()
                if not alt:
                    all_missing.append({
                        "product_id": product_id,
                        "product_title": product_title,
                        "product_handle": product_handle,
                        "product_url": f"{CADOMOTUS_BASE}/products/{product_handle}",
                        "image_id": media.get("id", ""),   # gid://shopify/MediaImage/...
                        "image_src": img.get("url", ""),
                        "current_alt": "",
                        "suggested_alt": _suggest_alt(product_title, idx),
                        "image_index": idx,
                        "status": "pending",
                    })

        page_info = products_data.get("pageInfo", {}) or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        page += 1
        log.info("[bulk] Shopify pagina %d — %d images zonder alt tot nu toe", page, len(all_missing))
        time.sleep(0.3)

    log.info("[bulk] Totaal %d images zonder alt-tekst", len(all_missing))
    return all_missing


# ─────────────────────────────────────────────────────────────
# B: HTML crawler — dode links + redirects
# ─────────────────────────────────────────────────────────────

class _LinkExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list = []
        self._in_a = False
        self._a_text: list = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_a = True
            self._a_text = []
            href = dict(attrs).get("href", "") or ""
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                abs_href = urljoin(self.base_url, href)
                if urlparse(abs_href).netloc == "cadomotus.com":
                    self.links.append({"href": abs_href, "text": ""})

    def handle_data(self, data):
        if self._in_a:
            self._a_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._in_a:
            if self.links:
                self.links[-1]["text"] = " ".join(self._a_text)[:100]
            self._in_a = False
            self._a_text = []


def _fetch_sitemap_urls(sitemap_url: str) -> list:
    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            # LOC_RE filtert al /fr/, /de/, /nl/ prefixes via negatieve lookahead
            return LOC_RE.findall(resp.text)
    except Exception as e:
        log.warning("[bulk] Sitemap fout %s: %s", sitemap_url, e)
    return []


def _crawl_page(url: str) -> list:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            return []
        parser = _LinkExtractor(url)
        parser.feed(resp.text)
        return [{"href": l["href"], "text": l["text"], "found_on": url} for l in parser.links]
    except Exception as e:
        log.warning("[bulk] Pagina-fetch fout %s: %s", url, e)
        return []


def _check_link(link_info: dict) -> dict:
    href = link_info["href"]
    try:
        resp = requests.head(href, headers=HEADERS, timeout=10, allow_redirects=False)
        status = resp.status_code
        location = resp.headers.get("Location", "")
        return {
            "link_url": href,
            "found_on_page": link_info["found_on"],
            "anchor_text": link_info["text"],
            "http_status": status,
            "redirects_to": urljoin(href, location) if location else "",
            "status": "pending",
        }
    except Exception as e:
        log.warning("[bulk] Link-check fout %s: %s", href, e)
        return {
            "link_url": href,
            "found_on_page": link_info["found_on"],
            "anchor_text": link_info["text"],
            "http_status": 0,
            "redirects_to": "",
            "status": "error",
        }


def crawl_links(status_callback=None) -> dict:
    """Crawl alle EN-sitemap pagina's en check link-status."""
    all_urls = []
    for sm in EN_SITEMAPS:
        urls = _fetch_sitemap_urls(sm)
        # Aanvulling: voeg ook sitemap-URL toe als de URL niet de query-string params mist
        if not urls:
            # Probeer met query-params vanuit sitemap index
            log.info("[bulk] %s: 0 URLs gevonden, skip", sm)
        all_urls.extend(urls)
        log.info("[bulk] Sitemap %s: %d URLs", sm.split("/")[-1], len(urls))

    # Dedup
    all_urls = list(dict.fromkeys(all_urls))
    log.info("[bulk] %d unieke EN-pagina's te crawlen", len(all_urls))

    if status_callback:
        status_callback({"status": "running", "phase": "crawling_pages",
                         "pages_crawled": 0, "total": len(all_urls)})

    # Pagina's crawlen (5 concurrent)
    all_links = []
    crawled = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_crawl_page, url): url for url in all_urls}
        for future in as_completed(futures):
            try:
                links = future.result()
                all_links.extend(links)
            except Exception:
                pass
            crawled += 1
            if crawled % 20 == 0:
                log.info("[bulk] Gecrawled: %d/%d pagina's", crawled, len(all_urls))
                if status_callback:
                    status_callback({"status": "running", "phase": "crawling_pages",
                                     "pages_crawled": crawled, "total": len(all_urls)})

    # Dedup links
    seen: set = set()
    unique_links = []
    for l in all_links:
        if l["href"] not in seen:
            seen.add(l["href"])
            unique_links.append(l)
    log.info("[bulk] %d unieke interne links te controleren", len(unique_links))

    if status_callback:
        status_callback({"status": "running", "phase": "checking_links",
                         "pages_crawled": crawled, "total": len(all_urls)})

    # Link-check (10 concurrent HEAD requests)
    results = []
    checked = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_check_link, l): l for l in unique_links}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception:
                pass
            checked += 1
            if checked % 100 == 0:
                log.info("[bulk] Link-check: %d/%d", checked, len(unique_links))

    dead = [r for r in results if r["http_status"] in (0, 404, 410)]
    redirects = [r for r in results if r["http_status"] in (301, 302, 307, 308)]
    log.info("[bulk] Resultaat: %d dode links, %d redirects", len(dead), len(redirects))
    return {"dead_links": dead, "redirect_links": redirects}


# ─────────────────────────────────────────────────────────────
# C: Coördinator
# ─────────────────────────────────────────────────────────────

def run_bulk_audit(data_dir: str = "/data", status_ref: dict = None) -> dict:
    """Volledige bulk audit: Shopify images + link-crawl. Slaat resultaten op als JSON."""
    import datetime

    def _upd(info: dict):
        if status_ref is not None:
            status_ref.clear()
            status_ref.update(info)

    _upd({"status": "running", "phase": "images", "pages_crawled": 0, "total": 0})

    log.info("[bulk] === Bulk audit gestart ===")

    # Fase 1: product images
    missing_alts = get_images_missing_alt()
    _upd({"status": "running", "phase": "links", "pages_crawled": 0, "total": 0,
          "missing_alt_count": len(missing_alts)})

    # Fase 2: link-crawl
    link_results = crawl_links(status_callback=_upd)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = {
        "crawled_at": now,
        "missing_alt": missing_alts,
        "dead_links": link_results["dead_links"],
        "redirect_links": link_results["redirect_links"],
        "summary": {
            "missing_alt_count": len(missing_alts),
            "dead_links_count": len(link_results["dead_links"]),
            "redirect_count": len(link_results["redirect_links"]),
        },
    }

    os.makedirs(data_dir, exist_ok=True)
    audit_path = os.path.join(data_dir, "bulk_audit.json")
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    log.info("[bulk] === Audit klaar: %s ===", audit_path)
    _upd({
        "status": "done",
        "phase": "done",
        "crawled_at": now,
        "missing_alt_count": len(missing_alts),
        "dead_links_count": len(link_results["dead_links"]),
        "redirect_count": len(link_results["redirect_links"]),
    })
    return result
