# backend/app/services/email_gmail.py
import base64
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ..config import settings


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def _gmail_service():
    """
    Crea il client Gmail usando OAuth2 'installed app' con refresh token.
    Richiede: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN.
    """
    # Costruisci credenziali con solo refresh_token: verrà fatto il refresh immediato.
    creds = Credentials(
        token=None,
        refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )
    # forza il refresh per ottenere un access token valido
    creds.refresh(Request())

    # cache_discovery=False evita warning in ambienti server
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_email_html(to: str, subject: str, html: str) -> None:
    """
    Invia una mail HTML via Gmail API.
    Se le variabili non sono presenti (es. in dev), stampa a console e non fallisce.
    Richieste env:
      - GOOGLE_CLIENT_ID
      - GOOGLE_CLIENT_SECRET
      - GOOGLE_REFRESH_TOKEN
      - EMAIL_FROM
    """
    if not (
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_REFRESH_TOKEN
        and settings.EMAIL_FROM
    ):
        # Fallback non-bloccante in dev
        print(f"[DEV] Gmail non configurato. Simulo invio a {to} — {subject}\n{html}")
        return

    # Costruisci MIME
    msg = MIMEText(html, "html", "utf-8")
    msg["to"] = to
    msg["from"] = settings.EMAIL_FROM
    msg["subject"] = subject

    # codifica base64 URL-safe come richiesto da Gmail
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    svc = _gmail_service()
    svc.users().messages().send(userId="me", body={"raw": raw}).execute()