from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets

from ..database import get_db, Base, engine
from ..models.user import User, Role
from ..models import password_reset as pr_models
from ..schemas.auth import RegisterIn, LoginIn, TokenOut, UserOut
from ..core.security import hash_password, verify_password, create_access_token
from ..deps import get_current_user
from ..services.email_gmail import send_email_html
from ..config import settings
from ..schemas.auth import ForgotIn, ResetIn

router = APIRouter(prefix="/auth", tags=["auth"])

@router.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

@router.post("/register", response_model=UserOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email già registrata")

    # accettiamo solo ARTIST o PRODUCER; default ARTIST se non passato
    role = payload.role or Role.ARTIST
    if role == Role.MANAGER:
        raise HTTPException(status_code=400, detail="Non è possibile registrarsi come manager")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role=role,
        # se in modello esiste requested_role, ignoriamolo
        is_active=True,
    )
    db.add(user); db.commit(); db.refresh(user)
    return user

@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    return TokenOut(access_token=create_access_token(sub=user.email))

@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current

@router.post("/forgot")
def forgot(payload: ForgotIn, db: Session = Depends(get_db)):
    email = payload.email
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"ok": True}

    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=2)
    item = pr_models.PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires,
        used=False
    )
    db.add(item)
    db.commit()

    reset_link = f"{settings.PUBLIC_BASE_URL}/frontend/auth/reset.html?token={token}"
    html = f"""
    <div style="font-family:Inter,Arial,sans-serif;color:#111;font-size:15px">
      <p>Ciao,</p>
      <p>Per reimpostare la password clicca qui:</p>
      <p><a href="{reset_link}">{reset_link}</a></p>
      <p>Se non hai richiesto questo cambio, ignora questa email.</p>
    </div>
    """

    try:
        send_email_html(user.email, "Reset password", html)
    except Exception as e:
        print("Email error:", e, "| Link manuale:", reset_link)

    resp = {"ok": True}
    if settings.APP_ENV == "dev":
        resp["dev_reset_link"] = reset_link
    return resp

@router.post("/reset")
def reset_password(payload: ResetIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rec = db.query(pr_models.PasswordResetToken)\
            .filter(pr_models.PasswordResetToken.token == payload.token)\
            .first()
    if not rec or rec.used or rec.expires_at < now:
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")

    user = db.query(User).filter(User.id == rec.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Utente non trovato")

    user.password_hash = hash_password(payload.new_password)
    rec.used = True
    db.commit()
    return {"ok": True}