# ============================================================
# models/user_models.py — Pydantic schemas for Users
# ============================================================

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional


class RegisterRequest(BaseModel):
    """
    Request body for POST /auth/register.

    Student fields  (required when role='student'):
        cgpa_trend      — positive = improving GPA, negative = declining
        attendance_drop — positive = more absences (percentage dropped)

    Teacher fields  (required when role='teacher'):
        workload_hrs    — weekly teaching hours
        class_count     — number of classes currently teaching
    """

    name: str
    email: EmailStr
    password: str
    role: str  # 'student' | 'teacher' | 'psychologist'

    # ── Student-specific fields ────────────────────────────
    cgpa_trend: Optional[float] = 0.0        # negative = declining GPA
    attendance_drop: Optional[float] = 0.0   # % attendance lost

    # ── Teacher-specific fields ────────────────────────────
    workload_hrs: Optional[float] = 0.0      # weekly hours
    class_count: Optional[int] = 0           # number of classes

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Ensure role is one of the accepted values."""
        allowed = {"student", "teacher", "psychologist"}
        if v.lower() not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce a minimum password length of 6 characters."""
        if len(v) < 6:
            raise ValueError("password must be at least 6 characters long")
        return v


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
