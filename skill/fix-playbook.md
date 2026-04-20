# Fix Playbook — Cadomotus

Hoe elk type SEO-issue op te lossen. Lees keywords.md voor doelzoekwoorden per taal.

## Algemene regels voor elke fix

1. Genereer altijd vanuit EN als basis, dan NL/DE/FR
2. Gebruik zoekwoorden uit keywords.md — 1 primair per veld, niet herhalen
3. Tel altijd het aantal tekens na voor meta titles (50-60) en meta descriptions (140-160)
4. Nooit dubbele aanhalingstekens in meta-velden — gebruik enkele quotes of geen quotes
5. Toon altijd de volledige voorgestelde tekst VOOR de API-call, nooit achteraf
6. Na goedkeuring: EN via productUpdate/collectionUpdate/pageUpdate, NL/DE/FR via translationsRegister

---
     
## Fix A: Meta Title toevoegen of verbeteren

### Wanneer
- seo.title is leeg
- seo.title is generiek ("Shop All Products", "Helmets – cadomotus.com", etc.)
- seo.title langer dan 65 tekens (wordt afgeknipt in Google)
- seo.title bevat geen herkenbaar zoekwoord

### Template per resource-type

**Product:**
```
[Specifieke productnaam] | Cadomotus
[Specifieke productnaam] — [korte USP] | Cadomotus
```

**Collectie:**
```
[Categorie zoekwoord] | Cadomotus
[Categorie zoekwoord] — CarbonShell | Cadomotus
```

**Pagina:**
```
[Paginatitel specifiek] | Cadomotus
```

### Voorbeelden per taal

Product "Chrono Triathlon Shoe":
```
EN: "Chrono Triathlon Cycling Shoe | Cadomotus"            (44 tekens) — voeg USP toe als ruimte
EN: "Chrono Triathlon Shoe — Carbon Speed | Cadomotus"     (52 tekens) — beter
NL: "Chrono Triathlon Fietsschoen — CarbonShell | Cadomotus" (57 tekens)
DE: "Chrono Triathlon Radschuh — CarbonShell | Cadomotus"  (54 tekens)
FR: "Chrono Chaussure Velo Triathlon | Cadomotus"          (46 tekens)
```

Collectie "Triathlon Cycling Shoes":
```
EN: "Triathlon Cycling Shoes — CarbonShell | Cadomotus"    (53 tekens)
NL: "Triathlon Fietsschoenen — CarbonShell | Cadomotus"    (53 tekens)
DE: "Triathlon Radsportschuhe — CarbonShell | Cadomotus"   (53 tekens)
FR: "Chaussures Velo Triathlon — CarbonShell | Cadomotus"  (54 tekens)
```

Collectie "All Products" (generiek probleem):
```
EN: "Triathlon Gear — Shoes, Helmets & Bags | Cadomotus"   (54 tekens)
NL: "Triathlon Uitrusting — Schoenen, Helmen & Tassen | Cadomotus" (60 tekens)
DE: "Triathlon Ausrustung — Schuhe, Helme & Taschen | Cadomotus"   (57 tekens)
FR: "Equipement Triathlon — Chaussures, Casques & Sacs | Cadomotus" (60 tekens)
```

---

## Fix B: Meta Description toevoegen

### Wanneer
- seo.description is leeg
- seo.description < 100 tekens (te kort)
- seo.description > 170 tekens (wordt afgeknipt)

### Structuur (altijd deze volgorde)
`[Primaire benefit] + [Technisch kenmerk of USP] + [Zachte CTA]`

### Templates per taal

**EN:**
Structuur: `[Product feature]. [Engineering USP]. [Soft CTA.]`
```
"[Product] for maximum triathlon speed. CarbonShell carbon sole transfers 100% power to
the pedal. Shop now."
```

**NL:**
Structuur: `[Product voordeel]. [Engineering USP]. [Zachte CTA.]`
```
"[Product] voor maximale triathlon snelheid. CarbonShell koolstofzool voor directe
krachtoverbrenging. Ontdek nu."
```

**DE:**
Structuur: `[Produkt Vorteil]. [Engineering USP]. [Schwache CTA.]`
```
"[Produkt] fur maximale Triathlon-Geschwindigkeit. CarbonShell Carbonsohle fur direkten
Kraftubertrag. Jetzt entdecken."
```

**FR:**
Structuur: `[Produit avantage]. [Engineering USP]. [CTA doux.]`
```
"[Produit] pour la vitesse maximale en triathlon. Semelle CarbonShell pour transfert de
puissance direct. Decouvrez maintenant."
```

### Concrete voorbeelden per productcategorie

**Triathlon fietsschoenen:**
```
Product "Chrono Aero" (€479, top-of-line):
EN: "CarbonShell™ triathlon cycling shoe with 3-9 watt aero saving. Ultra-stiff carbon
     sole, precision fit. Wind tunnel tested. Shop now."
     (147 tekens)

NL: "CarbonShell™ triathlon fietsschoen met 3-9 watt aerobesparing. Koolstofzool,
     precise pasvorm. Windtunnel getest. Ontdek nu."
     (136 tekens)

DE: "CarbonShell™ Triathlon-Radschuh mit 3-9 Watt Aeroeinsparung. Ultrasteife
     Carbonsohle, Prazisionspassform. Im Windkanal getestet. Jetzt entdecken."
     (156 tekens)

FR: "Chaussure triathlon CarbonShell™ avec 3-9 watts d'economie aero. Semelle carbone
     rigide, fit precis. Teste en soufflerie. Decouvrez."
     (143 tekens)
```

```
Product "Worldcup 4E" (€229, brede leest):
EN: "Cadomotus triathlon cycling shoe in 4E wide fit. CarbonShell™ carbon sole for
     maximum power transfer. Heat-moldable for a personalized fit. Shop now."
     (158 tekens)

NL: "Cadomotus triathlon fietsschoen in brede 4E pasvorm. CarbonShell™ koolstofzool
     voor maximaal vermogen. Warmvormbaar voor perfect comfort. Ontdek nu."
     (157 tekens)
```

**Helmen (Aero Helmets):**
> Let op: CarbonShell™ is een zooltechnologie voor fietsschoenen/schaatsen — gebruik hem
> NIET in helmcopy. Helmen praten over aerodynamica, ventilatie, gewicht en windtunnel.
```
Product "Omega Aero Helmet" (€199):
EN: "Cadomotus Omega aero helmet — wind tunnel tested for triathlon racing. Lightweight
     construction, superior ventilation. Fits over most cycling glasses. Shop now."
     (158 tekens)

NL: "Cadomotus Omega aerohelm — windtunnel getest voor triathlon. Lichtgewicht
     constructie, optimale ventilatie. Past over de meeste fietsbrillen. Ontdek nu."
     (156 tekens)

DE: "Cadomotus Omega Aerohelm — im Windkanal getestet für Triathlon. Leichte
     Konstruktion, optimale Belüftung. Passt über die meisten Radbrillen. Jetzt entdecken."
     (159 tekens)

FR: "Casque aéro Cadomotus Omega — testé en soufflerie pour le triathlon. Construction
     légère, ventilation optimale. Compatible avec la plupart des lunettes. Découvrez maintenant."
     (158 tekens)
```

**Wedstrijdtassen (Race Bags):**
```
Product "Versatile 3.0" (€129):
EN: "Cadomotus Versatile 3.0 transition bag — dedicated compartments for helmet, shoes
     and nutrition. Built for race day. Everything accessible in under 10 seconds."
     (159 tekens)

NL: "Cadomotus Versatile 3.0 transitiontas — aparte vakken voor helm, schoenen en
     voeding. Gebouwd voor wedstrijddag. Alles bereikbaar in minder dan 10 seconden."
     (159 tekens)
```

**Skeeleren (Inline Speed Skating):**
```
Product "Agility-3 Skeeler" (€399):
EN: "Cadomotus Agility-3 inline speed skate with CarbonShell™ carbon sole. 25+ years
     of speed skating engineering in a competition-ready boot. Shop now."
     (151 tekens)

NL: "Cadomotus Agility-3 skeeler met CarbonShell™ koolstofzool. 25+ jaar
     schaatsengineering in een wedstrijdklare schoen. Ontdek nu."
     (141 tekens)

DE: "Cadomotus Agility-3 Inline Speed Skate mit CarbonShell™ Carbonsohle. 25+ Jahre
     Speedskating-Engineering im wettkampfbereiten Boot. Jetzt entdecken."
     (154 tekens)
```

**IJsschaatsen (Ice Speed Skating):**
```
Product "Ci1-Pro Boot":
EN: "Cadomotus Ci1-Pro ice speed skating boot. CarbonShell™ carbon sole engineered for
     elite competition — the same technology trusted by Olympic speed skaters."
     (155 tekens)

NL: "Cadomotus Ci1-Pro ijsschaatsschoen. CarbonShell™ koolstofzool voor elite
     wedstrijden — dezelfde technologie als bij Olympische schaatsers. Ontdek nu."
     (155 tekens)
```

**Collectie "Triathlon Cycling Shoes":**
```
EN: "25+ years of CarbonShell engineering from elite speed skating applied to triathlon
     performance cycling shoes. Maximum power, zero flex. Explore the range."
     (158 tekens)

NL: "25+ jaar CarbonShell engineering uit de schaatssport toegepast op triathlon
     fietsschoenen. Maximaal vermogen, nul flex. Ontdek de collectie."
     (153 tekens)
```

---

## Fix C: Image Alt-tekst bijwerken

### Wanneer
- altText is leeg (null of "")
- altText = "image" of ander generiek woord
- altText bevat geen productnaam

### Template
`[Productnaam] [kleur/variant/perspectief] - Cadomotus`

### Voorbeelden
```
"Chrono Triathlon Cycling Shoe white side view - Cadomotus"    (59 tekens)
"Chrono Triathlon Cycling Shoe black top view - Cadomotus"     (58 tekens)
"Chrono Aero Helmet white front view - Cadomotus"              (50 tekens)
"Transition Bag open with compartments - Cadomotus"            (51 tekens)
```

### Regels
- Altijd Engelstalig (Shopify heeft geen per-taal alt-tekst)
- Max 125 tekens
- Beschrijf wat er daadwerkelijk te zien is + productnaam + merk
- Nooit: "foto van", "afbeelding van", "image of", "photo of", "picture of"
- Varieer perspectief per image: side view, top view, sole view, lifestyle, detail

---

## Fix D: Collectiebeschrijving toevoegen of verbeteren

### Wanneer
- description is leeg
- description < 50 woorden

### Format
2-4 zinnen, technisch-sportief, bevat primair zoekwoord voor die collectie.
Structuur: [wat het is] + [technologische onderbouwing] + [voor wie]

### Voorbeelden

Collectie "Triathlon Cycling Shoes" — EN:
```
"Engineered for triathlon performance, Cadomotus cycling shoes apply 25+ years of
CarbonShell technology from elite speed skating. Ultra-stiff carbon soles transfer
maximum power to the pedal — no energy wasted. Built for athletes who race to win,
from sprint triathlons to full Ironman distances."
(294 tekens, ~55 woorden)
```

Collectie "Aero Helmets" — EN:
```
"Cadomotus aero helmets combine wind-tunnel tested aerodynamics with triathlon-specific
ventilation. CarbonShell construction keeps weight minimal while maximising structural
integrity. Designed for athletes who need every second."
(222 tekens, ~35 woorden)
```

Collectie "Transition Bags" — EN:
```
"Cadomotus transition bags are built for race day efficiency. Dedicated compartments
for helmet, shoes, and nutrition — everything accessible in seconds. From sprint to
Ironman, engineered to keep your transition sharp."
(228 tekens, ~37 woorden)
```

Collectie "Aero Helmets" — NL:
```
"Cadomotus aerohelmen combineren windtunnelgeteste aerodynamica met triathlon-specifieke
ventilatie. CarbonShell constructie houdt het gewicht minimaal. Ontworpen voor atleten
die elke seconde meetellen."
(227 tekens, ~30 woorden)
```

Collectie "Inline Speed Skating (Skeeleren)" — EN:
```
"Cadomotus inline speed skates apply the same CarbonShell™ carbon sole technology used
in Olympic speed skating. Ultra-stiff, precision fit, engineered for competition from
first sprint to finish line."
(234 tekens, ~34 woorden)
```

Collectie "Inline Speed Skating (Skeeleren)" — NL:
```
"Cadomotus skeelers passen dezelfde CarbonShell™ koolstofzooltechnologie toe als bij
Olympisch schaatsen. Ultra-stijf, precisie pasvorm, gebouwd voor wedstrijden van
eerste sprint tot finish."
(215 tekens, ~31 woorden)
```

Collectie "Ice Speed Skating (Schaatsen)" — EN:
```
"Cadomotus ice speed skating boots are built on 25+ years of elite CarbonShell™
engineering — the same foundation that supports a 1.1mm blade at 60 km/h. Maximum
energy transfer, race-proven construction."
(239 tekens, ~35 woorden)
```

Collectie "Ice Speed Skating (Schaatsen)" — NL:
```
"Cadomotus schaatsschoenen zijn gebouwd op 25+ jaar elite CarbonShell™ engineering —
dezelfde basis die een 1,1mm ijskling op 60 km/u ondersteunt. Maximale energieoverdracht,
wedstrijdproven constructie."
(235 tekens, ~32 woorden)
```

---

## Fix E: Hreflang implementeren (theme-aanpassing)

### Belangrijk
Hreflang zit in de Shopify theme liquid — NIET in de Shopify Admin API.
De agent kan dit niet zelf uitvoeren. Genereer de code en geef door aan eigenaar.

### Actie
1. Meld in rapport: "Hreflang ontbreekt — urgent duplicate content risico voor 4 talen"
2. Genereer de onderstaande liquid code
3. Instructie aan gebruiker: "Voeg dit toe in de `<head>` sectie van `theme.liquid`"

### Liquid code voor theme.liquid

```liquid
{% comment %} Hreflang tags — Cadomotus multilingual SEO {% endcomment %}
{%- assign current_path = request.path -%}
{%- assign base = 'https://cadomotus.com' -%}

{%- comment %} Strip taal-prefix als aanwezig {%- endcomment -%}
{%- assign clean_path = current_path
  | remove_first: '/nl'
  | remove_first: '/de'
  | remove_first: '/fr' -%}

<link rel="alternate" hreflang="en" href="{{ base }}{{ clean_path }}" />
<link rel="alternate" hreflang="nl" href="{{ base }}/nl{{ clean_path }}" />
<link rel="alternate" hreflang="de" href="{{ base }}/de{{ clean_path }}" />
<link rel="alternate" hreflang="fr" href="{{ base }}/fr{{ clean_path }}" />
<link rel="alternate" hreflang="x-default" href="{{ base }}{{ clean_path }}" />
```

### Stappen voor eigenaar
1. Shopify Admin → Online Store → Themes → Edit code
2. Open `layout/theme.liquid`
3. Zoek de `</head>` tag
4. Plak bovenstaande code VOOR `</head>`
5. Sla op en test via: https://www.google.com/webmasters/tools/richsnippets

---

## Fix F: Generieke meta title verbeteren

Specifiek voor bekende problemen op cadomotus.com:

### "Shop All Products — cadomotus.com"
Huidige title van /collections/all — te generiek.
```
EN: "Triathlon Gear — Shoes, Helmets & Bags | Cadomotus"    (54 tekens)
NL: "Triathlon Uitrusting — Schoenen & Helmen | Cadomotus"  (55 tekens)
DE: "Triathlon Ausrustung — Schuhe & Helme | Cadomotus"     (51 tekens)
FR: "Equipement Triathlon — Chaussures & Casques | Cadomotus" (57 tekens)
```

### "About us — cadomotus.com" / "Over ons — cadomotus.com"
```
EN: "About Cadomotus — 25 Years of Triathlon Engineering"   (54 tekens)
NL: "Over Cadomotus — 25 Jaar Triathlon Engineering"        (49 tekens)
DE: "Uber Cadomotus — 25 Jahre Triathlon-Engineering"       (52 tekens)
FR: "A propos de Cadomotus — 25 ans d'ingenierie triathlon" (57 tekens)
```

---

## Fix G: Volledig nieuw product SEO-setup

### Wanneer
Nieuw product heeft: geen meta title, geen meta description, geen alt-tekst.
Dit is het meest urgente scenario — een product zonder SEO bestaat niet in Google.

### Stappenplan

1. **Haal productinfo op** via Shopify API:
   - `title`, `product_type`, `tags`, `priceRange`, `bodyHtml` (voor features)

2. **Identificeer het primaire zoekwoord** via keywords.md op basis van product_type:
   - product_type = "Triathlon" → `triathlon cycling shoes` / `triathlon fietsschoenen`
   - product_type = "Helmet" → `aero triathlon helmet` / `triathlon aero helm`
   - product_type = "Bag" → `triathlon transition bag` / `wisseltas triathlon`
   - product_type = "Inline" → `inline speed skates` / `skeelers kopen`
   - product_type = "Ice" → `ice speed skates` / `schaatsschoenen kopen`

3. **Genereer EN meta title + description** (altijd als eerste)

4. **Genereer NL, DE, FR** op basis van EN-versie

5. **Genereer alt-tekst** voor elke productafbeelding (op basis van filename/positie)

6. **Toon alles als één blok** voordat je iets doet:

```
Nieuw product: [Productnaam] — volledige SEO-setup

META TITLE EN:  "[...]"  (XX tekens)
META TITLE NL:  "[...]"  (XX tekens)
META TITLE DE:  "[...]"  (XX tekens)
META TITLE FR:  "[...]"  (XX tekens)

META DESCRIPTION EN:  "[...]"  (XX tekens)
META DESCRIPTION NL:  "[...]"  (XX tekens)
META DESCRIPTION DE:  "[...]"  (XX tekens)
META DESCRIPTION FR:  "[...]"  (XX tekens)

ALT-TEKST afbeelding 1: "[...]"
ALT-TEKST afbeelding 2: "[...]"
[etc.]

Bevestig met "ja" om alles in één keer in te stellen.
```

7. Na "ja": voer alle mutations uit in volgorde:
   - productUpdate (EN seo velden)
   - translationsRegister (NL meta_title + meta_description)
   - translationsRegister (DE meta_title + meta_description)
   - translationsRegister (FR meta_title + meta_description)
   - productUpdateMedia (alt-teksten per image)

8. Bevestig: "Nieuw product [naam] — volledige SEO-setup gedaan (8 velden bijgewerkt)."

---

## Fix H: Bulk-fix workflow — "fix alles"

### Wanneer
Diederik zegt: "fix alles", "pak alle urgente dingen", "doe alle meta descriptions".

### Werkwijze: batches van 5, niet alles tegelijk

**Nooit meer dan 5 producten per keer zonder tussentijdse check.**

Stap 1: Stel vast wat de scope is
> "Er zijn [X] items zonder meta description (EN). Wil je dat ik:
> A) Eerst de [5] bestsellers doe en dan verder ga?
> B) Alles in batches van 5 doe met goedkeuring per batch?
> C) Alleen de producten die ik in één keer kan tonen?"

Stap 2: Toon batch van max 5 items als één overzicht
```
Batch 1 van [X] — Meta descriptions EN

#1 [Productnaam] — "..." (155 tekens)
#2 [Productnaam] — "..." (148 tekens)
#3 [Collectienaam] — "..." (152 tekens)
#4 [Productnaam] — "..." (159 tekens)
#5 [Productnaam] — "..." (143 tekens)

Bevestig met "ja" voor deze 5, of geef aanpassingen door.
```

Stap 3: Na "ja" → voer de 5 mutations uit → meld resultaat → vraag voor volgende batch:
> "Batch 1 gedaan. Wil je door met batch 2? ([N] items resterend)"

Stap 4: Sluit af met overzicht
> "Klaar. [X] meta descriptions toegevoegd in [Y] batches.
> Hreflang staat nog open — dat vereist een theme-aanpassing (code staat klaar).
> Aanbeveling volgende stap: NL-vertalingen van dezelfde [X] pagina's."

### Volgorde binnen bulk-fix

1. EN meta descriptions (alle pagina's zonder) — hoogste prioriteit, meeste impact
2. NL meta descriptions — Nederland is primaire markt Diederik
3. Meta titles verbeteren waar generiek (Shop All Products etc.)
4. DE + FR meta descriptions
5. Image alt-teksten (minst urgent van de vier)

---

## Kwaliteitsvalidatie — 20 Fixes per Rapport

### Waarom 20 STERKE fixes?

Diederik ontvangt wekelijks één rapport. Elke fix moet direct uitvoerbaar en impactvol zijn.
Geen filler, geen "misschien later", geen halve voorstellen.

### Checklist per fix

Voordat een fix in het rapport komt, moet hij voldoen aan:

| Check | Criterium | Voorbeeld goed | Voorbeeld fout |
|-------|-----------|----------------|----------------|
| Concrete tekst | proposed_value = exacte nieuwe tekst | "Chrono Triathlon Cycling Shoe — Carbon Speed \| Cadomotus" | "Meta title verbeteren" |
| Juiste lengte | Title 50-60, Description 140-160 tekens | 52 tekens ✓ | 38 tekens ✗ |
| Zoekwoord | Primair keyword uit keywords.md aanwezig | "triathlon cycling shoe" in title | Geen keyword |
| Taal-CTA | Zachte CTA in de juiste taal | NL: "Ontdek nu" / DE: "Jetzt entdecken" | EN CTA in NL tekst |
| Echte data | Concrete cijfers waar beschikbaar | "3-9 watt aerobesparing" | "sneller dan ooit" |
| Impact | estimated_clicks berekend | +23 clicks/mnd | Geen schatting |
| Tool | Juiste mutation vermeld | EN: shopify_update_seo | Verkeerde tool |
| Language | Taalcode meegegeven | "language": "DE" | Geen taal |

### Taalverdeling

Het rapport MOET fixes bevatten voor alle 4 talen:

| Taal | Minimum | Tool | CTA |
|------|---------|------|-----|
| EN | 5 fixes | shopify_update_seo | "Shop now" |
| NL | 5 fixes | shopify_update_translation (locale: nl) | "Ontdek nu" |
| DE | 4 fixes | shopify_update_translation (locale: de) | "Jetzt entdecken" |
| FR | 4 fixes | shopify_update_translation (locale: fr) | "Découvrez maintenant" |

### Prioriteringsvolgorde voor de 20 fixes

1. **GSC quick wins** (positie 4-15, lage CTR) — hoogste impact, laagste effort
2. **Bestsellers zonder meta** — directe omzet-impact
3. **Nieuwe producten zonder SEO** — onzichtbaar in Google
4. **Ontbrekende vertalingen** (DE/FR worden vaak vergeten)
5. **Generieke titles** ("Shop All Products") — makkelijke winst
6. **Te korte/lange descriptions** — onder 100 of boven 170 tekens
7. **Ontbrekende alt-tekst** op productafbeeldingen

### Anti-patronen (NOOIT doen)

- Fix zonder proposed_value ("meta description toevoegen" zonder de tekst erbij)
- Dezelfde URL+taal combinatie twee keer in de fixes array
- Alleen EN en NL fixes — DE en FR moeten er altijd bij
- Vage impact ("meer traffic") in plaats van concrete schatting (+N clicks)
- Marketing-taal in meta descriptions ("de beste", "uniek", "geweldig")
- Meta title zonder "| Cadomotus" aan het einde
