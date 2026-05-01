# ============================================================
# db_migrations.py — Idempotent database schema migrations
#
# Adds new columns and tables required by the ML pipeline.
# Safe to run multiple times — checks existence before ALTER/CREATE.
#
# Usage:
#   python db_migrations.py
# ============================================================

import sys
import logging
import pyodbc
from database import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def _column_exists(cursor, table: str, column: str) -> bool:
    """
    Check if a column exists in a table using INFORMATION_SCHEMA.

    Args:
        cursor: An open pyodbc cursor.
        table:  Table name (e.g. 'SensorData').
        column: Column name (e.g. 'recorded_at').

    Returns:
        True if the column already exists.
    """
    cursor.execute(
        """
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def _table_exists(cursor, table: str) -> bool:
    """
    Check if a table exists using INFORMATION_SCHEMA.

    Args:
        cursor: An open pyodbc cursor.
        table:  Table name (e.g. 'MH_Results').

    Returns:
        True if the table already exists.
    """
    cursor.execute(
        """
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME = ?
        """,
        (table,),
    )
    return cursor.fetchone() is not None


def run_migrations():
    """
    Execute all schema migrations. Each step is idempotent:
    it checks for existence before making changes.

    Migrations:
      1. Add recorded_at, bp_systolic, bp_diastolic, data_type to SensorData.
      2. Add stage_number to Q_Responses.
      3. Create MH_Results table if it does not exist.
    """
    conn = get_connection()
    cursor = conn.cursor()

    print("=" * 60)
    print("Running database migrations...")
    print("=" * 60)

    # ── 1. SensorData — add columns ──────────────────────────
    sensor_columns = [
        ("recorded_at", "DATETIME DEFAULT GETDATE()"),
        ("bp_systolic", "INT NULL"),
        ("bp_diastolic", "INT NULL"),
        ("data_type", "VARCHAR(20) NULL"),
    ]

    for col_name, col_def in sensor_columns:
        if _column_exists(cursor, "SensorData", col_name):
            print(f"  [OK]   SensorData.{col_name} -- already exists, skipping.")
        else:
            try:
                sql = f"ALTER TABLE SensorData ADD {col_name} {col_def}"
                cursor.execute(sql)
                conn.commit()
                print(f"  [OK]   SensorData.{col_name} -- added successfully.")
            except pyodbc.Error as exc:
                conn.rollback()
                print(f"  [FAIL] SensorData.{col_name} -- FAILED: {exc}")

    # ── 2. Q_Responses — add stage_number ────────────────────
    if _column_exists(cursor, "Q_Responses", "stage_number"):
        print(f"  [OK]   Q_Responses.stage_number -- already exists, skipping.")
    else:
        try:
            cursor.execute("ALTER TABLE Q_Responses ADD stage_number INT NULL")
            conn.commit()
            print(f"  [OK]   Q_Responses.stage_number -- added successfully.")
        except pyodbc.Error as exc:
            conn.rollback()
            print(f"  [FAIL] Q_Responses.stage_number -- FAILED: {exc}")

    # ── 3. MH_Results table ──────────────────────────────────
    if _table_exists(cursor, "MH_Results"):
        print(f"  [OK]   MH_Results table -- already exists, skipping.")
    else:
        try:
            cursor.execute(
                """
                CREATE TABLE MH_Results (
                    result_id           INT IDENTITY(1,1) PRIMARY KEY,
                    session_id          INT REFERENCES Sessions(session_id),
                    user_role           VARCHAR(20),
                    emotional_score     FLOAT,
                    functional_score    FLOAT,
                    context_score       FLOAT,
                    isolation_score     FLOAT,
                    critical_score      FLOAT,
                    performance_score   FLOAT,
                    eeg_stress_index    FLOAT,
                    eeg_alpha_power     FLOAT,
                    eeg_theta_power     FLOAT,
                    hr_mean             FLOAT,
                    bp_avg_systolic     FLOAT,
                    bp_avg_diastolic    FLOAT,
                    pulse_avg           FLOAT,
                    dominant_emotion    VARCHAR(50),
                    emotion_distress_score FLOAT,
                    final_score         FLOAT,
                    recommendation      VARCHAR(50),
                    confidence          FLOAT,
                    calculated_at       DATETIME DEFAULT GETDATE()
                )
                """
            )
            conn.commit()
            print(f"  [OK]   MH_Results table -- created successfully.")
        except pyodbc.Error as exc:
            conn.rollback()
            print(f"  [FAIL] MH_Results table -- FAILED: {exc}")

    # ── 4. Add missing columns to MH_Results if it exists ────
    #    (covers case where table was created in a prior version
    #     without all columns)
    mh_extra_columns = [
        ("user_role", "VARCHAR(20) NULL"),
        ("performance_score", "FLOAT NULL"),
        ("eeg_stress_index", "FLOAT NULL"),
        ("eeg_alpha_power", "FLOAT NULL"),
        ("eeg_theta_power", "FLOAT NULL"),
        ("hr_mean", "FLOAT NULL"),
        ("bp_avg_systolic", "FLOAT NULL"),
        ("bp_avg_diastolic", "FLOAT NULL"),
        ("pulse_avg", "FLOAT NULL"),
        ("emotion_distress_score", "FLOAT NULL"),
        ("recommendation", "VARCHAR(50) NULL"),
        ("confidence", "FLOAT NULL"),
    ]

    if _table_exists(cursor, "MH_Results"):
        for col_name, col_def in mh_extra_columns:
            if not _column_exists(cursor, "MH_Results", col_name):
                try:
                    sql = f"ALTER TABLE MH_Results ADD {col_name} {col_def}"
                    cursor.execute(sql)
                    conn.commit()
                    print(f"  [OK]   MH_Results.{col_name} -- added successfully.")
                except pyodbc.Error as exc:
                    conn.rollback()
                    print(f"  [FAIL] MH_Results.{col_name} -- FAILED: {exc}")

    # ── 5. EmotionImages table ───────────────────────────────
    if _table_exists(cursor, "EmotionImages"):
        print(f"  [OK]   EmotionImages table -- already exists, skipping.")
    else:
        try:
            cursor.execute(
                """
                CREATE TABLE EmotionImages (
                    image_id INT IDENTITY(1,1) PRIMARY KEY,
                    user_id INT REFERENCES Users(user_id),
                    session_id INT REFERENCES Sessions(session_id),
                    image_name VARCHAR(255),
                    captured_at DATETIME DEFAULT GETDATE()
                )
                """
            )
            conn.commit()
            print(f"  [OK]   EmotionImages table -- created successfully.")
        except pyodbc.Error as exc:
            conn.rollback()
            print(f"  [FAIL] EmotionImages table -- FAILED: {exc}")

    # ── 6. FacialEmotions & EmotionImages — add columns ────────────────
    if _table_exists(cursor, "FacialEmotions"):
        if not _column_exists(cursor, "FacialEmotions", "image_id"):
            try:
                cursor.execute("ALTER TABLE FacialEmotions ADD image_id INT REFERENCES EmotionImages(image_id) NULL")
                conn.commit()
                print(f"  [OK]   FacialEmotions.image_id -- added successfully.")
            except pyodbc.Error as exc:
                conn.rollback()
                print(f"  [FAIL] FacialEmotions.image_id -- FAILED: {exc}")
                
        if not _column_exists(cursor, "FacialEmotions", "stage_number"):
            try:
                cursor.execute("ALTER TABLE FacialEmotions ADD stage_number INT NULL")
                conn.commit()
                print(f"  [OK]   FacialEmotions.stage_number -- added successfully.")
            except pyodbc.Error as exc:
                conn.rollback()
                print(f"  [FAIL] FacialEmotions.stage_number -- FAILED: {exc}")
                
    if _table_exists(cursor, "EmotionImages"):
        if not _column_exists(cursor, "EmotionImages", "stage_number"):
            try:
                cursor.execute("ALTER TABLE EmotionImages ADD stage_number INT NULL")
                conn.commit()
                print(f"  [OK]   EmotionImages.stage_number -- added successfully.")
            except pyodbc.Error as exc:
                conn.rollback()
                print(f"  [FAIL] EmotionImages.stage_number -- FAILED: {exc}")

    # ── 7. Seed Demo Users ───────────────────────────────────
    cursor.execute("SELECT 1 FROM Users WHERE email = 'student@clinic.edu'")
    if cursor.fetchone():
        print("  [OK]   Demo Student -- already exists, skipping.")
    else:
        try:
            cursor.execute(
                """
                INSERT INTO Users (name, email, password, role)
                OUTPUT INSERTED.user_id
                VALUES ('Demo Student', 'student@clinic.edu', 'password123', 'student')
                """
            )
            student_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO Students (user_id, cgpa_trend, attendance_drop) VALUES (?, -0.2, 5.0)",
                (student_id,)
            )
            conn.commit()
            print("  [OK]   Demo Student -- created successfully.")
        except pyodbc.Error as exc:
            conn.rollback()
            print(f"  [FAIL] Demo Student -- FAILED: {exc}")

    cursor.execute("SELECT 1 FROM Users WHERE email = 'teacher@clinic.edu'")
    if cursor.fetchone():
        print("  [OK]   Demo Teacher -- already exists, skipping.")
    else:
        try:
            cursor.execute(
                """
                INSERT INTO Users (name, email, password, role)
                OUTPUT INSERTED.user_id
                VALUES ('Demo Teacher', 'teacher@clinic.edu', 'password123', 'teacher')
                """
            )
            teacher_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO Teachers (user_id, workload_hrs, class_count) VALUES (?, 24.5, 4)",
                (teacher_id,)
            )
            conn.commit()
            print("  [OK]   Demo Teacher -- created successfully.")
        except pyodbc.Error as exc:
            conn.rollback()
            print(f"  [FAIL] Demo Teacher -- FAILED: {exc}")

    conn.close()

    print()
    print("=" * 60)
    print("Migrations complete.")
    print("=" * 60)


if __name__ == "__main__":
    run_migrations()
