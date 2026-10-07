"""routers/auth.py — Authentication endpoints (login + register)."""

import logging
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.user_models import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from utils.auth_utils import create_token
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """Authenticate user and return a JWT token."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, name, password, role FROM Users WHERE email = ?",
            (payload.email,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

        # Plain text password comparison
        if payload.password != row.password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

        token = create_token(user_id=row.user_id, role=row.role)
        logger.info("User logged in: user_id=%d role=%s", row.user_id, row.role)
        return LoginResponse(access_token=token, user_id=row.user_id, role=row.role, name=row.name)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Login error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed.")
    finally:
        conn.close()


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
    """Create a new user with plain text password."""
    if payload.role not in ("student", "teacher"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role must be 'student' or 'teacher'.")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM Users WHERE email = ?", (payload.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")

        # Store password as plain text
        cursor.execute(
            "INSERT INTO Users (name, email, password, role) OUTPUT INSERTED.user_id VALUES (?, ?, ?, ?)",
            (payload.name, payload.email, payload.password, payload.role),
        )
        user_id = cursor.fetchone()[0]

        if payload.role == "student":
            cursor.execute("INSERT INTO Students (user_id) VALUES (?)", (user_id,))
        else:
            cursor.execute("INSERT INTO Teachers (user_id) VALUES (?)", (user_id,))

        conn.commit()
        logger.info("User registered: user_id=%d role=%s", user_id, payload.role)
        return RegisterResponse(user_id=user_id)

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("Register error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed.")
    finally:
        conn.close()
