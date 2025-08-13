# backend/app/schemas/booking.py
from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import date, time
from typing import Optional
from sqlalchemy.orm import aliased
from ..models.user import User

# -----------------------------
# SLOT (disponibilità studio)
# -----------------------------

class SlotIn(BaseModel):
    """Creazione singolo slot (se mai servisse)."""
    date: date
    start_time: time
    end_time: time

class SlotBulkIn(BaseModel):
    """Creazione a blocchi: da start a end, step_minuti (es. 60)."""
    date: date
    start_time: time
    end_time: time
    step_minutes: int = Field(60, ge=15, le=240)

class SlotOut(BaseModel):
    id: int
    date: date
    start_time: time
    end_time: time
    status: str  # "LIBERO" / "OCCUPATO"
    class Config:
        from_attributes = True  # pydantic v2

# -----------------------------
# BOOKING (prenotazioni)
# -----------------------------

class CreateBookingFromSlotIn(BaseModel):
    """Richiesta artista: prenota uno slot esistente scegliendo il producer."""
    producer_id: int
    slot_id: int

class BookingOut(BaseModel):
    id: int
    artist_id: int
    producer_id: int
    status: str

    # campi opzionali, così siamo compatibili sia con modelli "vecchi"
    # (day/start_time) sia con quelli "nuovi" basati su slot
    day: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None

    slot_id: Optional[int] = None
    slot_date: Optional[date] = None
    start: Optional[time] = None
    end: Optional[time] = None

    artist_name: Optional[str] = None
    artist_email: Optional[str] = None
    producer_name: Optional[str] = None
    producer_email: Optional[str] = None

    class Config:
        from_attributes = True