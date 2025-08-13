from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..deps import get_current_user
from ..models.user import User, Role
from ..database import get_db
from ..services.neon_ops import neon_usage_last_days, list_projects_and_resolve

router = APIRouter(prefix="/ops", tags=["ops"])


class NeonUsageOut(BaseModel):
    ok: bool
    project_id: str | None = None
    project_name: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    compute_hours: float | None = None
    storage_gb: float | None = None
    last_updated: str | None = None
    raw: dict | None = None
    error: dict | None = None


def _ensure_manager(me: User):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")


@router.get("/neon/projects")
def neon_projects(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_manager(me)
    return list_projects_and_resolve()


@router.get("/neon/usage", response_model=NeonUsageOut)
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
        return NeonUsageOut(
            ok=False,
            last_updated=now_iso,
            error=res.get("last_error") or {"message": "Chiamata Neon non riuscita"},
            raw=res if include_raw else None,
        )

    payload = res.get("raw") or {}
    meta = res.get("meta") or {}
    return NeonUsageOut(
        ok=True,
        project_id=meta.get("project_id"),
        project_name=meta.get("project_name"),
        last_updated=now_iso,
        raw=payload if include_raw else None,
    )