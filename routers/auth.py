"""routers/auth.py — Authentication endpoints"""

import logging
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.user_models import LoginRequest, LoginResponse
from utils.auth_utils import create_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, password, role FROM Users WHERE email = ?",
            (payload.email,),
        )
        row = cursor.fetchone()

        if not row or payload.password != row.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        token = create_token(user_id=row.user_id, role=row.role)
        logger.info("User logged in: user_id=%d role=%s", row.user_id, row.role)

        return LoginResponse(access_token=token, user_id=row.user_id, role=row.role)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Login error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed.")
    finally:
        conn.close()
