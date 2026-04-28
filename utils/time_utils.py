# ============================================================
# utils/time_utils.py — UTC datetime helpers
# ============================================================

from datetime import datetime, timezone
from typing import Tuple, Optional
import pyodbc
import logging

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """
    Return the current UTC datetime as a timezone-aware object.
    Always use this instead of datetime.utcnow() (which is naive).
    """
    return datetime.now(timezone.utc)


def format_dt(dt: Optional[datetime]) -> Optional[str]:
    """
    Format a datetime object as an ISO 8601 string (UTC).
    Returns None if *dt* is None.

    Example output: '2024-11-15T08:32:00+00:00'
    """
    if dt is None:
        return None
    # If naive (no tzinfo), assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def stage_time_range(
    session_id: int,
    stage_number: int,
    conn: pyodbc.Connection,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Query Q_Responses to find the earliest and latest timestamp
    recorded for a given stage within a session.

    Used by the risk engine and reporting to understand when each
    questionnaire stage occurred.

    Returns:
        (start_dt, end_dt) — both may be None if no responses found.
    """
    sql = """
        SELECT
            MIN(timestamp) AS stage_start,
            MAX(timestamp) AS stage_end
        FROM Q_Responses
        WHERE session_id = ?
          AND stage_number = ?
    """
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (session_id, stage_number))
        row = cursor.fetchone()
        if row:
            return row.stage_start, row.stage_end
        return None, None
    except pyodbc.Error as exc:
        logger.error(
            "stage_time_range failed for session=%s stage=%s: %s",
            session_id, stage_number, exc,
        )
        return None, None
