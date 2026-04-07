"""Gedeelde Google OAuth2 authenticatie voor GSC + Gmail."""

import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "/data/token.json")
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "/app/google_credentials.json")


def get_google_credentials() -> Credentials:
    """Haal geldige Google credentials op. Refresh automatisch als verlopen."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
    elif not creds or not creds.valid:
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(
                f"Google credentials niet gevonden op {CREDENTIALS_PATH}. "
                "Download OAuth2 client credentials van Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=8090)
        _save_token(creds)

    return creds


def _save_token(creds: Credentials):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
