from pydantic import BaseModel, EmailStr
from ..models.user import Role

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
    role: Role  # ARTIST | PRODUCER | MANAGER

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserOut(BaseModel):
    id: int
    email: EmailStr
    display_name: str | None
    role: Role
    class Config:
        from_attributes = True

class ForgotIn(BaseModel):
    email: EmailStr

class ResetIn(BaseModel):
    token: str
    new_password: str