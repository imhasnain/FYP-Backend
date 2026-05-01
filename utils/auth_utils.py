# ============================================================
# utils/auth_utils.py — JWT creation, decoding & FastAPI dependency
# ============================================================

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from config import settings

logger = logging.getLogger(__name__)

# ── OAuth2 token URL (used by Swagger UI "Authorize" button) ──
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")




# ─────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────

def create_token(user_id: int, role: str) -> str:
    """
    Create a signed JWT token encoding user_id and role.

    Token expires after TOKEN_EXPIRE_MINUTES (default 480 = 8 hours).
    Returns the encoded JWT string.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),   # Subject — stored as string for JWT compliance
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Returns a dict with keys: user_id (int), role (str).
    Raises HTTPException 401 if the token is invalid or expired.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id_str: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")

        if user_id_str is None or role is None:
            raise credentials_exc

        return {"user_id": int(user_id_str), "role": role}

    except JWTError as exc:
        logger.warning("JWT decode error: %s", exc)
        raise credentials_exc


# ─────────────────────────────────────────────────────────────
# FastAPI dependency
# ─────────────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency that extracts the current authenticated user
    from the Authorization: Bearer <token> header.

    Returns dict with user_id and role.
    Raises HTTP 401 if token is missing or invalid.

    Usage:
        @router.get("/protected")
        def endpoint(user=Depends(get_current_user)):
            ...
    """
    return decode_token(token)
