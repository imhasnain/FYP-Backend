# ============================================================
# routers/auth.py — Authentication endpoints
#   POST /auth/register
#   POST /auth/login
# ============================================================

import logging
import pyodbc
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.user_models import LoginRequest, LoginResponse
from utils.auth_utils import create_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """
    Authenticate a user and return a JWT access token.

    Steps:
      1. Look up the user by email.
      2. Verify the password.
      3. Generate a signed JWT token.
      4. Return token + user_id + role.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ── 1. Look up user ───────────────────────────────
        cursor.execute(
            "SELECT user_id, password, role FROM Users WHERE email = ?",
            (payload.email,),
        )
        row = cursor.fetchone()

        if not row:
            # Do NOT reveal whether the email exists — use generic message
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        user_id, stored_password, role = row.user_id, row.password, row.role

        # ── 2. Verify password ────────────────────────────
        if payload.password != stored_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        # ── 3. Generate JWT ───────────────────────────────
        token = create_token(user_id=user_id, role=role)
        logger.info("User logged in: user_id=%d role=%s", user_id, role)

        return LoginResponse(
            access_token=token,
            user_id=user_id,
            role=role,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Login error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again.",
        )
    finally:
        conn.close()
