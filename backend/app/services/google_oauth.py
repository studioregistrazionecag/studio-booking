# backend/app/services/google_oauth.py
import requests
from ..config import settings

TOKEN_URL = "https://oauth2.googleapis.com/token"

def get_access_token() -> str | None:
    """
    Usa il refresh token per ottenere un access token nuovo (Gmail/Calendar).
    Ritorna None se mancano le variabili o c'è un errore.
    """
    cid = settings.GOOGLE_CLIENT_ID
    csec = settings.GOOGLE_CLIENT_SECRET
    rtok = settings.GOOGLE_REFRESH_TOKEN
    if not (cid and csec and rtok):
        return None

    data = {
        "client_id": cid,
        "client_secret": csec,
        "refresh_token": rtok,
        "grant_type": "refresh_token",
    }
    try:
        resp = requests.post(TOKEN_URL, data=data, timeout=15)
        resp.raise_for_status()
        j = resp.json()
        return j.get("access_token")
    except Exception:
        return None