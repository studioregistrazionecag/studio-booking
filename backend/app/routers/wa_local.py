from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models.slot import AvailabilitySlot, SlotStatus
from ..models.booking import Booking, BookingStatus
from datetime import date

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-local"])

def _auth(bearer: str | None):
    if settings.APP_ENV == "prod" and settings.WHATSAPP_LOCAL_BEARER:
        if bearer != f"Bearer {settings.WHATSAPP_LOCAL_BEARER}":
            raise HTTPException(403, "Forbidden")

@router.post("/incoming")
def incoming(payload: dict,
             db: Session = Depends(get_db),
             authorization: str | None = Header(None)):
    _auth(authorization)

    from_phone = str(payload.get("from", "")).strip()
    text = str(payload.get("text", "")).strip().lower()
    print("WA IN:", from_phone, text)

    # Esempio di due comandi:
    if text in ("help", "ciao", "?"):
        return {"ok": True, "reply": "Comandi: 'slot oggi' • 'stato'"}

    if text.startswith("slot oggi"):
        today = date.today()
        q = db.query(AvailabilitySlot).filter(
            AvailabilitySlot.date == today,
            AvailabilitySlot.status == SlotStatus.LIBERO,
            AvailabilitySlot.is_deleted == False
        ).order_by(AvailabilitySlot.start_time)
        slots = q.all()
        if not slots:
            return {"ok": True, "reply": "Oggi nessuno slot LIBERO."}
        return {"ok": True, "reply": " | ".join(f"{str(s.start_time)[:5]}–{str(s.end_time)[:5]}" for s in slots)}

    if text.startswith("stato"):
        bookings = db.query(Booking)\
                     .filter(Booking.status == BookingStatus.CONFIRMED)\
                     .order_by(Booking.id.desc()).limit(5).all()
        if not bookings:
            return {"ok": True, "reply": "Nessuna conferma al momento."}
        return {"ok": True, "reply": " • ".join(f"{b.slot.date} {str(b.slot.start_time)[:5]}–{str(b.slot.end_time)[:5]}" for b in bookings)}

    return {"ok": True}