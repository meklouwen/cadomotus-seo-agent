"""Volledige SEO-audit: alle pagina's × alle talen × alle checks.

Checks per pagina:
  meta_title_too_short     < 30 chars
  meta_title_too_long      > 60 chars
  meta_title_no_brand      geen 'cádomotus' / 'cadomotus' in title
  meta_desc_missing        geen meta description
  meta_desc_too_long       > 160 chars
  meta_desc_too_short      < 70 chars
  og_image_http            og:image via http:// (niet https)
  og_image_missing         geen og:image
  og_title_missing         geen og:title
  h1_missing               geen <h1>
  h1_multiple              meer dan 1 <h1>
  canonical_missing        geen canonical link
  hreflang_missing         geen hreflang alternate links
  hreflang_no_xdefault     hreflang aanwezig maar geen x-default
  schema_missing           geen JSON-LD script
  schema_malformed         JSON-LD parseert niet als JSON

Plus via Shopify Admin API:
  shopify_seo_title_missing     seo.title leeg
  shopify_seo_desc_missing      seo.description leeg
  shopify_seo_desc_too_long     seo.description > 160 chars
  shopify_seo_title_no_brand    geen 'cádomotus' in seo.title
  shopify_no_description        product/collection body leeg
  shopify_collection_no_image   collection heeft geen afbeelding
"""

import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from tools.shopify import _graphql

log = logging.getLogger("cadomotus-full-seo")

BASE = "https://cadomotus.com"
# Gebruik herkenbare SEO-bot UA — Cloudflare laat deze door,
# maar Chrome UA triggert een JS-challenge die requests() niet kan oplossen.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CadomotusSEOBot/2.0; +https://thesystem.nl)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SITEMAP_INDEX = f"{BASE}/sitemap.xml"

SEVERITY = {
    "meta_title_too_short":       "medium",
    "meta_title_too_long":        "medium",
    "meta_title_no_brand":        "medium",
    "meta_desc_missing":          "high",
    "meta_desc_too_long":         "high",
    "meta_desc_too_short":        "medium",
    "og_image_http":              "low",
    "og_image_missing":           "medium",
    "og_title_missing":           "medium",
    "h1_missing":                 "high",
    "h1_multiple":                "medium",
    "canonical_missing":          "high",
    "hreflang_missing":           "high",
    "hreflang_no_xdefault":       "medium",
    "schema_missing":             "medium",
    "schema_malformed":           "high",
    "shopify_seo_title_missing":   "high",
    "shopify_seo_desc_missing":    "high",
    "shopify_seo_desc_too_long":   "high",
    "shopify_seo_title_no_brand":  "medium",
    "shopify_no_description":      "medium",
    "shopify_collection_no_image": "low",
    "shopify_article_seo_title_missing":  "high",
    "shopify_article_seo_desc_missing":   "high",
    "shopify_article_no_brand":           "medium",
    "shopify_article_no_image":           "medium",
    "shopify_article_thin_content":       "medium",
    "shopify_article_seo_desc_too_long":  "medium",
    "shopify_page_seo_title_missing":     "high",
    "shopify_page_seo_desc_missing":      "high",
    "shopify_page_no_brand":              "medium",
    "shopify_page_thin_content":          "medium",
    "shopify_page_seo_desc_too_long":     "medium",
    "shopify_redirect_chain":             "medium",
    "shopify_product_few_images":         "medium",
    "shopify_product_no_tags":            "low",
}

LABEL = {
    "meta_title_too_short":       "Meta-title te kort (< 30 tekens)",
    "meta_title_too_long":        "Meta-title te lang (> 60 tekens)",
    "meta_title_no_brand":        "Merknaam ontbreekt in meta-title",
    "meta_desc_missing":          "Meta-description ontbreekt",
    "meta_desc_too_long":         "Meta-description te lang (> 160 tekens)",
    "meta_desc_too_short":        "Meta-description te kort (< 70 tekens)",
    "og_image_http":              "OG-afbeelding via onveilig HTTP",
    "og_image_missing":           "OG-afbeelding (og:image) ontbreekt",
    "og_title_missing":           "OG-titel (og:title) ontbreekt",
    "h1_missing":                 "Geen H1-tag gevonden",
    "h1_multiple":                "Meerdere H1-tags op één pagina",
    "canonical_missing":          "Canonical URL ontbreekt",
    "hreflang_missing":           "Hreflang-attributen ontbreken",
    "hreflang_no_xdefault":       "Hreflang zonder x-default",
    "schema_missing":             "Geen JSON-LD structured data",
    "schema_malformed":           "JSON-LD structured data ongeldig",
    "shopify_seo_title_missing":   "[Product] SEO-titel niet ingesteld",
    "shopify_seo_desc_missing":    "[Product] SEO-beschrijving niet ingesteld",
    "shopify_seo_desc_too_long":   "[Product] SEO-beschrijving te lang (> 160 tekens)",
    "shopify_seo_title_no_brand":  "[Product] Merknaam ontbreekt in SEO-titel",
    "shopify_no_description":      "[Product/Collectie] Beschrijving ontbreekt",
    "shopify_collection_no_image": "[Collectie] Geen afbeelding",
    "shopify_article_seo_title_missing":  "[Artikel] SEO-titel niet ingesteld",
    "shopify_article_seo_desc_missing":   "[Artikel] SEO-beschrijving niet ingesteld",
    "shopify_article_no_brand":           "[Artikel] Merknaam ontbreekt in SEO-titel",
    "shopify_article_no_image":           "[Artikel] Geen uitgelichte afbeelding",
    "shopify_article_thin_content":       "[Artikel] Te weinig content (< 300 woorden)",
    "shopify_article_seo_desc_too_long":  "[Artikel] SEO-beschrijving te lang (> 160 tekens)",
    "shopify_page_seo_title_missing":     "[Pagina] SEO-titel niet ingesteld",
    "shopify_page_seo_desc_missing":      "[Pagina] SEO-beschrijving niet ingesteld",
    "shopify_page_no_brand":              "[Pagina] Merknaam ontbreekt in SEO-titel",
    "shopify_page_thin_content":          "[Pagina] Te weinig content (< 100 woorden)",
    "shopify_page_seo_desc_too_long":     "[Pagina] SEO-beschrijving te lang (> 160 tekens)",
    "shopify_redirect_chain":             "[Redirect] Redirect-keten (dubbele omleiding)",
    "shopify_product_few_images":         "[Product] Weinig afbeeldingen (< 3)",
    "shopify_product_no_tags":            "[Product] Geen tags/keywords ingesteld",
}


# ─────────────────────────────────────────────────────────────
# A: Sitemap crawler — alle URLs uit de sitemap-index
# ─────────────────────────────────────────────────────────────

LOC_RE = re.compile(r"<loc>([^<]+)</loc>")

BOT_UA = "Mozilla/5.0 (compatible; CadomotusSEOBot/2.0; +https://thesystem.nl)"


def _curl_fetch(url: str, timeout: int = 8) -> tuple:
    """Haal een URL op via curl (bypassed Cloudflare TLS fingerprint detectie).

    Returns: (status_code: int, body: str, final_url: str)
    """
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-L",
                "--max-time", str(timeout),
                "-A", BOT_UA,
                "-w", "\n__CURL_STATUS__%{http_code}__CURL_URL__%{url_effective}__",
                url,
            ],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        raw = result.stdout
        # Extract status + final URL from the sentinel at the end
        sentinel_start = raw.rfind("\n__CURL_STATUS__")
        if sentinel_start == -1:
            return 0, "", url
        body = raw[:sentinel_start]
        meta = raw[sentinel_start + 1:]
        parts = meta.split("__")
        # parts: ['__CURL_STATUS', status_code, '__CURL_URL', final_url, '__']
        status = int(parts[2]) if len(parts) >= 3 else 0
        final = parts[4] if len(parts) >= 5 else url
        return status, body, final
    except Exception as e:
        log.warning("[full_audit] curl fout %s: %s", url, e)
        return 0, "", url


def _fetch_urls_from_sitemap(url: str) -> list:
    status, body, _ = _curl_fetch(url, timeout=15)
    if status == 200:
        return LOC_RE.findall(body)
    log.warning("[full_audit] sitemap-curl fout %s: status %d", url, status)
    return []

# Fallback sitemaps als cadomotus.com de index-sitemap niet serveert (bijv. Cloudflare-ban)
_FALLBACK_SITEMAPS = [
    "https://cadomotus.com/sitemap_products_1.xml?from=9682207441182&to=10119519961374",
    "https://cadomotus.com/sitemap_pages_1.xml?from=140724535582&to=160297976094",
    "https://cadomotus.com/sitemap_collections_1.xml?from=636039987486&to=651201741086",
    "https://cadomotus.com/sitemap_blogs_1.xml",
    "https://cadomotus.com/nl/sitemap_products_1.xml?from=9682207441182&to=10119519961374",
    "https://cadomotus.com/nl/sitemap_pages_1.xml?from=140724535582&to=160297976094",
    "https://cadomotus.com/nl/sitemap_collections_1.xml?from=636039987486&to=651201741086",
    "https://cadomotus.com/nl/sitemap_blogs_1.xml",
    "https://cadomotus.com/de/sitemap_products_1.xml?from=9682207441182&to=10119519961374",
    "https://cadomotus.com/de/sitemap_pages_1.xml?from=140724535582&to=160297976094",
    "https://cadomotus.com/de/sitemap_collections_1.xml?from=636039987486&to=651201741086",
    "https://cadomotus.com/de/sitemap_blogs_1.xml",
    "https://cadomotus.com/fr/sitemap_products_1.xml?from=9682207441182&to=10119519961374",
    "https://cadomotus.com/fr/sitemap_pages_1.xml?from=140724535582&to=160297976094",
    "https://cadomotus.com/fr/sitemap_collections_1.xml?from=636039987486&to=651201741086",
    "https://cadomotus.com/fr/sitemap_blogs_1.xml",
]


def fetch_all_sitemap_urls() -> list:
    """Haal alle URLs op uit de sitemap-index (inclusief alle talen).

    Valt terug op hardcoded sitemaps als de index geblokkeerd is (bijv. Cloudflare).
    """
    index_xml = ""
    child_sitemaps = []

    status, body, _ = _curl_fetch(SITEMAP_INDEX, timeout=15)
    log.info("[full_audit] sitemap-index status: %d (eerste 200 chars: %s)",
             status, body[:200].replace("\n", " "))
    if status == 200 and "<?xml" in body[:50]:
        index_xml = body
    else:
        log.warning("[full_audit] sitemap-index niet leesbaar (status %d of geen XML) — "
                    "gebruik fallback sitemaps", status)

    if index_xml:
        child_sitemaps = LOC_RE.findall(index_xml)
        # HTML entity decode &amp; → &
        child_sitemaps = [s.replace("&amp;", "&") for s in child_sitemaps]
        # Sla agentic_discovery over (niet nuttig voor SEO-audit)
        child_sitemaps = [s for s in child_sitemaps if "agentic_discovery" not in s]

    if not child_sitemaps:
        log.warning("[full_audit] Geen child-sitemaps van index — gebruik %d hardcoded fallback sitemaps",
                    len(_FALLBACK_SITEMAPS))
        child_sitemaps = _FALLBACK_SITEMAPS

    log.info("[full_audit] %d child-sitemaps gevonden", len(child_sitemaps))

    all_urls = []
    for sm in child_sitemaps:
        urls = _fetch_urls_from_sitemap(sm)
        # Blogsitemap bevat zowel blog-index als artikelen
        # Verwijder uitsluitend blog-index pagina's (pad eindigt op /blogs/)
        page_urls = [u for u in urls if not u.rstrip("/").endswith("/blogs")]
        all_urls.extend(page_urls)
        log.info("[full_audit] %s: %d urls", sm.split("/")[-1].split("?")[0], len(page_urls))
        time.sleep(0.1)

    # Dedup maar behoud volgorde
    seen = set()
    unique = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    log.info("[full_audit] Totaal %d unieke URLs", len(unique))
    return unique


# ─────────────────────────────────────────────────────────────
# B: HTML-parser — extraheer SEO-attributen per pagina
# ─────────────────────────────────────────────────────────────

class _SEOParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.h1s: list = []
        self._in_h1 = False
        self._h1_buf = ""
        self.meta_desc = ""
        self.og: dict = {}
        self.canonical = ""
        self.hreflangs: list = []
        self.ld_json_blocks: list = []
        self._in_ld_json = False
        self._ld_buf = ""
        self._in_head = True  # stop parsing body after </head> for speed

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "head":
            self._in_head = True
        elif tag == "body":
            self._in_head = False
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
            self._h1_buf = ""
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            content = a.get("content") or ""
            if name == "description":
                self.meta_desc = content.strip()
            elif prop.startswith("og:"):
                self.og[prop] = content.strip()
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            if rel == "canonical":
                self.canonical = a.get("href", "")
            elif rel == "alternate":
                hl = a.get("hreflang", "")
                if hl:
                    self.hreflangs.append(hl.lower())
        elif tag == "script":
            if (a.get("type") or "").lower() == "application/ld+json":
                self._in_ld_json = True
                self._ld_buf = ""

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_h1:
            self._h1_buf += data
        if self._in_ld_json:
            self._ld_buf += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            self.title = self.title.strip()
        elif tag == "h1":
            self._in_h1 = False
            h1 = self._h1_buf.strip()
            if h1:
                self.h1s.append(h1)
        elif tag == "script" and self._in_ld_json:
            self._in_ld_json = False
            self.ld_json_blocks.append(self._ld_buf.strip())


def _detect_lang(url: str) -> str:
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if parts and parts[0] in ("fr", "de", "nl"):
        return parts[0]
    return "en"

def _detect_page_type(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Remove language prefix
    parts = path.split("/")
    if parts and parts[0] in ("fr", "de", "nl"):
        parts = parts[1:]
    if not parts:
        return "home"
    first = parts[0]
    if first == "products":
        return "product"
    if first == "collections":
        return "collection"
    if first == "pages":
        return "page"
    if first == "blogs":
        return "article"
    return "other"


def analyze_page(url: str) -> list:
    """Crawl één pagina en retourneer alle SEO-issues als lijst van dicts."""
    issues = []
    lang = _detect_lang(url)
    page_type = _detect_page_type(url)

    # curl ipv requests — Cloudflare blokkeert Python requests op basis van TLS fingerprint
    status_code, html_text, final_url = _curl_fetch(url)

    if status_code == 0:
        return [{
            "type": "http_error", "url": url, "lang": lang, "page_type": page_type,
            "severity": "high",
            "label": "HTTP-fout bij ophalen pagina",
            "current_value": "curl fout / timeout",
            "status": "pending",
        }]

    if status_code == 429:
        log.info("[full_audit] 429 op %s — wacht 5s en retry", url)
        time.sleep(5)
        status_code, html_text, final_url = _curl_fetch(url)
        if status_code in (0, 429):
            return []  # Skip na tweede 429

    # Maak resp-achtige structuur voor de rest van de code
    class _FakeResp:
        def __init__(self, s, t, u):
            self.status_code = s
            self.text = t
            self.url = u
    resp = _FakeResp(status_code, html_text, final_url)

    if resp.status_code != 200:
        return [{
            "type": "http_error", "url": url, "lang": lang, "page_type": page_type,
            "severity": "high",
            "label": f"HTTP {resp.status_code}",
            "current_value": f"Status: {resp.status_code}",
            "status": "pending",
        }]

    # Redirect gevolgd? Log final URL
    final_url = resp.url

    parser = _SEOParser()
    try:
        parser.feed(resp.text)
    except Exception:
        pass

    title = parser.title
    meta_desc = parser.meta_desc
    og = parser.og
    canonical = parser.canonical
    hreflangs = parser.hreflangs
    h1s = parser.h1s
    ld_blocks = parser.ld_json_blocks

    def add(issue_type: str, current: str = "", extra: dict = None):
        item = {
            "type": issue_type,
            "url": final_url,
            "lang": lang,
            "page_type": page_type,
            "severity": SEVERITY.get(issue_type, "low"),
            "label": LABEL.get(issue_type, issue_type),
            "current_value": current[:300] if current else "",
            "status": "pending",
        }
        if extra:
            item.update(extra)
        issues.append(item)

    # ── Meta title ──────────────────────────────────────────
    if title:
        if len(title) < 30:
            add("meta_title_too_short", title, {"char_count": len(title), "min_chars": 30})
        if len(title) > 60:
            add("meta_title_too_long", title, {"char_count": len(title), "max_chars": 60})
        if "cadomotus" not in title.lower() and "cádomotus" not in title.lower():
            add("meta_title_no_brand", title)

    # ── Meta description ─────────────────────────────────────
    if not meta_desc:
        add("meta_desc_missing", "")
    else:
        if len(meta_desc) > 160:
            add("meta_desc_too_long", meta_desc, {"char_count": len(meta_desc), "max_chars": 160})
        elif len(meta_desc) < 70:
            add("meta_desc_too_short", meta_desc, {"char_count": len(meta_desc), "min_chars": 70})

    # ── OG tags ──────────────────────────────────────────────
    if not og.get("og:title"):
        add("og_title_missing", "")
    og_img = og.get("og:image") or og.get("og:image:secure_url", "")
    if not og_img:
        add("og_image_missing", "")
    elif og_img.startswith("http://"):
        add("og_image_http", og_img)

    # ── H1 ───────────────────────────────────────────────────
    if not h1s and page_type not in ("home",):
        add("h1_missing", "")
    elif len(h1s) > 1:
        add("h1_multiple", " | ".join(h1s[:5]), {"h1_count": len(h1s)})

    # ── Canonical ────────────────────────────────────────────
    if not canonical:
        add("canonical_missing", "")

    # ── Hreflang ─────────────────────────────────────────────
    if not hreflangs:
        add("hreflang_missing", "")
    elif "x-default" not in hreflangs:
        add("hreflang_no_xdefault", ", ".join(hreflangs))

    # ── Schema / JSON-LD ─────────────────────────────────────
    valid_ld = []
    for block in ld_blocks:
        try:
            parsed_ld = json.loads(block)
            valid_ld.append(parsed_ld)
        except (json.JSONDecodeError, ValueError):
            add("schema_malformed", block[:150])

    if not valid_ld and page_type in ("product", "collection", "article"):
        add("schema_missing", "")

    return issues


# ─────────────────────────────────────────────────────────────
# C: Shopify API audit — SEO-velden via Admin API
# ─────────────────────────────────────────────────────────────

_PRODUCTS_SEO_QUERY = """
query getAllProductsSEO($cursor: String) {
  products(first: 50, query: "status:active", after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title
      descriptionHtml
      seo { title description }
    }
  }
}
"""

_COLLECTIONS_SEO_QUERY = """
query getAllCollectionsSEO($cursor: String) {
  collections(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id handle title
      descriptionHtml
      seo { title description }
      image { url }
    }
  }
}
"""

_ARTICLES_SEO_QUERY = """
query getAllArticlesSEO($cursor: String) {
  articles(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title handle
      blog { title handle }
      seo { title description }
      image { url }
      contentHtml
      publishedAt
      tags
    }
  }
}
"""

_PAGES_SEO_QUERY = """
query getAllPagesSEO($cursor: String) {
  pages(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title handle
      seo { title description }
      body
    }
  }
}
"""

_REDIRECTS_QUERY = """
query getAllRedirects($cursor: String) {
  urlRedirects(first: 250, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      path
      target
    }
  }
}
"""

_PRODUCT_IMAGES_COUNT_QUERY = """
query getProductImageCounts($cursor: String) {
  products(first: 50, query: "status:active", after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id title handle
      tags
      media(first: 50) {
        nodes {
          ... on MediaImage { id }
        }
      }
    }
  }
}
"""


def _strip_html(html: str) -> str:
    """Verwijder HTML-tags voor lengte-check."""
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _shopify_product_seo_issues() -> list:
    issues = []
    cursor = None
    page = 0

    while True:
        res = _graphql(_PRODUCTS_SEO_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify product-query fout: %s", res["error"])
            break

        products = res.get("products", {}) or {}
        for p in (products.get("nodes") or []):
            pid = p.get("id", "")
            handle = p.get("handle", "")
            title = p.get("title", "")
            seo = p.get("seo") or {}
            seo_title = (seo.get("title") or "").strip()
            seo_desc = (seo.get("description") or "").strip()
            desc_html = p.get("descriptionHtml") or ""
            desc_plain = _strip_html(desc_html)
            url = f"{BASE}/products/{handle}"

            def add_shopify(issue_type: str, current: str = ""):
                issues.append({
                    "type": issue_type,
                    "url": url,
                    "lang": "en",
                    "page_type": "product",
                    "severity": SEVERITY.get(issue_type, "medium"),
                    "label": LABEL.get(issue_type, issue_type),
                    "current_value": current[:300],
                    "shopify_resource_id": pid,
                    "shopify_handle": handle,
                    "shopify_title": title,
                    "status": "pending",
                })

            if not seo_title:
                add_shopify("shopify_seo_title_missing", "")
            else:
                if "cadomotus" not in seo_title.lower() and "cádomotus" not in seo_title.lower():
                    add_shopify("shopify_seo_title_no_brand", seo_title)

            if not seo_desc:
                add_shopify("shopify_seo_desc_missing", "")
            elif len(seo_desc) > 160:
                add_shopify("shopify_seo_desc_too_long", seo_desc)

            if not desc_plain or len(desc_plain) < 50:
                add_shopify("shopify_no_description", desc_plain[:100])

        page_info = products.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        page += 1
        log.info("[full_audit] Shopify products pagina %d — %d issues tot nu toe", page, len(issues))
        time.sleep(0.3)

    log.info("[full_audit] Shopify products: %d issues", len(issues))
    return issues


def _shopify_collection_seo_issues() -> list:
    issues = []
    cursor = None

    while True:
        res = _graphql(_COLLECTIONS_SEO_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify collection-query fout: %s", res["error"])
            break

        cols = res.get("collections", {}) or {}
        for c in (cols.get("nodes") or []):
            cid = c.get("id", "")
            handle = c.get("handle", "")
            title = c.get("title", "")
            seo = c.get("seo") or {}
            seo_title = (seo.get("title") or "").strip()
            seo_desc = (seo.get("description") or "").strip()
            desc_html = c.get("descriptionHtml") or ""
            desc_plain = _strip_html(desc_html)
            has_image = bool((c.get("image") or {}).get("url"))
            url = f"{BASE}/collections/{handle}"

            def add_col(issue_type: str, current: str = ""):
                issues.append({
                    "type": issue_type,
                    "url": url,
                    "lang": "en",
                    "page_type": "collection",
                    "severity": SEVERITY.get(issue_type, "medium"),
                    "label": LABEL.get(issue_type, issue_type),
                    "current_value": current[:300],
                    "shopify_resource_id": cid,
                    "shopify_handle": handle,
                    "shopify_title": title,
                    "status": "pending",
                })

            if not seo_title:
                add_col("shopify_seo_title_missing", "")
            else:
                if "cadomotus" not in seo_title.lower() and "cádomotus" not in seo_title.lower():
                    add_col("shopify_seo_title_no_brand", seo_title)

            if not seo_desc:
                add_col("shopify_seo_desc_missing", "")
            elif len(seo_desc) > 160:
                add_col("shopify_seo_desc_too_long", seo_desc)

            if not desc_plain or len(desc_plain) < 50:
                add_col("shopify_no_description", desc_plain[:100])

            if not has_image:
                add_col("shopify_collection_no_image", "")

        page_info = cols.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(0.3)

    log.info("[full_audit] Shopify collections: %d issues", len(issues))
    return issues


def _count_words(html: str) -> int:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return len(text.split())


def _shopify_article_seo_issues() -> list:
    """Blog-artikelen controleren op SEO-velden, afbeelding en content-dikte."""
    issues = []
    cursor = None

    while True:
        res = _graphql(_ARTICLES_SEO_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify articles-query fout: %s", res["error"])
            break

        articles = res.get("articles", {}) or {}
        for a in (articles.get("nodes") or []):
            aid = a.get("id", "")
            handle = a.get("handle", "")
            title = a.get("title", "")
            blog = a.get("blog") or {}
            blog_handle = blog.get("handle", "")
            seo = a.get("seo") or {}
            seo_title = (seo.get("title") or "").strip()
            seo_desc = (seo.get("description") or "").strip()
            has_image = bool((a.get("image") or {}).get("url"))
            word_count = _count_words(a.get("contentHtml") or "")
            url = f"{BASE}/blogs/{blog_handle}/{handle}"

            def add_art(issue_type: str, current: str = ""):
                issues.append({
                    "type": issue_type,
                    "url": url,
                    "lang": "en",
                    "page_type": "article",
                    "severity": SEVERITY.get(issue_type, "medium"),
                    "label": LABEL.get(issue_type, issue_type),
                    "current_value": current[:300],
                    "shopify_resource_id": aid,
                    "shopify_handle": handle,
                    "shopify_title": title,
                    "status": "pending",
                })

            if not seo_title:
                add_art("shopify_article_seo_title_missing", "")
            else:
                if "cadomotus" not in seo_title.lower() and "cádomotus" not in seo_title.lower():
                    add_art("shopify_article_no_brand", seo_title)

            if not seo_desc:
                add_art("shopify_article_seo_desc_missing", "")
            elif len(seo_desc) > 160:
                add_art("shopify_article_seo_desc_too_long", seo_desc[:160])

            if not has_image:
                add_art("shopify_article_no_image", "")

            if word_count < 300:
                add_art("shopify_article_thin_content", f"{word_count} woorden")

        page_info = articles.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(0.3)

    log.info("[full_audit] Shopify articles: %d issues", len(issues))
    return issues


def _shopify_page_seo_issues() -> list:
    """Shopify-pagina's controleren op SEO-velden en content-dikte."""
    issues = []
    cursor = None

    while True:
        res = _graphql(_PAGES_SEO_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify pages-query fout: %s", res["error"])
            break

        pages = res.get("pages", {}) or {}
        for p in (pages.get("nodes") or []):
            pid = p.get("id", "")
            handle = p.get("handle", "")
            title = p.get("title", "")
            seo = p.get("seo") or {}
            seo_title = (seo.get("title") or "").strip()
            seo_desc = (seo.get("description") or "").strip()
            word_count = _count_words(p.get("body") or "")
            url = f"{BASE}/pages/{handle}"

            def add_page(issue_type: str, current: str = ""):
                issues.append({
                    "type": issue_type,
                    "url": url,
                    "lang": "en",
                    "page_type": "page",
                    "severity": SEVERITY.get(issue_type, "medium"),
                    "label": LABEL.get(issue_type, issue_type),
                    "current_value": current[:300],
                    "shopify_resource_id": pid,
                    "shopify_handle": handle,
                    "shopify_title": title,
                    "status": "pending",
                })

            if not seo_title:
                add_page("shopify_page_seo_title_missing", "")
            else:
                if "cadomotus" not in seo_title.lower() and "cádomotus" not in seo_title.lower():
                    add_page("shopify_page_no_brand", seo_title)

            if not seo_desc:
                add_page("shopify_page_seo_desc_missing", "")
            elif len(seo_desc) > 160:
                add_page("shopify_page_seo_desc_too_long", seo_desc[:160])

            if word_count < 100:
                add_page("shopify_page_thin_content", f"{word_count} woorden")

        page_info = pages.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(0.3)

    log.info("[full_audit] Shopify pages: %d issues", len(issues))
    return issues


def _shopify_redirect_issues() -> list:
    """URL-redirects controleren op ketens (A→B→C) en verdachte targets."""
    issues = []
    cursor = None
    all_redirects = []

    while True:
        res = _graphql(_REDIRECTS_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify redirects-query fout: %s", res["error"])
            break

        redir = res.get("urlRedirects", {}) or {}
        all_redirects.extend(redir.get("nodes") or [])

        page_info = redir.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(0.3)

    # Bouw set van bekende redirect-paths voor keten-detectie
    redirect_paths = {r["path"].rstrip("/") for r in all_redirects}

    for r in all_redirects:
        path = r.get("path", "")
        target = r.get("target", "")
        rid = r.get("id", "")
        # Keten: target is ook een redirect-from-path
        target_path = target.rstrip("/")
        if target_path in redirect_paths or (
            target_path.startswith(BASE) and
            target_path[len(BASE):].rstrip("/") in redirect_paths
        ):
            issues.append({
                "type": "shopify_redirect_chain",
                "url": f"{BASE}{path}",
                "lang": "en",
                "page_type": "redirect",
                "severity": "medium",
                "label": LABEL["shopify_redirect_chain"],
                "current_value": f"{path} → {target}",
                "shopify_resource_id": rid,
                "shopify_handle": path,
                "shopify_title": f"Redirect: {path}",
                "status": "pending",
            })

    log.info("[full_audit] Shopify redirects: %d issues (van %d redirects)", len(issues), len(all_redirects))
    return issues


def _shopify_product_extra_issues() -> list:
    """Extra product-checks: weinig afbeeldingen + geen tags."""
    issues = []
    cursor = None

    while True:
        res = _graphql(_PRODUCT_IMAGES_COUNT_QUERY, {"cursor": cursor})
        if "error" in res:
            log.error("[full_audit] Shopify product-extra fout: %s", res["error"])
            break

        products = res.get("products", {}) or {}
        for p in (products.get("nodes") or []):
            pid = p.get("id", "")
            handle = p.get("handle", "")
            title = p.get("title", "")
            tags = p.get("tags") or []
            media_nodes = (p.get("media") or {}).get("nodes") or []
            image_count = len([m for m in media_nodes if m.get("id")])
            url = f"{BASE}/products/{handle}"

            def add_extra(issue_type: str, current: str = ""):
                issues.append({
                    "type": issue_type,
                    "url": url,
                    "lang": "en",
                    "page_type": "product",
                    "severity": SEVERITY.get(issue_type, "medium"),
                    "label": LABEL.get(issue_type, issue_type),
                    "current_value": current[:200],
                    "shopify_resource_id": pid,
                    "shopify_handle": handle,
                    "shopify_title": title,
                    "status": "pending",
                })

            if image_count < 3:
                add_extra("shopify_product_few_images", f"{image_count} afbeelding(en)")

            if not tags:
                add_extra("shopify_product_no_tags", "")

        page_info = products.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        time.sleep(0.3)

    log.info("[full_audit] Shopify product-extra: %d issues", len(issues))
    return issues


# ─────────────────────────────────────────────────────────────
# D: Coördinator
# ─────────────────────────────────────────────────────────────

def run_full_seo_audit(data_dir: str = "/data", status_ref: dict = None) -> dict:
    """Volledige site-brede SEO-audit. Resultaat opgeslagen als full_audit.json."""
    import datetime

    def _upd(info: dict):
        if status_ref is not None:
            status_ref.clear()
            status_ref.update(info)

    _upd({"status": "running", "phase": "sitemap", "pages_crawled": 0, "total": 0, "issues_found": 0})
    log.info("[full_audit] === Volledige SEO-audit gestart ===")

    # Fase 1: Shopify API checks (snel — geen crawl vereist)
    _upd({"status": "running", "phase": "shopify_products", "issues_found": 0})
    product_issues = _shopify_product_seo_issues()

    _upd({"status": "running", "phase": "shopify_collections", "issues_found": len(product_issues)})
    collection_issues = _shopify_collection_seo_issues()

    _upd({"status": "running", "phase": "shopify_articles", "issues_found": len(product_issues) + len(collection_issues)})
    article_issues = _shopify_article_seo_issues()

    _upd({"status": "running", "phase": "shopify_pages",
          "issues_found": len(product_issues) + len(collection_issues) + len(article_issues)})
    page_issues = _shopify_page_seo_issues()

    _upd({"status": "running", "phase": "shopify_redirects",
          "issues_found": len(product_issues) + len(collection_issues) + len(article_issues) + len(page_issues)})
    redirect_issues = _shopify_redirect_issues()

    _upd({"status": "running", "phase": "shopify_product_extra",
          "issues_found": sum(len(x) for x in [product_issues, collection_issues, article_issues, page_issues, redirect_issues])})
    product_extra_issues = _shopify_product_extra_issues()

    shopify_issues = (product_issues + collection_issues + article_issues +
                      page_issues + redirect_issues + product_extra_issues)
    log.info("[full_audit] Shopify-issues totaal: %d", len(shopify_issues))

    # Fase 2: Sitemap-URLs ophalen
    _upd({"status": "running", "phase": "sitemap", "issues_found": len(shopify_issues)})
    all_urls = fetch_all_sitemap_urls()

    total = len(all_urls)
    _upd({"status": "running", "phase": "html_crawl", "pages_crawled": 0,
          "total": total, "issues_found": len(shopify_issues)})

    # Fase 3: HTML-crawl (3 workers — hoger veroorzaakt 429 bij Shopify/Cloudflare)
    html_issues = []
    crawled = 0

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(analyze_page, url): url for url in all_urls}
        for future in as_completed(futures):
            try:
                page_issues = future.result()
                html_issues.extend(page_issues)
            except Exception as e:
                log.warning("[full_audit] Pagina-fout: %s", e)
            crawled += 1
            if crawled % 50 == 0:
                log.info("[full_audit] Gecrawled: %d/%d pagina's, %d issues",
                         crawled, total, len(html_issues))
                _upd({"status": "running", "phase": "html_crawl",
                      "pages_crawled": crawled, "total": total,
                      "issues_found": len(shopify_issues) + len(html_issues)})

    # Combineer en sla op
    all_issues = shopify_issues + html_issues
    log.info("[full_audit] Totaal issues: %d", len(all_issues))

    # Voeg unieke ID's toe
    for idx, issue in enumerate(all_issues):
        issue["id"] = f"issue-{idx:04d}"

    # Samenvatting per type
    type_counts: dict = {}
    for issue in all_issues:
        t = issue["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = {
        "crawled_at": now,
        "total_issues": len(all_issues),
        "pages_crawled": crawled,
        "issues": all_issues,
        "summary_by_type": type_counts,
        "summary_by_severity": {
            "high":   sum(1 for i in all_issues if i.get("severity") == "high"),
            "medium": sum(1 for i in all_issues if i.get("severity") == "medium"),
            "low":    sum(1 for i in all_issues if i.get("severity") == "low"),
        },
    }

    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, "full_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    log.info("[full_audit] === Audit klaar: %s issues opgeslagen in %s ===", len(all_issues), out_path)
    _upd({
        "status": "done",
        "phase": "done",
        "crawled_at": now,
        "total_issues": len(all_issues),
        "pages_crawled": crawled,
        "summary_by_type": type_counts,
    })
    return result
