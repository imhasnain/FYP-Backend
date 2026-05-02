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

    # ── 8. Replace questionnaire stages & questions ───────────
    #    Detects old question bank (< 50 questions) and replaces it.
    cursor.execute("SELECT COUNT(*) FROM Q_Questions")
    q_count = cursor.fetchone()[0]

    if q_count >= 50:
        print("  [OK]   Q_Questions -- already has 50+ questions, skipping.")
    else:
        try:
            print("  [INFO] Replacing questionnaire stages and questions...")
            # Clear existing data (responses first due to FK, then questions, then stages)
            cursor.execute("DELETE FROM Q_Responses")
            cursor.execute("DELETE FROM Q_Questions")
            cursor.execute("DELETE FROM Q_Stages")
            conn.commit()

            # Re-seed stages
            cursor.executemany(
                "INSERT INTO Q_Stages (stage_number, stage_name, target_role, threshold) VALUES (?, ?, ?, ?)",
                [
                    (1, "Emotional State Screening", "both", 8.0),
                    (2, "Functional Impact",          "both", 8.0),
                    (3, "Contextual Mental Strain",   "both", 8.0),
                    (4, "Psychological Risk",          "both", 8.0),
                    (5, "Critical Risk Screening",     "both", 5.0),
                ],
            )
            conn.commit()

            # Fetch stage IDs in order
            cursor.execute("SELECT stage_id, stage_number FROM Q_Stages ORDER BY stage_number")
            stage_map = {row[1]: row[0] for row in cursor.fetchall()}
            s1, s2, s3, s4, s5 = stage_map[1], stage_map[2], stage_map[3], stage_map[4], stage_map[5]

            questions = [
                # Stage 1 – Emotional State Screening
                (s1, "How often do you feel nervous or worried?", 1.0),
                (s1, "How often do you feel sad or down?", 1.0),
                (s1, "How often do everyday tasks feel like too much?", 1.0),
                (s1, "How often do you feel restless or unable to relax?", 1.0),
                (s1, "How often do you feel emotionally worn out?", 1.0),
                (s1, "How often do you worry too much about your responsibilities?", 1.0),
                (s1, "How often do you feel irritable for no clear reason?", 1.0),
                (s1, "How often do you feel like you have no energy to start things?", 1.0),
                (s1, "How often does your mind feel tired or foggy?", 1.0),
                (s1, "How often do you feel scared without knowing why?", 1.0),
                # Stage 2 – Functional Impact
                (s2, "How often does stress make it hard to focus?", 1.0),
                (s2, "How often does stress make you forgetful?", 1.0),
                (s2, "How often do you have trouble sleeping?", 1.0),
                (s2, "How often do you wake up feeling tired?", 1.0),
                (s2, "How often has your eating changed because of stress?", 1.0),
                (s2, "How often have you lost interest in your work or studies?", 1.0),
                (s2, "How often do you feel mentally drained by the end of the day?", 1.0),
                (s2, "How often do you put off tasks because they feel stressful?", 1.0),
                (s2, "How often has your performance at work or school dropped?", 1.0),
                (s2, "How often does stress cause you to avoid people or social situations?", 1.0),
                # Stage 3 – Contextual Mental Strain
                (s3, "How often do deadlines make you anxious?", 1.0),
                (s3, "How often do heavy workloads or long study hours drain you?", 1.0),
                (s3, "How often do exams, evaluations, or performance reviews cause you stress?", 1.0),
                (s3, "How often do you feel pressure from family or institution expectations?", 1.0),
                (s3, "How often do you feel unsupported by peers, managers, or teachers?", 1.0),
                (s3, "How often does comparing yourself to others stress you?", 1.0),
                (s3, "How often do money or job-security concerns affect your peace of mind?", 1.0),
                (s3, "How often do you struggle to balance work/study and personal life?", 1.0),
                (s3, "How often do strict rules, attendance, or schedules make you feel anxious?", 1.0),
                (s3, "How often do you feel your efforts are ignored or not valued?", 1.0),
                # Stage 4 – Psychological Risk
                (s4, "How often do you feel cut off from people around you?", 1.0),
                (s4, "How often do you feel hopeless about your future?", 1.0),
                (s4, "How often do you feel worthless?", 1.0),
                (s4, "How often do you feel emotionally numb or empty?", 1.0),
                (s4, "How often do you feel your problems are too big to handle?", 1.0),
                (s4, "How often do your emotions change quickly and without warning?", 1.0),
                (s4, "How often do you get frustrated very easily?", 1.0),
                (s4, "How often do you feel like giving up on your daily duties?", 1.0),
                (s4, "How often do you avoid meeting or talking to others?", 1.0),
                (s4, "How often do you feel like your life has no purpose?", 1.0),
                # Stage 5 – Critical Risk Screening
                (s5, "Have you had thoughts of hurting yourself?", 2.0),
                (s5, "Have you felt that life is not worth living?", 2.0),
                (s5, "Have you wished you could just disappear?", 2.0),
                (s5, "Have you stopped doing things you used to enjoy?", 1.0),
                (s5, "Have you felt completely trapped in your situation?", 1.5),
                (s5, "Have you felt like a burden to others?", 1.5),
                (s5, "Have you lost interest in taking care of your health or safety?", 1.5),
                (s5, "Have you felt that no one would understand what you are going through?", 1.0),
                (s5, "Have you thought about ending your life, even if you would not act on it?", 2.0),
                (s5, "Have you felt that things will never get better no matter what you do?", 1.5),
            ]
            cursor.executemany(
                "INSERT INTO Q_Questions (stage_id, question_text, weight) VALUES (?, ?, ?)",
                questions,
            )
            conn.commit()
            print(f"  [OK]   Q_Stages & Q_Questions -- replaced with 5 stages / 50 questions.")
        except Exception as exc:
            conn.rollback()
            print(f"  [FAIL] Questionnaire replacement -- FAILED: {exc}")

    conn.close()

    print()
    print("=" * 60)
    print("Migrations complete.")
    print("=" * 60)


if __name__ == "__main__":
    run_migrations()

