# backend/app/services/neon.py
import requests
from datetime import datetime, timedelta, timezone
from ..config import settings

BASE = "https://console.neon.tech/api/v2"


def _headers():
    if not settings.NEON_API_KEY:
        raise RuntimeError("NEON_API_KEY mancante")
    return {"Authorization": f"Bearer {settings.NEON_API_KEY}", "Accept": "application/json"}


def _iso(dt: datetime) -> str:
    # RFC3339 con suffisso Z
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _try_get(url: str, params: dict):
    """
    Esegue GET e ritorna (ok, payload|errore_testuale).
    Non alza eccezioni: ci serve mostrare l'errore vero in UI.
    """
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=20)
        if r.status_code >= 400:
            try:
                j = r.json()
            except Exception:
                j = {"text": r.text}
            return False, {
                "status": r.status_code,
                "reason": r.reason,
                "details": j
            }
        return True, r.json()
    except requests.Timeout:
        return False, {"status": 504, "reason": "Timeout", "details": "Timeout chiamando Neon"}
    except Exception as e:
        return False, {"status": 502, "reason": "Bad Gateway", "details": str(e)}


def neon_usage_last_days(days: int = 30) -> dict:
    """
    Tenta più forme di chiamata alla “consumption history” di Neon.
    Ritorna:
      { ok: True, raw: <payload> }
    oppure
      { ok: False, tried: [...], last_error: {...} }
    """
    pid = settings.NEON_PROJECT_ID
    if not pid:
        return {"ok": False, "error": "NEON_PROJECT_ID mancante"}

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now

    url = f"{BASE}/consumption_history/projects"

    # Proviamo una serie di varianti comuni:
    variants = [
        # 1) Param minimo: solo project_id (alcuni ambienti danno periodo di default)
        {"project_id": pid},
        # 2) Con from/to (RFC3339) + granularity
        {"project_id": pid, "from": _iso(start), "to": _iso(end), "granularity": "day"},
        # 3) project_ids (senza [])
        {"project_ids": pid, "from": _iso(start), "to": _iso(end), "granularity": "day"},
        # 4) project_ids[] come array singolo
        {"project_ids[]": pid, "from": _iso(start), "to": _iso(end), "granularity": "day"},
    ]

    tried = []
    last_error = None

    for params in variants:
        ok, payload = _try_get(url, params)
        tried.append({"url": url, "params": params, "ok": ok})
        if ok:
            return {"ok": True, "raw": payload, "tried": tried}
        else:
            last_error = payload

    return {"ok": False, "tried": tried, "last_error": last_error}