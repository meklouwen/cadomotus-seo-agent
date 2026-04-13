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
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6-20250514")


def load_system_prompt() -> str:
    """Laad de volledige SEO skill als system prompt."""
    prompt_parts = []
    skill_files = [
        "system_prompt.md",
    ]
    for fname in skill_files:
        fpath = SKILL_DIR / fname
        if fpath.exists():
            prompt_parts.append(fpath.read_text())

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

    task = f"""Het is {today}, vrijdagochtend. Genereer het wekelijkse SEO-rapport voor Diederik.

Doe het volgende stap voor stap:

1. Haal GSC search analytics op voor de afgelopen 7 dagen (vergelijk met de 7 dagen daarvoor).
2. Haal quick wins op — pagina's met positie 4-15 en lage CTR.
3. Haal de nieuwste producten op uit Shopify en check welke geen SEO hebben.
4. Check PageSpeed voor de homepage (cadomotus.com) op mobile.
5. Check ALLE 4 TALEN (EN, NL, DE, FR) op ontbrekende of slechte meta titles/descriptions.
   - Haal vertalingen op via Shopify Translations API voor NL, DE en FR.
   - Producten/collecties zonder NL/DE/FR meta zijn ook een fix.
6. Selecteer exact 20 verbeterpunten voor het rapport.
7. Stuur het rapport via gmail_send_report.

BELANGRIJK — FIXES REGELS:
- Stuur ALTIJD exact 20 fixes mee in de fixes array. Niet meer, niet minder.
- Elke fix moet een UNIEKE combinatie van pagina-URL + taal hebben.
  Dezelfde URL mag meerdere keren voorkomen als het om verschillende talen gaat.
- Verdeel de fixes over alle 4 talen (EN, NL, DE, FR). Niet alleen EN en NL.
  Streef naar minimaal 2-3 fixes per taal, meer als er meer issues zijn.
- Als er minder dan 20 issues zijn, kijk breder: collecties, blog posts, CMS pagina's.
- Als er meer dan 20 zijn, kies de top 20 op basis van geschatte impact (positie × impressies).
- Elke fix heeft een uniek id (bijv. "fix-1", "fix-2", etc.).
- Vermeld bij elke fix duidelijk welke TAAL het betreft (EN/NL/DE/FR).
- Vermijd dubbele informatie: noem elke pagina+taal combinatie slechts één keer.

Houd het rapport kort en actionable. Diederik is een drukke ondernemer —
hij wil weten: wat gaat goed, wat kan beter, en wat moet ik doen.

Gebruik deze structuur voor het onderwerp:
"Cadomotus SEO — {today} | 20 verbeterpunten (EN/NL/DE/FR)"
"""

    result = run_agent(task, system_prompt)
    log.info("Rapport resultaat: %s", result[:200])


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

    replies_json = execute_gmail_tool("gmail_check_replies", {"max_results": 5})
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
