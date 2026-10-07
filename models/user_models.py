"""models/user_models.py — Pydantic schemas for Users."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str  # 'student' or 'teacher'


class RegisterResponse(BaseModel):
    user_id: int
    message: str = "Registration successful."
