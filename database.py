"""
database.py — SQL Server connection factory via pyodbc.

Uses Windows Authentication by default.
Set DB_TRUSTED_CONNECTION=false and DB_USER/DB_PASSWORD in .env for SQL Auth.
"""

import time
import logging
from contextlib import contextmanager

import pyodbc
from config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1


def _build_conn_str() -> str:
    if settings.DB_TRUSTED_CONNECTION:
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            f"Trusted_Connection=yes;"
        )
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={settings.DB_SERVER};"
        f"DATABASE={settings.DB_NAME};"
        f"UID={settings.DB_USER};"
        f"PWD={settings.DB_PASSWORD};"
    )


def get_connection() -> pyodbc.Connection:
    """Open a new pyodbc connection with retry logic. Caller must close it."""
    conn_str = _build_conn_str()
    last_exc = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            conn = pyodbc.connect(conn_str, timeout=5)
            conn.autocommit = False
            return conn
        except pyodbc.Error as exc:
            last_exc = exc
            logger.warning("DB connection attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    raise last_exc


def test_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        conn = get_connection()
        conn.cursor().execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False


@contextmanager
def db_cursor():
    """Context manager: yields a cursor, commits on success, rolls back on error."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
