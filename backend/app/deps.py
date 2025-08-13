from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .core.security import decode_token
from .models.user import User, Role

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    data = decode_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.email == data["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

def require_role(*allowed: Role):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dep

def auth_any_role(user: User = Depends(get_current_user)) -> User:
    return user

def auth_manager(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.MANAGER:
        raise HTTPException(status_code=403, detail="Solo manager")
    return user

def auth_producer(user: User = Depends(get_current_user)) -> User:
    if user.role not in (Role.PRODUCER, Role.MANAGER):
        raise HTTPException(status_code=403, detail="Solo produttori/manager")
    return user