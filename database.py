# ============================================================
# database.py — SQL Server connection factory via pyodbc
# Uses Windows Authentication by default; falls back to
# SQL Server Auth when DB_USER / DB_PASSWORD are set.
# ============================================================

import time
import logging
from contextlib import contextmanager

import pyodbc
from config import settings

logger = logging.getLogger(__name__)

# Maximum number of connection attempts before giving up
MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 1


def _build_conn_str() -> str:
    """
    Build the pyodbc connection string from settings.

    Returns:
        Connection string for pyodbc.connect().
    """
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
    """
    Create and return a new pyodbc connection to SQL Server
    with retry logic (3 attempts, 2-second delay between retries).

    Connection strategy:
      - If DB_TRUSTED_CONNECTION is True  → Windows Authentication
      - Otherwise                         → SQL Server Authentication

    The caller is responsible for closing the connection.

    Returns:
        An open pyodbc.Connection with autocommit=False.

    Raises:
        pyodbc.Error: If all retry attempts fail.
    """
    conn_str = _build_conn_str()
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn = pyodbc.connect(conn_str, timeout=5)
            conn.autocommit = False
            if attempt > 1:
                logger.info("Database connection succeeded on attempt %d.", attempt)
            return conn
        except pyodbc.Error as exc:
            last_exc = exc
            logger.warning(
                "Database connection attempt %d/%d failed: %s",
                attempt, MAX_RETRIES, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error("All %d database connection attempts failed.", MAX_RETRIES)
    raise last_exc


def test_connection() -> bool:
    """
    Test the database connection by executing a simple query.

    Returns:
        True if the connection succeeds, False otherwise.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
        conn.close()
        return True
    except Exception as exc:
        logger.error("test_connection failed: %s", exc)
        return False


@contextmanager
def db_cursor():
    """
    Context manager that opens a database connection, yields a cursor,
    commits on success, rolls back on error, and always closes the connection.

    Usage:
        with db_cursor() as cursor:
            cursor.execute("SELECT ...")
            rows = cursor.fetchall()
    """
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


# ── Self-test ─────────────────────────────────────────────
if __name__ == "__main__":
    """
    Run this file directly to verify the database connection:
        python database.py
    """
    print("Testing database connection...")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE() AS server_time")
        row = cursor.fetchone()
        print(f"SUCCESS: Connected! SQL Server time: {row.server_time}")
        conn.close()
    except Exception as exc:
        print(f"ERROR: Connection failed: {exc}")
