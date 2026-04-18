"""Cadomotus SEO Agent — draait op de VPS via Easypanel.

Usage:
    python agent.py --weekly-report     # Vrijdag 07:00 cron
    python agent.py --watch-replies     # Continu draaien als service
    python agent.py --auth              # Eenmalig: Google OAuth2 flow
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

from tools import ALL_TOOLS, TOOL_EXECUTORS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("cadomotus-agent")

client = Anthropic()

SKILL_DIR = Path(__file__).parent / "skill"
POLL_INTERVAL = int(os.getenv("REPLY_POLL_INTERVAL", 300))
MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")


def load_system_prompt() -> str:
    """Laad de volledige SEO skill als system prompt."""
    prompt_parts = []
    skill_files = [
        "system_prompt.md",
        "brand-voice.md",
        "fix-playbook.md",
        "keywords.md",
    ]
    for fname in skill_files:
        fpath = SKILL_DIR / fname
        if fpath.exists():
            prompt_parts.append(f"# === {fname} ===\n\n{fpath.read_text()}")
        else:
            log.warning("Skill file ontbreekt: %s", fpath)

    if not prompt_parts:
        log.error("Geen system prompt gevonden in %s", SKILL_DIR)
        sys.exit(1)

    return "\n\n---\n\n".join(prompt_parts)


def run_agent(task: str, system_prompt: str, max_turns: int = 20) -> str:
    """Voer de agentic loop uit: Claude roept tools aan tot hij klaar is."""
    messages = [{"role": "user", "content": task}]

    # Convert tool definitions voor Anthropic API format
    api_tools = []
    for t in ALL_TOOLS:
        api_tools.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        })

    for turn in range(max_turns):
        log.info("Agent turn %d/%d", turn + 1, max_turns)

        response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=system_prompt,
            tools=api_tools,
            messages=messages,
        )

        # Verzamel tekst output
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if response.stop_reason == "end_turn" or not tool_calls:
            final_text = "\n".join(text_parts)
            log.info("Agent klaar na %d turns", turn + 1)
            return final_text

        # Voer tool calls uit
        log.info("Agent roept %d tools aan: %s",
                 len(tool_calls),
                 [tc.name for tc in tool_calls])

        tool_results = []
        for tc in tool_calls:
            executor = TOOL_EXECUTORS.get(tc.name)
            if executor:
                try:
                    result = executor(tc.name, tc.input)
                    log.info("Tool %s: succes", tc.name)
                except Exception as e:
                    result = json.dumps({"error": str(e)})
                    log.error("Tool %s: fout — %s", tc.name, e)
            else:
                result = json.dumps({"error": f"Tool {tc.name} niet gevonden"})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    log.warning("Agent bereikt max turns (%d)", max_turns)
    return "\n".join(text_parts) if text_parts else "Agent kon de taak niet voltooien."


# ---------- Weekly report ----------

def weekly_report():
    """Genereer en verstuur het wekelijkse SEO-rapport."""
    log.info("=== Wekelijks SEO rapport starten ===")
    system_prompt = load_system_prompt()

    today = datetime.now().strftime("%Y-%m-%d")

    task = f"""Het is {today}, vrijdagochtend. Genereer het wekelijkse SEO-rapport.

ABSOLUUT BELANGRIJKSTE REGEL — PREVIEW FIRST:
Deze run MAG NIET direct naar Diederik sturen. Je stuurt ALTIJD eerst een preview
naar Maarten (preview=true). Maarten controleert, keurt goed, en pas daarna — in een
volgende run — wordt het echte rapport naar Diederik gestuurd (preview=false).

Als je gmail_send_report aanroept met preview=false zonder goedkeuring: FOUT. Altijd preview=true.

Doe het volgende stap voor stap:

1. Haal GSC search analytics op voor de afgelopen 7 dagen (vergelijk met de 7 dagen daarvoor).
2. Haal quick wins op — pagina's met positie 4-15 en lage CTR (max 20).
3. Haal de nieuwste producten op uit Shopify en check welke geen SEO hebben.
4. Check PageSpeed voor de homepage (cadomotus.com) op mobile.
5. Check ALLE 4 TALEN (EN, NL, DE, FR) — verzamel kandidaten:
   - Tot 20 kandidaat-issues PER TAAL (dus potentieel 80 kandidaten totaal).
   - Haal vertalingen op via shopify_get_translations voor NL, DE en FR.
   - Ontbrekende NL/DE/FR meta's zijn kandidaten, net als zwakke EN meta's.
6. Scoor en selecteer de TOP 20 STERKSTE fixes uit alle ~80 kandidaten.
7. Stuur als PREVIEW via gmail_send_report met preview=true.

SELECTIE-STRATEGIE — 20 PAGINA'S × 4 TALEN:
Nieuw datamodel: 1 fix = 1 pagina met voorstellen voor alle 4 talen tegelijk.
20 fixes × tot 4 talen per fix = potentieel 80 daadwerkelijke meta-updates.
Diederik klikt 20x Goedkeuren en alle talen worden tegelijk bijgewerkt.

- Fase A: identificeer 20 UNIEKE PAGINA'S met de grootste SEO-impact (niet 20 taal-varianten).
- Fase B: bereken impact score per pagina:
    impact = (impressies × (verwachte_CTR - huidige_CTR)) + bestseller_bonus
    Som over alle talen per pagina — zo tellen slechte vertalingen mee in de prioritering.
- Fase C: voor elke van de 20 pagina's, genereer voorstellen voor:
    * EN (via shopify_update_seo)
    * NL (via shopify_update_translation locale=nl)
    * DE (via shopify_update_translation locale=de)
    * FR (via shopify_update_translation locale=fr)
  Minimaal 2 talen per pagina, liefst alle 4.
- Fase D: voeg elk samen tot 1 fix-object met proposed_values: {EN, NL, DE, FR}.

BELANGRIJK — FIXES REGELS:
- Stuur ALTIJD exact 20 fixes mee. Elke fix = 1 pagina.
- Elke fix heeft UNIEKE pagina-URL. Geen duplicaten.
- Elke fix heeft proposed_values met minimaal 2 talen, liefst alle 4 (EN/NL/DE/FR).
- field is OF "meta_title" OF "meta_description" (1 veld per fix — aparte fix per veld per pagina als beide moeten veranderen).
- Elke fix heeft een uniek id (bijv. "fix-1", "fix-2", etc.).

KWALITEITSEISEN PER FIX — elke fix moet STERK zijn:
- proposed_values bevat EXACTE teksten per taal. Geen placeholders.
- Meta titles: 50-60 tekens per taal, eindigt op "| Cadomotus".
- Meta descriptions: 140-160 tekens per taal, structuur: [benefit] + [technisch kenmerk] + [CTA].
- Correcte taal-CTA: EN "Shop now" | NL "Ontdek nu" | DE "Jetzt entdecken" | FR "Découvrez".
- Gebruik ECHTE data: windtunnel, wattbesparing, gewicht — geen vage claims.
- estimated_clicks = som van verwachte extra clicks/mnd over alle talen.
- ON-BRAND: technisch-sportief, CarbonShell™, geen superlatieven (zie brand-voice.md).

LAATSTE STAP — DIT MOET JE DOEN (ANDERS IS DE RUN MISLUKT):
Roep gmail_send_report aan. Dit is verplicht — zonder deze call wordt er niets verstuurd.

Parameters:
- date: "{today}"
- subject: "Cadomotus SEO — {today} | 20 verbeterpunten (EN/NL/DE/FR)"
- performance: object met GSC deltas
- fixes: array van exact 20 fix-objecten. Elk fix-object bevat:
    * id (uniek, bijv. "fix-1")
    * url (echte Shopify product/collection URL — gebruik letterlijk het handle veld uit shopify_get_products)
    * field ("meta_title" of "meta_description")
    * resource_type ("product", "collection", of "page")
    * resource_id (Shopify GID, bijv. "gid://shopify/Product/123...")
    * current_values: {EN: "...", NL: "...", DE: "...", FR: "..."} (mag missende talen bevatten)
    * proposed_values: {EN: "...", NL: "...", DE: "...", FR: "..."} (minimaal 2 talen, liefst 4)
    * primary_keyword, position, ctr, impressions, estimated_clicks
- preview: true  ← BELANGRIJK: altijd true voor veiligheid

De tool stuurt dan automatisch naar maarten@thesystem.nl met "[PREVIEW]" prefix.
NOOIT preview=false zonder expliciete goedkeuring.

Als je onvoldoende data hebt voor 20 fixes: stuur alsnog gmail_send_report met de fixes
die je WEL hebt, en vermeld in text_summary hoeveel er ontbreken en waarom. Beter een
onvolledige preview dan geen mail.
"""

    result = run_agent(task, system_prompt, max_turns=40)
    log.info("Rapport resultaat: %s", result[:500])
    if "gmail_send_report" not in result and "verzonden" not in result.lower() and "sent" not in result.lower():
        log.warning("Mogelijk mail NIET verstuurd — agent output bevat geen verzend-bevestiging")


# ---------- Reply watcher ----------

def watch_replies():
    """Poll n8n elke X minuten op replies van Diederik."""
    log.info("=== Reply watcher gestart (interval: %ds) ===", POLL_INTERVAL)
    system_prompt = load_system_prompt()

    while True:
        try:
            _check_and_handle_replies(system_prompt)
        except Exception as e:
            log.error("Fout bij reply check: %s", e, exc_info=True)

        log.info("Volgende check over %d seconden...", POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)


def _check_and_handle_replies(system_prompt: str):
    """Check op nieuwe replies en laat de agent ze afhandelen."""
    from tools.gmail import execute_gmail_tool

    replies_json = execute_gmail_tool("gmail_check_replies", {"max_results": 20})
    replies = json.loads(replies_json)

    if not replies:
        log.info("Geen nieuwe replies gevonden.")
        return

    log.info("Gevonden: %d nieuwe replies", len(replies))

    for reply in replies:
        log.info("Reply van %s: %s", reply["from"], reply["body"][:100])

        task = f"""Diederik heeft gereageerd op het SEO-rapport. Handel zijn verzoek af.

REPLY VAN DIEDERIK:
Van: {reply['from']}
Datum: {reply['date']}
Onderwerp: {reply['subject']}
Bericht:
{reply['body']}

THREAD INFO:
Thread ID: {reply['thread_id']}
Message ID: {reply['message_id_header']}

INSTRUCTIES:
1. Analyseer wat Diederik vraagt of wil.
2. Als hij een SEO-wijziging wil (meta title/description aanpassen):
   - Laat EERST zien wat je gaat doen via een gmail_reply_thread.
   - Wacht NIET op bevestiging in deze run — stuur het voorstel.
   - De volgende keer dat hij "ok" of "akkoord" reply, voer je het uit.
3. Als hij "ok", "akkoord", "ja", "doen", "go" of iets vergelijkbaars zegt:
   - Voer de laatst voorgestelde wijziging uit via shopify_update_seo.
   - Stuur bevestiging via gmail_reply_thread.
4. Als hij een vraag stelt: beantwoord via gmail_reply_thread.
5. Reageer altijd in het Nederlands — informeel, kort, direct.

Belangrijk: gebruik altijd gmail_reply_thread met de thread_id en message_id hierboven,
zodat het antwoord in dezelfde email thread verschijnt.
"""

        result = run_agent(task, system_prompt)
        log.info("Reply afgehandeld: %s", result[:200])


# ---------- Auth helper ----------

def auth_flow():
    """Eenmalige OAuth2 flow om Google token te genereren."""
    log.info("=== Google OAuth2 authenticatie ===")
    from tools._google_auth import get_google_credentials
    creds = get_google_credentials()
    log.info("Authenticatie succesvol. Token opgeslagen.")
    log.info("Scopes: %s", creds.scopes)


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="Cadomotus SEO Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--weekly-report", action="store_true",
                       help="Genereer en verstuur het wekelijkse rapport")
    group.add_argument("--watch-replies", action="store_true",
                       help="Start de Gmail reply watcher")
    group.add_argument("--auth", action="store_true",
                       help="Voer de Google OAuth2 flow uit")

    args = parser.parse_args()

    if args.weekly_report:
        weekly_report()
    elif args.watch_replies:
        watch_replies()
    elif args.auth:
        auth_flow()


if __name__ == "__main__":
    main()
