# ============================================================
# utils/response_utils.py — Standard API response helpers
#
# All endpoints should use these helpers to maintain a
# consistent response envelope across the entire API.
# ============================================================

from typing import Any, Optional


def success(
    data: Any = None,
    message: str = "Request successful.",
) -> dict:
    """
    Build a standard success response envelope.

    Args:
        data:    The response payload (dict, list, or None).
        message: Human-readable success message.

    Returns:
        Dict in the format:
        { "status": "success", "message": str, "data": ... }
    """
    return {
        "status": "success",
        "message": message,
        "data": data,
    }


def error_response(
    message: str = "An error occurred.",
    data: Any = None,
) -> dict:
    """
    Build a standard error response envelope (for non-HTTP-exception cases).

    For most errors, prefer raising fastapi.HTTPException directly.
    This helper is useful when you need to return an error body inside
    a 200 response (e.g., partial success scenarios).

    Args:
        message: Human-readable error message.
        data:    Optional error details.

    Returns:
        Dict in the format:
        { "status": "error", "message": str, "data": ... }
    """
    return {
        "status": "error",
        "message": message,
        "data": data,
    }
