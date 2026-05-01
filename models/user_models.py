# ============================================================
# models/user_models.py — Pydantic schemas for Users
# ============================================================

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional





class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Response body for POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str


class UserProfileResponse(BaseModel):
    """Public user profile returned by protected endpoints."""

    user_id: int
    name: str
    email: str
    role: str
