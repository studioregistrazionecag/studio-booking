# backend/app/services/google_calendar.py
import os
import requests
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
APP_TZ = os.getenv("APP_TIMEZONE", "Europe/Rome")

def _get_access_token() -> str:
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def _iso(dt: datetime) -> str:
    # restituisce RFC3339 con timezone
    return dt.isoformat()

def create_event(*, day: date, start: time, end: time,
                 summary: str, description: str = "") -> str:
    """
    Crea un evento e ritorna eventId.
    """
    tz = ZoneInfo(APP_TZ)
    start_dt = datetime.combine(day, start).replace(tzinfo=tz)
    end_dt = datetime.combine(day, end).replace(tzinfo=tz)

    access_token = _get_access_token()
    payload = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": _iso(start_dt), "timeZone": APP_TZ},
        "end": {"dateTime": _iso(end_dt), "timeZone": APP_TZ},
    }
    r = requests.post(
        f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events",
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        json=payload, timeout=15
    )
    r.raise_for_status()
    return r.json()["id"]

def delete_event(event_id: str) -> None:
    if not event_id:
        return
    access_token = _get_access_token()
    r = requests.delete(
        f"{CALENDAR_BASE}/calendars/{CALENDAR_ID}/events/{event_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15
    )
    # 204 OK, 200 in alcuni casi; se 404 lo ignoriamo
    if r.status_code not in (200, 204, 404):
        r.raise_for_status()