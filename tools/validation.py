"""Pre-flight validatie voor het wekelijkse rapport.

Het doel: verhinderen dat een slecht gestelde fixes-lijst (duplicates, verkeerde
lengtes, category-clashes, missende velden) via de preview-mail naar buiten gaat.
Dit is de hard-enforcement die de prompts niet kunnen garanderen — het model ziet
een error-JSON terug en moet zijn fixes herschrijven.
"""

from typing import Iterable, Tuple

META_TITLE_RANGE = (50, 60)
META_DESC_RANGE = (140, 160)
META_TITLE_HARD = (40, 70)
META_DESC_HARD = (120, 175)

# Lengte-regels per niet-meta veld. (ideaal_min, ideaal_max, hard_min, hard_max).
FIELD_LENGTH_RULES = {
    "meta_title":            (50, 60, 40, 70),
    "meta_description":      (140, 160, 120, 175),
    "image_alt":             (40, 100, 5, 125),     # Beschrijvend, niet keyword-stuffing
    "collection_body":       (200, 600, 80, 1500),  # Korte intro, niet artikel
    "page_body":             (300, 2500, 100, 5000),
}

# Welke field-types zijn auto-applybaar (bulk approve flow) versus alleen suggestie
AUTO_APPLY_FIELDS = {"meta_title", "meta_description", "image_alt", "collection_body"}
SUGGESTION_ONLY_FIELDS = {"page_body", "product_body"}  # Per item review nodig
ALL_VALID_FIELDS = AUTO_APPLY_FIELDS | SUGGESTION_ONLY_FIELDS


# Canonieke categorie-labels voor Cadomotus. In de actuele Shopify-store is
# `productType` LEEG voor alle producten — categorie zit in tags (bv. "helmet",
# "bag", "boot", en "col-tri-*"/"col-sk8-*"/"col-ice-*"-prefixes) en in de
# collection-handles (bv. "inline-speed-skating-boots", "ice-speed-skating-helmets",
# "triathlon-cycling-shoes"). Mapping ondersteunt al deze signalen.
CADOMOTUS_CATEGORY_MAP = {
    # Shoes
    "triathlon cycling shoe": "shoe",
    "cycling shoe": "shoe",
    "shoes": "shoe",
    "shoe": "shoe",
    "fietsschoen": "shoe",
    "triathlon-cycling-shoes": "shoe",
    "cycling-shoes": "shoe",
    # Helmets (Cadomotus tag = `helmet`, collections = `*-helmets`)
    "aero helmet": "helmet",
    "helmet": "helmet",
    "helm": "helmet",
    "road helmet": "helmet",
    "ice-speed-skating-helmets": "helmet",
    "inline-speed-skating-helmets": "helmet",
    "triathlon-helmets": "helmet",
    "aero-helmets": "helmet",
    # Bags / trolleys (tag = `bag`, collections = `*-bags`)
    "transition bag": "bag",
    "race bag": "bag",
    "bag": "bag",
    "hybrid trolley": "bag",
    "trolley": "bag",
    "tas": "bag",
    "triathlon-transition-bag": "bag",
    "transition-bags": "bag",
    "ice-speed-skate-bags": "bag",
    "inline-speed-skate-bags": "bag",
    "speed-skate-bags": "bag",
    "skate-bags": "bag",
    # Inline speed skates (tag = `boot`+`col-sk8-*`, collections = `inline-*`)
    "inline speed skate": "inline",
    "inline skate": "inline",
    "skeeler": "inline",
    "skeelers": "inline",
    "inline-speed-skating": "inline",
    "inline-speed-skating-boots": "inline",
    "inline-speed-skating-frames": "inline",
    "inline-speed-skating-wheels": "inline",
    "skeelers-en-inline-skates": "inline",
    # Ice speed skates (col-ice-* + ice-speed-skating-*)
    "ice speed skate": "ice",
    "ice skate": "ice",
    "ijsschaats": "ice",
    "klapschaats": "ice",
    "ice-speed-skating": "ice",
    "ice-speed-skating-boots": "ice",
    "ice-speed-skating-blades": "ice",
    # Onderdelen (wheels, frames, blades) — vaak generieke onderdelen die op
    # meerdere skates passen. Krijgen aparte categorie zodat ze geen schoen-copy
    # of helm-copy krijgen.
    "wheel": "part",
    "wheels": "part",
    "frame": "part",
    "frames": "part",
    "blade": "part",
    "blades": "part",
    "boot": "part",  # losse boot zonder frame/wheels = onderdeel
    "insoles": "part",
}

# Termen die NOOIT in de copy van een andere categorie horen te staan.
# Lowercase, substring match. Gebruiken we om te detecteren of een tas-fix per
# ongeluk fietsschoen-taal gebruikt (het oorspronkelijke productie-incident).
CATEGORY_FORBIDDEN_TERMS = {
    "shoe": [],  # schoen-termen zijn voor schoenen juist correct
    "bag": ["carbon sole", "koolstofzool", "cycling shoe", "fietsschoen", "radschuh",
            "chaussure vélo", "chaussure velo", "stack height", "pedal", "wattbesparing",
            "watt savings", "triathlon cycling", "aerodynamic helmet", "aerohelm"],
    "helmet": ["carbon sole", "koolstofzool", "cycling shoe", "fietsschoen", "radschuh",
               "compartment", "vakindeling", "compartiment", "transition bag"],
    "inline": ["triathlon cycling", "aero helmet", "aerohelm", "transition bag",
               "cycling shoe", "fietsschoen", "ice skate", "ijsschaats"],
    "ice": ["triathlon cycling", "aero helmet", "aerohelm", "transition bag",
            "cycling shoe", "fietsschoen", "inline skate", "skeeler"],
    "part": ["complete shoe", "complete helmet", "transition bag",
             "carbon sole" if False else "carbon-sole-as-part-feature-allowed"],  # parts mogen carbon noemen
}


def categorize_product(
    product_type: str = "",
    tags: Iterable[str] = (),
    collection_handles: Iterable[str] = (),
) -> str:
    """Map Shopify productType + tags + collection-handles naar een Cadomotus-
    categorie. In de actuele store is productType leeg, dus tags en collections
    zijn de echte signalen. Tolerant voor hoofdletters en `col-*` prefixes."""
    candidates = []
    if product_type:
        candidates.append(product_type)
    candidates.extend(tags or [])
    candidates.extend(collection_handles or [])

    for raw in candidates:
        if not raw:
            continue
        key = raw.strip().lower()
        # Cadomotus gebruikt `col-tri-*` / `col-sk8-*` / `col-ice-*` prefix-tags
        # voor sport-niche maar deze zijn niet specifiek genoeg voor categorie
        # — sla over en kijk naar de echte productcategorie-signalen.
        if key.startswith("col-tri-") or key.startswith("col-sk8-") or key.startswith("col-ice-"):
            continue
        if key in CADOMOTUS_CATEGORY_MAP:
            return CADOMOTUS_CATEGORY_MAP[key]
        # Substring-match op bekende sleutels (voor "ice-speed-skating-helmets"
        # → "helmet" via "helmet" substring).
        for needle, cat in CADOMOTUS_CATEGORY_MAP.items():
            if needle in key:
                return cat
    return "unknown"


def _len_issue(label: str, text: str, ideal: Tuple[int, int], hard: Tuple[int, int]) -> str:
    n = len(text.strip())
    if n < hard[0] or n > hard[1]:
        return f"{label} {n} tekens BUITEN hard limit {hard[0]}-{hard[1]}"
    if n < ideal[0] or n > ideal[1]:
        return f"{label} {n} tekens buiten ideaal {ideal[0]}-{ideal[1]}"
    return ""


def validate_fixes(fixes: list, expected_count: int = 22) -> dict:
    """Valideer de fixes-array vóór gmail_send_report. Retourneert een dict met
    errors (blokkerend) en warnings (loggen). Doel ~22 (gemiddeld 20-25)."""
    errors: list = []
    warnings: list = []

    if not isinstance(fixes, list):
        return {"valid": False, "errors": ["fixes is geen array"], "warnings": []}

    # Soft window: 15-30 is OK, daarbuiten warning. Onder 12 hard fail.
    if len(fixes) < 12:
        errors.append(f"Te weinig fixes: {len(fixes)} (minimum 12, doel ~{expected_count})")
    elif len(fixes) < 15 or len(fixes) > 30:
        warnings.append(f"{len(fixes)} fixes (doel ~{expected_count}, range 15-30)")

    seen_url_field: set = set()
    per_lang_texts = {"EN": set(), "NL": set(), "DE": set(), "FR": set()}
    categories_seen: dict = {}
    fields_seen: dict = {}  # tel hoeveel per field-type (rapport-spreiding)

    required_keys = ("id", "url", "field", "resource_id", "proposed_values")
    for i, fix in enumerate(fixes, start=1):
        if not isinstance(fix, dict):
            errors.append(f"Fix #{i}: geen object")
            continue

        missing = [k for k in required_keys if not fix.get(k)]
        if missing:
            errors.append(f"Fix #{i}: ontbrekende velden {missing}")
            continue

        # Uniciteit op URL+field combinatie. Een product mag wel meta_title én
        # image_alt hebben — dat is twee fixes met dezelfde URL maar ander field.
        url = fix["url"]
        url_field = (url, fix.get("field", ""))
        if url_field in seen_url_field:
            errors.append(f"Fix #{i}: duplicate URL+field combinatie {url_field}")
        seen_url_field.add(url_field)

        # Field enum.
        field = fix["field"]
        if field not in ALL_VALID_FIELDS:
            errors.append(
                f"Fix #{i}: field {field!r} onbekend. Geldig: {sorted(ALL_VALID_FIELDS)}"
            )
            continue
        fields_seen[field] = fields_seen.get(field, 0) + 1

        # image_alt is store-wide (geen vertaling). Andere zijn meertalig.
        single_lang_field = (field == "image_alt")

        pv = fix.get("proposed_values") or {}
        if not isinstance(pv, dict):
            errors.append(f"Fix #{i}: proposed_values is geen object")
            continue

        if single_lang_field:
            # Verwacht alleen "EN" key (of "default") met de alt-tekst.
            text = (pv.get("EN") or pv.get("default") or "").strip()
            if not text:
                errors.append(f"Fix #{i}: image_alt heeft geen tekst (key 'EN' of 'default')")
                continue
            filled = ["EN"]
        else:
            filled = [lang for lang in ("EN", "NL", "DE", "FR") if (pv.get(lang) or "").strip()]
            if len(filled) < 2:
                errors.append(f"Fix #{i}: minimaal 2 talen vereist, gevuld: {filled}")

        # Lengte-rules per veld-type.
        rule = FIELD_LENGTH_RULES.get(field)
        ideal = (rule[0], rule[1]) if rule else (0, 99999)
        hard = (rule[2], rule[3]) if rule else (0, 99999)

        for lang in filled:
            text = pv[lang].strip()
            issue = _len_issue(f"Fix #{i} {field} {lang}", text, ideal, hard)
            if issue:
                (errors if "BUITEN hard" in issue else warnings).append(issue)
            # Uniek per taal — alleen voor meta-velden, alt-text mag herhaling.
            if not single_lang_field:
                if text in per_lang_texts[lang]:
                    errors.append(f"Fix #{i}: duplicate {lang}-tekst (botst met eerdere fix)")
                per_lang_texts[lang].add(text)

        # Category-fit: als er category-context is, check op clash-termen.
        category = (fix.get("category") or fix.get("product_type") or "").strip().lower()
        canon = CADOMOTUS_CATEGORY_MAP.get(category, category or "unknown")
        categories_seen[canon] = categories_seen.get(canon, 0) + 1
        forbidden = CATEGORY_FORBIDDEN_TERMS.get(canon, [])
        if forbidden:
            joined = " ".join(pv.values()).lower()
            hits = [t for t in forbidden if t in joined]
            if hits:
                errors.append(
                    f"Fix #{i}: category-clash — {canon!r} copy bevat verboden termen {hits}"
                )

    # Categorie-spreiding: minstens 3 distinct (excl. unknown) voor diversiteit.
    distinct = {c for c in categories_seen if c and c != "unknown"}
    if len(distinct) < 3:
        warnings.append(
            f"Weinig categorie-spreiding: slechts {len(distinct)} distinct categorieën "
            f"({sorted(distinct)}). Streef naar minstens 3."
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "categories": categories_seen,
        "fields": fields_seen,
        "count": len(fixes),
    }
