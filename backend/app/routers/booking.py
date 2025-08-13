from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, aliased
from datetime import date, datetime, time, timedelta
from typing import List
import re

from ..database import get_db, Base, engine
from ..deps import get_current_user, require_role
from ..models.user import User, Role
from ..models.slot import (
    AvailabilitySlot,
    SlotStatus,
)  # LIBERO / IN_SOSPESO / OCCUPATO / CHIUSO
from ..models.booking import Booking, BookingStatus
from ..schemas.booking import SlotOut, SlotBulkIn, CreateBookingFromSlotIn, BookingOut
from ..services.email_gmail import send_email_html
from ..services.calendar import create_calendar_event
from ..config import settings
from sqlalchemy import and_, or_


# -----------------------------------------
# Helpers
# -----------------------------------------
def _user_label(u: User | None) -> str:
    if not u:
        return ""
    return (u.display_name or "").strip() or u.email


def _fmt_slot(s: AvailabilitySlot) -> str:
    return f"{s.date.isoformat()} • {str(s.start_time)[:5]}–{str(s.end_time)[:5]}"


def _managers(db: Session) -> list[User]:
    return (
        db.query(User).filter(User.role == Role.MANAGER, User.is_active == True).all()
    )


def _send_to_many(addresses: list[str], subject: str, html: str) -> None:
    """
    Invio tollerante + dedup case-insensitive per evitare duplicati.
    In dev senza Gmail configurata, la funzione di servizio stampa/loga.
    """
    # de-dup
    seen = set()
    deduped: list[str] = []
    for a in addresses or []:
        key = (a or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(a)

    print("EMAIL ->", deduped, "|", subject)  # log
    for a in deduped:
        try:
            send_email_html(a, subject, html)
        except Exception as e:
            print("Email error:", e)


def _now_parts():
    now = datetime.now()
    return now.date(), now.time().replace(microsecond=0)


def _only_future(q):
    """Applica il filtro 'solo futuri' a una query che già usa AvailabilitySlot."""
    today, now_time = _now_parts()
    return q.filter(
        or_(
            AvailabilitySlot.date > today,
            and_(AvailabilitySlot.date == today, AvailabilitySlot.end_time >= now_time),
        )
    )


_LAST_CLEANUP_AT: datetime | None = None
_CLEANUP_COOLDOWN_SEC = 300  # non più di una volta ogni 5 minuti


def _cleanup_past_slots(db: Session) -> int:
    """
    Cancella tutti gli slot già terminati (data < oggi oppure end_time < adesso se oggi).
    Prima elimina le bookings collegate, poi gli slot.
    Throttling interno per non farlo troppo spesso.
    Ritorna il numero di slot eliminati.
    """
    global _LAST_CLEANUP_AT
    now = datetime.now()
    if (
        _LAST_CLEANUP_AT
        and (now - _LAST_CLEANUP_AT).total_seconds() < _CLEANUP_COOLDOWN_SEC
    ):
        return 0  # throttled

    today, now_time = _now_parts()

    # seleziona ID slot passati
    past_q = db.query(AvailabilitySlot.id).filter(
        or_(
            AvailabilitySlot.date < today,
            and_(AvailabilitySlot.date == today, AvailabilitySlot.end_time < now_time),
        )
    )
    past_ids = [row[0] for row in past_q.all()]
    if not past_ids:
        _LAST_CLEANUP_AT = now
        return 0

    # elimina prima le prenotazioni, poi gli slot
    db.query(Booking).filter(Booking.slot_id.in_(past_ids)).delete(
        synchronize_session=False
    )
    deleted = (
        db.query(AvailabilitySlot)
        .filter(AvailabilitySlot.id.in_(past_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    _LAST_CLEANUP_AT = now
    return deleted


def _parse_manager_emails_from_env() -> list[str]:
    """
    Legge settings.MANAGER_EMAILS (CSV, ; o newline),
    pulisce, deduplica case-insensitive e filtra formati invaldi.
    """
    raw = (settings.MANAGER_EMAILS or "").strip()
    if not raw:
        return []

    parts = re.split(r"[,\n;]+", raw)
    emails = []
    seen = set()
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    for p in parts:
        e = p.strip()
        if not e:
            continue
        if not email_re.match(e):
            continue
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(e)

    return emails


def _manager_emails(db: Session) -> list[str]:
    """
    Sorgente primaria: MANAGER_EMAILS da .env (se presente).
    Fallback: prendi i manager dal DB.
    """
    env_emails = _parse_manager_emails_from_env()
    if env_emails:
        return env_emails
    # fallback DB
    db_emails = [m.email for m in _managers(db) if m.email]
    # de-dup case-insensitive
    seen = set()
    out: list[str] = []
    for p in db_emails:
        key = (p or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


# -----------------------------------------
# Router
# -----------------------------------------
router = APIRouter(prefix="/booking", tags=["booking"])

# -----------------------------------------------------------------------------
# AVAILABILITY (gli utenti autenticati vedono gli slot dei manager)
# -----------------------------------------------------------------------------
@router.get("/availability", response_model=List[SlotOut])
def availability(
    day: date | None = None,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # lazy GC
    _cleanup_past_slots(db)

    q = db.query(AvailabilitySlot).filter(AvailabilitySlot.is_deleted == False)
    if day:
        q = q.filter(AvailabilitySlot.date == day)
    else:
        q = _only_future(q)  # solo futuri se non c'è filtro

    return q.order_by(
        AvailabilitySlot.date.asc(), AvailabilitySlot.start_time.asc()
    ).all()


# -----------------------------------------------------------------------------
# MANAGER: crea/lista/elimina slot
# -----------------------------------------------------------------------------
@router.post("/manager/slots/bulk")
def manager_slots_bulk(
    payload: SlotBulkIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo i manager possono creare slot")

    if payload.step_minutes <= 0 or payload.step_minutes > 480:
        raise HTTPException(400, "step_minutes non valido")

    # calcolo window
    start_dt = datetime.combine(payload.date, payload.start_time)
    end_dt = datetime.combine(payload.date, payload.end_time)

    # 00:00 = giorno successivo
    if payload.end_time == time(0, 0):
        end_dt += timedelta(days=1)

    if end_dt <= start_dt:
        raise HTTPException(400, "Fine deve essere dopo l'inizio")

    step = timedelta(minutes=payload.step_minutes)

    # costruisci la lista candidata di (start_time, end_time) nel giorno
    candidates: list[tuple[time, time]] = []
    cur = start_dt
    while cur + step <= end_dt:
        st = cur.time()
        et = (cur + step).time()
        candidates.append((st, et))
        cur += step

    if not candidates:
        raise HTTPException(400, "Nessuno slot generato")

    # PRE-FILTRO: prendi gli slot esistenti per quel manager e giorno
    existing = (
        db.query(AvailabilitySlot.start_time, AvailabilitySlot.end_time)
        .filter(
            AvailabilitySlot.manager_id == me.id,
            AvailabilitySlot.date == payload.date,
            AvailabilitySlot.is_deleted == False,
        )
        .all()
    )
    existing_set = {(row[0], row[1]) for row in existing}

    # inserisci solo i mancanti
    to_insert: list[AvailabilitySlot] = []
    skipped = 0
    for st, et in candidates:
        if (st, et) in existing_set:
            skipped += 1
            continue
        to_insert.append(
            AvailabilitySlot(
                manager_id=me.id,
                date=payload.date,
                start_time=st,
                end_time=et,
                status=SlotStatus.LIBERO,
                is_deleted=False,
            )
        )

    created = 0
    if to_insert:
        db.add_all(to_insert)
        db.commit()
        created = len(to_insert)

    # non alzare eccezioni: torna conteggi chiari per l’UI
    return {"ok": True, "created": created, "skipped": skipped}


@router.get("/manager/slots", response_model=List[SlotOut])
def manager_slots_list(
    db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")

    _cleanup_past_slots(db)

    q = db.query(AvailabilitySlot).filter(AvailabilitySlot.is_deleted == False)
    q = _only_future(q)
    return q.order_by(
        AvailabilitySlot.date.asc(), AvailabilitySlot.start_time.asc()
    ).all()


@router.delete("/manager/slots/{slot_id}")
def manager_slots_delete(
    slot_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")
    s = db.get(AvailabilitySlot, slot_id)
    if not s or s.is_deleted:
        raise HTTPException(404, "Slot non trovato")
    s.is_deleted = True
    db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------------
# ARTISTA: prenota uno slot (da slot esistente)
# -----------------------------------------------------------------------------
@router.post("", response_model=BookingOut)
def request_booking_from_slot(
    payload: CreateBookingFromSlotIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if me.role != Role.ARTIST:
        raise HTTPException(403, "Solo gli artisti possono prenotare")

    slot = db.get(AvailabilitySlot, payload.slot_id)
    if not slot or slot.is_deleted:
        raise HTTPException(404, "Slot non trovato")

    if slot.status != SlotStatus.LIBERO:
        raise HTTPException(409, "Slot non disponibile")

    exists = (
        db.query(Booking)
        .filter(
            Booking.slot_id == slot.id,
            Booking.status.in_(
                [
                    BookingStatus.PENDING_PRODUCER,
                    BookingStatus.PENDING_MANAGER,
                    BookingStatus.CONFIRMED,
                ]
            ),
        )
        .first()
    )
    if exists:
        raise HTTPException(409, "Slot già prenotato o in verifica")

    b = Booking(
        slot_id=slot.id,
        artist_id=me.id,
        producer_id=payload.producer_id,
        status=BookingStatus.PENDING_PRODUCER,
        notes="",
    )

    slot.status = SlotStatus.IN_SOSPESO
    db.add(b)
    db.commit()
    db.refresh(b)

    producer = db.get(User, payload.producer_id)
    if producer and producer.is_active and producer.email:
        subject = "Nuova richiesta di prenotazione"
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(producer)},</p>
          <p>hai ricevuto una nuova richiesta di prenotazione dall'artista <b>{_user_label(me)}</b>.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <p>Accedi all'area Produttore per accettare o rifiutare.</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([producer.email], subject, html)

    return b


# -----------------------------------------------------------------------------
# PRODUCER: richieste in arrivo + accept/reject
# -----------------------------------------------------------------------------
auth_producer = require_role(Role.PRODUCER)
auth_any_role = require_role(Role.MANAGER, Role.PRODUCER, Role.ARTIST)


@router.get("/producer/incoming")
def producer_incoming(
    db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role not in (Role.PRODUCER, Role.MANAGER):
        raise HTTPException(403, "Solo produttori/manager")

    q = (
        db.query(Booking)
        .options(joinedload(Booking.slot), joinedload(Booking.artist))
        .filter(Booking.status == BookingStatus.PENDING_PRODUCER)
        .order_by(Booking.id.desc())
    )
    if me.role == Role.PRODUCER:
        q = q.filter(Booking.producer_id == me.id)

    q = _only_future(q)  # mostra solo richieste future

    out = []
    for b in q.all():
        s = b.slot
        a = b.artist
        out.append(
            {
                "id": b.id,
                "date": s.date.isoformat(),
                "start_time": str(s.start_time)[:5],
                "end_time": str(s.end_time)[:5],
                "artist_id": b.artist_id,
                "artist_name": (a.display_name or a.email) if a else None,
                "status": b.status.value,
            }
        )
    return out


@router.post("/{booking_id}/producer/accept", response_model=BookingOut)
def producer_accept(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    b = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Prenotazione non trovata")
    if me.role == Role.PRODUCER and b.producer_id != me.id:
        raise HTTPException(403, "Non autorizzato")
    if me.role not in (Role.PRODUCER, Role.MANAGER):
        raise HTTPException(403, "Non autorizzato")
    if b.status != BookingStatus.PENDING_PRODUCER:
        raise HTTPException(400, "Stato non valido")

    b.status = BookingStatus.PENDING_MANAGER
    db.commit()
    db.refresh(b)

    slot = db.get(AvailabilitySlot, b.slot_id)
    artist = db.get(User, b.artist_id)
    producer = db.get(User, b.producer_id)
    to_mgrs = _manager_emails(db)

    if slot and artist and producer:
        if to_mgrs:
            subject_mgr = "Richiesta in approvazione (manager)"
            html_mgr = f"""
            <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
              <p>Ciao,</p>
              <p>Il produttore <b>{_user_label(producer)}</b> ha accettato la richiesta dell'artista <b>{_user_label(artist)}</b>.</p>
              <p><b>Slot:</b> {_fmt_slot(slot)}</p>
              <p>Conferma o rifiuta dalla dashboard Manager.</p>
              <hr><small>W8 x CAG</small>
            </div>
            """
            _send_to_many(to_mgrs, subject_mgr, html_mgr)

        subject_artist = "Il produttore ha accettato la tua richiesta"
        html_artist = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(artist)},</p>
          <p>Il produttore <b>{_user_label(producer)}</b> ha accettato la tua richiesta.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <p>Ora la prenotazione è in approvazione dai manager.</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([artist.email], subject_artist, html_artist)

    return b


@router.post("/{booking_id}/producer/reject", response_model=BookingOut)
def producer_reject(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    b = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Prenotazione non trovata")
    if me.role == Role.PRODUCER and b.producer_id != me.id:
        raise HTTPException(403, "Non autorizzato")
    if me.role not in (Role.PRODUCER, Role.MANAGER):
        raise HTTPException(403, "Non autorizzato")
    if b.status != BookingStatus.PENDING_PRODUCER:
        raise HTTPException(400, "Stato non valido")

    b.status = BookingStatus.REJECTED_BY_PRODUCER
    slot = db.get(AvailabilitySlot, b.slot_id)
    if slot:
        slot.status = SlotStatus.LIBERO
    db.commit()
    db.refresh(b)

    artist = db.get(User, b.artist_id)
    producer = db.get(User, b.producer_id)
    if slot and artist and producer and artist.email:
        subject = "La tua richiesta è stata rifiutata dal produttore"
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(artist)},</p>
          <p>Il produttore <b>{_user_label(producer)}</b> ha rifiutato la tua richiesta.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([artist.email], subject, html)

    return b


# -----------------------------------------------------------------------------
# MANAGER: coda decisione (dopo OK produttore)
# -----------------------------------------------------------------------------
@router.get("/manager/pending")
def manager_pending(
    db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")

    Artist = aliased(User)
    Producer = aliased(User)

    q = (
        db.query(
            Booking.id.label("booking_id"),
            Booking.status.label("b_status"),
            AvailabilitySlot.date.label("s_date"),
            AvailabilitySlot.start_time.label("s_start"),
            AvailabilitySlot.end_time.label("s_end"),
            Artist.display_name.label("artist_name"),
            Artist.email.label("artist_email"),
            Producer.display_name.label("producer_name"),
            Producer.email.label("producer_email"),
        )
        .join(AvailabilitySlot, Booking.slot_id == AvailabilitySlot.id)
        .join(Artist, Booking.artist_id == Artist.id)
        .join(Producer, Booking.producer_id == Producer.id)
        .filter(Booking.status == BookingStatus.PENDING_MANAGER)
        .order_by(AvailabilitySlot.date.asc(), AvailabilitySlot.start_time.asc())
    )

    rows = q.all()
    out = []
    for r in rows:
        out.append(
            {
                "id": r.booking_id,
                "date": r.s_date.isoformat(),
                "start_time": str(r.s_start)[:5],
                "end_time": str(r.s_end)[:5],
                "status": r.b_status.value
                if hasattr(r.b_status, "value")
                else str(r.b_status),
                "artist_name": (r.artist_name or r.artist_email),
                "producer_name": (r.producer_name or r.producer_email),
            }
        )
    return out


@router.post("/{booking_id}/manager/accept", response_model=BookingOut)
def manager_accept(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")
    b = db.get(Booking, booking_id)
    if not b or b.status != BookingStatus.PENDING_MANAGER:
        raise HTTPException(400, "Stato non valido")

    b.status = BookingStatus.CONFIRMED

    slot = db.get(AvailabilitySlot, b.slot_id)
    if slot:
        try:
            slot.status = SlotStatus.OCCUPATO
        except Exception:
            slot.status = getattr(SlotStatus, "BOOKED", slot.status)

    # Calendar (best-effort)
    try:
        cal_id = settings.GOOGLE_CALENDAR_ID or "primary"
        artist = db.get(User, b.artist_id)
        producer = db.get(User, b.producer_id)
        create_calendar_event(
            calendar_id=cal_id,
            slot_date=slot.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            artist_name=(artist.display_name if artist else None),
            artist_email=(artist.email if artist else None),
            producer_name=(producer.display_name if producer else None),
            producer_email=(producer.email if producer else None),
            manager_name=_user_label(me),
            description=f"Prenotazione confermata (ID {b.id}).",
        )
    except Exception as e:
        print("Calendar error:", e)

    db.commit()
    db.refresh(b)

    if slot:
        artist = db.get(User, b.artist_id)
        producer = db.get(User, b.producer_id)
        tos = [x.email for x in (artist, producer) if x and x.email]
        if tos:
            subject = "Prenotazione confermata"
            html = f"""
            <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
              <p>Ciao,</p>
              <p>La tua prenotazione è stata <b>confermata</b>.</p>
              <p><b>Artista:</b> {_user_label(artist)}<br/>
                 <b>Produttore:</b> {_user_label(producer)}<br/>
                 <b>Slot:</b> {_fmt_slot(slot)}
              </p>
              <hr><small>W8 x CAG</small>
            </div>
            """
            _send_to_many(tos, subject, html)

    return b


@router.post("/{booking_id}/manager/reject", response_model=BookingOut)
def manager_reject(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    if me.role != Role.MANAGER:
        raise HTTPException(403, "Solo manager")
    b = db.get(Booking, booking_id)
    if not b or b.status != BookingStatus.PENDING_MANAGER:
        raise HTTPException(400, "Stato non valido")

    b.status = BookingStatus.REJECTED_BY_MANAGER
    slot = db.get(AvailabilitySlot, b.slot_id)
    if slot:
        slot.status = SlotStatus.LIBERO

    db.commit()
    db.refresh(b)

    artist = db.get(User, b.artist_id)
    producer = db.get(User, b.producer_id)
    if slot and artist and producer:
        subject = "Prenotazione rifiutata dal manager"
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao,</p>
          <p>La prenotazione è stata <b>rifiutata</b> dai manager.</p>
          <p><b>Artista:</b> {_user_label(artist)}<br/>
             <b>Produttore:</b> {_user_label(producer)}<br/>
             <b>Slot:</b> {_fmt_slot(slot)}
          </p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        tos = [x.email for x in (artist, producer) if x and x.email]
        _send_to_many(tos, subject, html)

    return b


# -----------------------------------------------------------------------------
# CANCELLAZIONI — solo prenotazioni CONFERMATE
# -----------------------------------------------------------------------------
@router.post("/{booking_id}/producer/cancel", response_model=BookingOut)
def producer_cancel(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    """
    Il PRODUTTORE annulla una prenotazione confermata per imprevisti.
    Email:
      - conferma al produttore
      - avviso all'artista
      - avviso a tutti i manager
    """
    b = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Prenotazione non trovata")
    if me.role != Role.PRODUCER:
        raise HTTPException(403, "Solo il produttore può annullare")
    if b.producer_id != me.id:
        raise HTTPException(403, "Non autorizzato")
    if b.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            400,
            "Solo le prenotazioni confermate possono essere annullate dal produttore",
        )

    b.status = BookingStatus.CANCELED_BY_PRODUCER
    slot = db.get(AvailabilitySlot, b.slot_id)
    if slot:
        slot.status = SlotStatus.LIBERO
    db.commit()
    db.refresh(b)

    artist = db.get(User, b.artist_id)
    producer = db.get(User, b.producer_id)
    to_mgrs = _manager_emails(db)

    # conferma al producer
    if producer and producer.email and slot:
        subject_p = "Conferma annullamento prenotazione"
        html_p = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(producer)},</p>
          <p>hai annullato la prenotazione confermata.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([producer.email], subject_p, html_p)

    # avvisi
    if artist and artist.email and slot:
        subject_a = "Il produttore ha annullato la prenotazione"
        html_a = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(artist)},</p>
          <p>il produttore <b>{_user_label(producer)}</b> ha annullato la prenotazione confermata.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([artist.email], subject_a, html_a)

    if to_mgrs and slot:
        subject_m = "Prenotazione annullata dal produttore"
        html_m = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao,</p>
          <p>Il produttore <b>{_user_label(producer)}</b> ha annullato una prenotazione confermata con l'artista <b>{_user_label(artist)}</b>.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many(to_mgrs, subject_m, html_m)

    return b


@router.post("/{booking_id}/artist/cancel", response_model=BookingOut)
def artist_cancel(
    booking_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)
):
    """
    L'ARTISTA annulla una prenotazione confermata.
    Email:
      - conferma all'artista
      - avviso al relativo produttore
      - avviso a tutti i manager
    """
    b = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, "Prenotazione non trovata")
    if me.role != Role.ARTIST:
        raise HTTPException(403, "Solo l'artista può annullare")
    if b.artist_id != me.id:
        raise HTTPException(403, "Non autorizzato")
    if b.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            400, "Solo le prenotazioni confermate possono essere annullate dall'artista"
        )

    b.status = BookingStatus.CANCELED_BY_ARTIST
    slot = db.get(AvailabilitySlot, b.slot_id)
    if slot:
        slot.status = SlotStatus.LIBERO
    db.commit()
    db.refresh(b)

    artist = db.get(User, b.artist_id)
    producer = db.get(User, b.producer_id)
    to_mgrs = _manager_emails(db)

    # conferma all'artista
    if artist and artist.email and slot:
        subject_a = "Conferma annullamento prenotazione"
        html_a = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(artist)},</p>
          <p>hai annullato la prenotazione confermata.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([artist.email], subject_a, html_a)

    # avviso al producer
    if producer and producer.email and slot:
        subject_p = "L'artista ha annullato la prenotazione"
        html_p = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao {_user_label(producer)},</p>
          <p>l'artista <b>{_user_label(artist)}</b> ha annullato la prenotazione confermata.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many([producer.email], subject_p, html_p)

    # avviso a manager
    if to_mgrs and slot:
        subject_m = "Prenotazione annullata dall'artista"
        html_m = f"""
        <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
          <p>Ciao,</p>
          <p>L'artista <b>{_user_label(artist)}</b> ha annullato una prenotazione confermata con il produttore <b>{_user_label(producer)}</b>.</p>
          <p><b>Slot:</b> {_fmt_slot(slot)}</p>
          <hr><small>W8 x CAG</small>
        </div>
        """
        _send_to_many(to_mgrs, subject_m, html_m)

    return b


# -----------------------------------------------------------------------------
# AGENDA CONDIVISA (solo confermate, FUTURE, con Nomi)
# -----------------------------------------------------------------------------
@router.get("/agenda/confirmed")
def agenda_confirmed(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    q = (
        db.query(Booking)
        .options(
            joinedload(Booking.slot),
            joinedload(Booking.artist),
            joinedload(Booking.producer),
        )
        .filter(Booking.status == BookingStatus.CONFIRMED)
    )
    q = _only_future(q)  # solo eventi futuri
    q = q.order_by(AvailabilitySlot.date.asc(), AvailabilitySlot.start_time.asc())

    out = []
    for b in q.all():
        s = b.slot
        out.append(
            {
                "id": b.id,
                "date": s.date.isoformat(),
                "start_time": str(s.start_time)[:5],
                "end_time": str(s.end_time)[:5],
                "artist_name": (b.artist.display_name or b.artist.email)
                if b.artist
                else None,
                "producer_name": (b.producer.display_name or b.producer.email)
                if b.producer
                else None,
            }
        )
    return out