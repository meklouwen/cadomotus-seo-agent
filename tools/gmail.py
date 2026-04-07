"""Gmail tools voor de Cadomotus SEO agent."""

import os
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
from tools._google_auth import get_google_credentials

REPORT_TO = os.getenv("REPORT_TO", "diederik@cadomotus.com")
REPORT_CC = os.getenv("REPORT_CC", "maarten@thesystem.nl")

GMAIL_TOOLS = [
    {
        "name": "gmail_send_report",
        "description": (
            "Stuur het wekelijkse SEO-rapport naar Diederik. "
            "Wordt gebruikt door de vrijdagochtend cron."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Email onderwerp"
                },
                "body_html": {
                    "type": "string",
                    "description": "Email body in HTML"
                },
                "body_text": {
                    "type": "string",
                    "description": "Email body in plain text (fallback)"
                }
            },
            "required": ["subject", "body_html", "body_text"]
        }
    },
    {
        "name": "gmail_reply_thread",
        "description": (
            "Stuur een reply in een bestaande email thread. "
            "Gebruikt voor het beantwoorden van Diederik's reacties."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID"
                },
                "message_id": {
                    "type": "string",
                    "description": "Message-ID header om op te replyen"
                },
                "subject": {
                    "type": "string",
                    "description": "Re: onderwerp"
                },
                "body_html": {"type": "string"},
                "body_text": {"type": "string"}
            },
            "required": ["thread_id", "message_id", "subject", "body_text"]
        }
    },
    {
        "name": "gmail_check_replies",
        "description": (
            "Check op nieuwe replies van Diederik op SEO-rapport threads. "
            "Geeft ongelezen berichten terug die een reactie zijn op onze mails."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "default": 5
                }
            }
        }
    }
]

THREAD_SUBJECT_PREFIX = "Cadomotus SEO"


def _get_service():
    creds = get_google_credentials()
    return build("gmail", "v1", credentials=creds)


def _build_message(to: str, subject: str, body_text: str,
                   body_html: str = None, cc: str = None,
                   thread_id: str = None, in_reply_to: str = None) -> dict:
    msg = MIMEMultipart("alternative")
    msg["to"] = to
    msg["subject"] = subject
    if cc:
        msg["cc"] = cc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = {"raw": raw}
    if thread_id:
        result["threadId"] = thread_id
    return result


def execute_gmail_tool(name: str, input_data: dict) -> str:
    service = _get_service()

    if name == "gmail_send_report":
        message = _build_message(
            to=REPORT_TO,
            subject=input_data["subject"],
            body_text=input_data["body_text"],
            body_html=input_data.get("body_html"),
            cc=REPORT_CC,
        )
        sent = service.users().messages().send(
            userId="me", body=message
        ).execute()
        return json.dumps({
            "status": "sent",
            "message_id": sent["id"],
            "thread_id": sent["threadId"],
        })

    elif name == "gmail_reply_thread":
        subject = input_data["subject"]
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        message = _build_message(
            to=REPORT_TO,
            subject=subject,
            body_text=input_data["body_text"],
            body_html=input_data.get("body_html"),
            thread_id=input_data["thread_id"],
            in_reply_to=input_data.get("message_id"),
        )
        sent = service.users().messages().send(
            userId="me", body=message
        ).execute()
        return json.dumps({
            "status": "replied",
            "message_id": sent["id"],
            "thread_id": sent["threadId"],
        })

    elif name == "gmail_check_replies":
        max_results = input_data.get("max_results", 5)
        # Zoek threads met ons subject prefix die ongelezen replies hebben
        query = f"subject:{THREAD_SUBJECT_PREFIX} is:unread -from:me"
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = []
        for msg_ref in results.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            # Extract body
            body = ""
            payload = msg["payload"]
            if "parts" in payload:
                for part in payload["parts"]:
                    if part["mimeType"] == "text/plain":
                        body = base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8", errors="replace")
                        break
            elif payload.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(
                    payload["body"]["data"]
                ).decode("utf-8", errors="replace")

            messages.append({
                "id": msg["id"],
                "thread_id": msg["threadId"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "message_id_header": headers.get("Message-ID", ""),
                "date": headers.get("Date", ""),
                "body": body.strip(),
            })

            # Markeer als gelezen
            service.users().messages().modify(
                userId="me", id=msg["id"],
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()

        return json.dumps(messages, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})
