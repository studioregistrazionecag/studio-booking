# backend/app/routers/manager.py
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..models.user import User, Role
from ..database import get_db
from ..services.neon import neon_usage_last_days
from datetime import datetime, timezone

router = APIRouter(prefix="/manager", tags=["manager"])


class NeonUsageOut(BaseModel):
    ok: bool
    project_id: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    compute_hours: float | None = None
    storage_gb: float | None = None
    last_updated: str | None = None
    raw: dict | None = None
    error: dict | None = None


def _ensure_manager(me: User):
    if me.role != Role.MANAGER:
        raise HTTPException(status_code=403, detail="Solo manager")


@router.get("/neon-usage", response_model=NeonUsageOut)
def neon_usage(
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    last_days: int = Query(30, ge=1, le=90),
    include_raw: bool = Query(False),
):
    _ensure_manager(me)

    res = neon_usage_last_days(last_days)
    now_iso = datetime.now(timezone.utc).isoformat()

    if not res.get("ok"):
        # ritorna info utili in UI per capire il 400
        return NeonUsageOut(
            ok=False,
            last_updated=now_iso,
            error=res.get("last_error") or {"message": "Chiamata Neon non riuscita"},
            raw=res if include_raw else None,
        )

    payload = res.get("raw") or {}
    # Non proviamo a interpretare troppo; mostriamo raw (facoltativo)
    # e lasciamo compute_hours/storage_gb vuoti a meno che tu voglia parsarli qui.
    return NeonUsageOut(
        ok=True,
        last_updated=now_iso,
        raw=payload if include_raw else None,
    )


# Facoltativo: piccolo ping DB per la card (stato connessione)
@router.get("/neon-ping")
def neon_ping(me: User = Depends(get_current_user)):
    _ensure_manager(me)
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}