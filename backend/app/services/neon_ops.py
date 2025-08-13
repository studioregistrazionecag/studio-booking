import requests
from datetime import datetime, timedelta, timezone
from ..config import settings

BASE = "https://console.neon.tech/api/v2"


def _headers():
    if not settings.NEON_API_KEY:
        raise RuntimeError("NEON_API_KEY mancante")
    return {"Authorization": f"Bearer {settings.NEON_API_KEY}", "Accept": "application/json"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_get(url: str, params: dict):
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=20)
        if r.status_code >= 400:
            try:
                body = r.json()
            except Exception:
                body = {"text": r.text}
            return False, {"status": r.status_code, "reason": r.reason, "details": body, "url": r.url}
        return True, r.json()
    except requests.Timeout:
        return False, {"status": 504, "reason": "Timeout", "details": "Timeout chiamando Neon", "url": url}
    except Exception as e:
        return False, {"status": 502, "reason": "Bad Gateway", "details": str(e), "url": url}


def list_projects_and_resolve() -> dict:
    """
    Lista i progetti e prova a risolvere NEON_PROJECT_ID:
    - se è un ID valido, lo conferma
    - se è uno slug/nome, prova a trovarne il vero ID
    """
    url = f"{BASE}/projects"
    ok, data = _safe_get(url, params={})
    if not ok:
        return {"ok": False, "last_error": data}

    want = (settings.NEON_PROJECT_ID or "").strip()
    resolved_id = None
    resolved_name = None

    projects = data.get("projects") or data.get("data") or data.get("items") or []
    for p in projects:
        pid = p.get("id") or p.get("project_id")
        name = p.get("name") or p.get("display_name") or p.get("project")
        if not resolved_id and want:
            # match diretto su id
            if pid == want:
                resolved_id, resolved_name = pid, name
            # match su name/display_name
            if not resolved_id and name == want:
                resolved_id, resolved_name = pid, name

    # fallback: se non specificato o non trovato, usa il primo progetto
    if not resolved_id and projects:
        p0 = projects[0]
        resolved_id = p0.get("id") or p0.get("project_id")
        resolved_name = p0.get("name") or p0.get("display_name") or p0.get("project")

    return {
        "ok": True,
        "projects": projects,
        "resolved_id": resolved_id,
        "resolved_name": resolved_name,
        "env_value": want or None,
    }


def neon_usage_last_days(days: int = 30) -> dict:
    """
    Risolve l'ID progetto e poi tenta più varianti della chiamata consumption.
    """
    # 1) risolvi progetto
    res = list_projects_and_resolve()
    if not res.get("ok"):
        return res
    project_id = res.get("resolved_id")
    project_name = res.get("resolved_name")
    if not project_id:
        return {"ok": False, "last_error": {"reason": "Project non trovato", "hint": "Controlla NEON_PROJECT_ID"}}

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now

    url = f"{BASE}/consumption_history/projects"

    variants = [
        {"project_id": project_id},
        {"project_id": project_id, "from": _iso(start), "to": _iso(end), "granularity": "day"},
        {"project_ids": project_id, "from": _iso(start), "to": _iso(end), "granularity": "day"},
        {"project_ids[]": project_id, "from": _iso(start), "to": _iso(end), "granularity": "day"},
    ]

    last_error = None
    for params in variants:
        ok, payload = _safe_get(url, params)
        if ok:
            return {
                "ok": True,
                "raw": payload,
                "meta": {"project_id": project_id, "project_name": project_name},
            }
        last_error = payload

    return {
        "ok": False,
        "last_error": last_error or {"reason": "Unknown error"},
        "meta": {"project_id": project_id, "project_name": project_name},
    }