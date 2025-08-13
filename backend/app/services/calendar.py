# backend/app/services/calendar.py
from datetime import datetime, date as date_type, time as time_type, timedelta, timezone
import requests
from ..config import settings
from .google_oauth import get_access_token

CAL_EVENTS_URL_TMPL = "https://www.googleapis.com/calendar/v3/calendars/{calendarId}/events"

def _to_rfc3339(d: date_type, t: time_type, tz: str) -> str:
    """
    Converte date+time locali (naive) in RFC3339 con timezone NAME (fa uso dell’offset attuale).
    Per semplicità usiamo offset statico calcolato dal sistema locale. In prod puoi integrare pytz/zoneinfo.
    """
    # NB: senza zoneinfo, forziamo offset locale corrente (workaround semplice).
    # Se installi Python 3.9+ con zoneinfo, meglio usare zoneinfo.ZoneInfo(tz).
    # Qui assumiamo Europe/Rome: CET/CEST. Se vuoi preciso, aggiungi zoneinfo.
    now_offset = datetime.now().astimezone().utcoffset() or timedelta(hours=0)
    dt = datetime.combine(d, t)
    dt = dt.replace(tzinfo=timezone(now_offset))
    return dt.isoformat()

def _end_after_start(day: date_type, start: time_type, end: time_type) -> tuple[str, str]:
    """
    Se end <= start, consideriamo end come giorno successivo (caso 23:00–00:00).
    Ritorna (start_rfc3339, end_rfc3339).
    """
    tz = settings.TIMEZONE or "Europe/Rome"
    start_rfc = _to_rfc3339(day, start, tz)

    # se end è <= start -> +1 giorno
    if (end.hour, end.minute, end.second) <= (start.hour, start.minute, start.second):
        d2 = day + timedelta(days=1)
        end_rfc = _to_rfc3339(d2, end, tz)
    else:
        end_rfc = _to_rfc3339(day, end, tz)
    return start_rfc, end_rfc

def create_calendar_event(*,
                          calendar_id: str,
                          slot_date: date_type,
                          start_time: time_type,
                          end_time: time_type,
                          artist_name: str | None,
                          artist_email: str | None,
                          producer_name: str | None,
                          producer_email: str | None,
                          manager_name: str | None,
                          description: str | None = None) -> dict | None:
    """
    Crea evento nel calendario indicato. Ritorna il JSON dell’evento o None in caso di errore.
    """
    token = get_access_token()
    if not token or not calendar_id:
        return None

    start_rfc, end_rfc = _end_after_start(slot_date, start_time, end_time)

    summary = f"Sessione studio: {artist_name or 'Artista'} × {producer_name or 'Producer'}"
    desc_lines = [
        f"Artista: {artist_name or artist_email or '-'}",
        f"Producer: {producer_name or producer_email or '-'}",
        f"Manager: {manager_name or '-'}",
    ]
    if description:
        desc_lines.append("")
        desc_lines.append(description)
    description_full = "\n".join(desc_lines)

    attendees = []
    for name, mail in (
        (artist_name, artist_email),
        (producer_name, producer_email),
    ):
        if mail:
            attendees.append({"email": mail, "displayName": name or mail, "responseStatus": "needsAction"})

    payload = {
        "summary": summary,
        "description": description_full,
        "start": { "dateTime": start_rfc },
        "end":   { "dateTime": end_rfc },
        "attendees": attendees,
        "reminders": { "useDefault": True },
        "visibility": "private",
    }

    url = CAL_EVENTS_URL_TMPL.format(calendarId=calendar_id)
    headers = { "Authorization": f"Bearer {token}", "Content-Type": "application/json" }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None