"""Gedeelde Google OAuth2 authenticatie voor GSC.

Drie manieren om credentials te leveren, in volgorde van prioriteit:

1. **Env-var `GOOGLE_TOKEN_JSON`** (aanbevolen voor Easypanel): de volledige
   inhoud van je `token.json` als string. Bij startup wordt die naar
   `GOOGLE_TOKEN_PATH` geschreven als die nog niet bestaat. Eenmalige setup,
   daarna refresht de token zichzelf op disk.
2. **Bestand op `GOOGLE_TOKEN_PATH`** (meestal `/data/token.json` in de volume).
   Gebruik dit als je liever handmatig uploadt naar het persistent volume.
3. **Lokale OAuth-flow** (`python agent.py --auth`): opent een browser, schrijft
   `token.json` naar disk. Werkt alleen op je eigen laptop — niet in een
   headless container.

Als geen van drie werkt, geeft `get_google_credentials` een FileNotFoundError en
valt de GSC-tool terug op een gracefull error-JSON. Het rapport draait dan door
op Shopify-data (zie `tools/gsc.py::execute_gsc_tool`).
"""

import logging
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

log = logging.getLogger("cadomotus-agent")

# Alleen GSC read — Gmail loopt via n8n webhook, geen scope nodig.
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
]

TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/data/google_credentials.json")


def _materialize_from_env():
    """Schrijf token/credentials naar disk als ze als env-var zijn meegegeven.
    Niet-destructief: als er al een bestand op dat pad staat, laten we het zo —
    dat bestand is mogelijk recenter gerefresht dan de env-var."""
    for env_key, dest in (
        ("GOOGLE_TOKEN_JSON", TOKEN_PATH),
        ("GOOGLE_CREDENTIALS_JSON", CREDENTIALS_PATH),
    ):
        val = os.getenv(env_key, "").strip()
        if not val:
            continue
        dest_path = Path(dest)
        if dest_path.exists():
            continue  # bestaande (mogelijk recenter gerefreshed) file niet overschrijven
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(val, encoding="utf-8")
            log.info("GOOGLE_AUTH | %s → %s (bootstrap uit env-var)", env_key, dest)
        except OSError as e:
            log.warning("GOOGLE_AUTH | kon %s niet schrijven naar %s: %s", env_key, dest, e)


def get_google_credentials() -> Credentials:
    """Haal geldige Google credentials op. Refresh automatisch als verlopen."""
    _materialize_from_env()

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        log.info("GOOGLE_AUTH | token verlopen, refreshing…")
        creds.refresh(Request())
        _save_token(creds)
        return creds

    if creds and creds.valid:
        return creds

    # Geen geldige creds op disk én geen env-var: val terug op lokale flow.
    # In een headless container werkt dit NIET — de caller (execute_gsc_tool) vangt
    # de FileNotFoundError op en draait het rapport verder zonder GSC-data.
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Geen Google token ({TOKEN_PATH}) en geen client credentials "
            f"({CREDENTIALS_PATH}) gevonden. Set GOOGLE_TOKEN_JSON als env-var "
            "of upload token.json naar het persistent volume. "
            "GSC wordt overgeslagen — het rapport draait door op Shopify-data."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=8090)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials):
    path = Path(TOKEN_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
