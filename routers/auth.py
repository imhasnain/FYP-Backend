# ============================================================
# routers/auth.py — Authentication endpoints
#   POST /auth/register
#   POST /auth/login
# ============================================================

import logging
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.user_models import RegisterRequest, LoginRequest, LoginResponse
from utils.auth_utils import hash_password, verify_password, create_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    """
    Register a new user (student, teacher, or psychologist).

    Steps:
      1. Check the email is not already taken.
      2. Hash the password with bcrypt.
      3. Insert the base record into Users.
      4. Insert a role-specific row into Students or Teachers.

    Returns a success message with the new user_id.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ── 1. Duplicate email check ──────────────────────
        cursor.execute(
            "SELECT user_id FROM Users WHERE email = ?",
            (payload.email,),
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        # ── 2. Hash the password ──────────────────────────
        hashed = hash_password(payload.password)

        # ── 3. Insert into Users ──────────────────────────
        cursor.execute(
            """
            INSERT INTO Users (name, email, password, role)
            OUTPUT INSERTED.user_id
            VALUES (?, ?, ?, ?)
            """,
            (payload.name, payload.email, hashed, payload.role),
        )
        row = cursor.fetchone()
        new_user_id: int = row[0]

        # ── 4. Role-specific extension table ─────────────
        if payload.role == "student":
            cursor.execute(
                """
                INSERT INTO Students (user_id, cgpa_trend, attendance_drop)
                VALUES (?, ?, ?)
                """,
                (
                    new_user_id,
                    payload.cgpa_trend if payload.cgpa_trend is not None else 0.0,
                    payload.attendance_drop if payload.attendance_drop is not None else 0.0,
                ),
            )
        elif payload.role == "teacher":
            cursor.execute(
                """
                INSERT INTO Teachers (user_id, workload_hrs, class_count)
                VALUES (?, ?, ?)
                """,
                (
                    new_user_id,
                    payload.workload_hrs if payload.workload_hrs is not None else 0.0,
                    payload.class_count if payload.class_count is not None else 0,
                ),
            )

        conn.commit()
        logger.info("New user registered: user_id=%d role=%s", new_user_id, payload.role)

        return {
            "message": "Registration successful.",
            "user_id": new_user_id,
            "role": payload.role,
        }

    except HTTPException:
        raise  # Re-raise HTTP exceptions unchanged
    except Exception as exc:
        conn.rollback()
        logger.exception("Registration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        )
    finally:
        conn.close()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    """
    Authenticate a user and return a JWT access token.

    Steps:
      1. Look up the user by email.
      2. Verify the bcrypt password.
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

        user_id, stored_hash, role = row.user_id, row.password, row.role

        # ── 2. Verify password ────────────────────────────
        if not verify_password(payload.password, stored_hash):
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
