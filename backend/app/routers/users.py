from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.user import User, Role

router = APIRouter(prefix="/users", tags=["users"])

@router.get("")
def list_users(role: Role | None = None, db: Session = Depends(get_db)):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    # ordina prima per display_name se presente, altrimenti per email
    return q.order_by(User.display_name.is_(None), User.display_name, User.email).all()