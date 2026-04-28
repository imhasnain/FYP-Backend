"""
test_apis.py — Complete API test suite for the Virtual Clinic backend.

Tests every endpoint in the correct order with realistic sample data.
Verifies HTTP status codes AND prints the database state after key steps.

Run from the Backend/ folder (with venv active and server running):
    python test_apis.py

Requirements:
    pip install requests pyodbc
    Server must be running: uvicorn main:app --reload --port 8000
"""

import base64
import json
import sys
import time
from datetime import datetime

import requests

# ── Configuration ─────────────────────────────────────────
BASE_URL = "http://localhost:8000"
HEADERS  = {"Content-Type": "application/json"}

# Counters for pass/fail
PASSED = 0
FAILED = 0


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _print_section(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def _check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    status = "✅ PASS" if condition else "❌ FAIL"
    suffix = f"  → {detail}" if detail else ""
    print(f"  {status}  {label}{suffix}")
    if condition:
        PASSED += 1
    else:
        FAILED += 1


def post(path: str, body: dict, token: str = None) -> requests.Response:
    """POST helper with optional Bearer token."""
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE_URL}{path}", headers=h, json=body, timeout=15)


def get(path: str, token: str = None) -> requests.Response:
    """GET helper with optional Bearer token."""
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE_URL}{path}", headers=h, timeout=15)


def db_query(sql: str, params: tuple = ()):
    """Run a raw SQL query and return all rows (for verification)."""
    try:
        import pyodbc
        from config import settings

        if settings.DB_TRUSTED_CONNECTION:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={settings.DB_SERVER};DATABASE={settings.DB_NAME};Trusted_Connection=yes;"
            )
        else:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={settings.DB_SERVER};DATABASE={settings.DB_NAME};"
                f"UID={settings.DB_USER};PWD={settings.DB_PASSWORD};"
            )

        conn   = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows   = cursor.fetchall()
        cols   = [col[0] for col in cursor.description]
        conn.close()
        return cols, rows
    except Exception as exc:
        print(f"    ⚠️  DB check skipped: {exc}")
        return [], []


def db_print(label: str, sql: str, params: tuple = ()) -> None:
    """Print a DB query result as a simple table."""
    cols, rows = db_query(sql, params)
    if not cols:
        return
    print(f"\n  📋 DB check — {label}")
    print("  " + " | ".join(f"{c:<22}" for c in cols))
    print("  " + "-" * (25 * len(cols)))
    for row in rows:
        print("  " + " | ".join(f"{str(v):<22}" for v in row))


# ─────────────────────────────────────────────────────────
# 0. Health check
# ─────────────────────────────────────────────────────────

_print_section("0. Health Check")

resp = requests.get(f"{BASE_URL}/", timeout=5)
_check("GET /  → 200 OK",         resp.status_code == 200)
_check("status == 'running'",     resp.json().get("status") == "running")
print(f"  Response: {resp.json()}")


# ─────────────────────────────────────────────────────────
# 1. Register Users
# ─────────────────────────────────────────────────────────

_print_section("1. Auth — Register")

# -- Student --
student_email = f"student_{int(time.time())}@uni.edu"
resp = post("/auth/register", {
    "name":             "Ahmed Raza",
    "email":            student_email,
    "password":         "Test@1234",
    "role":             "student",
    "cgpa_trend":       -0.35,     # declining GPA
    "attendance_drop":  12.5,      # 12.5% attendance drop
})
_check("POST /auth/register (student) → 201", resp.status_code == 201)
student_data = resp.json()
student_user_id = student_data.get("user_id")
print(f"  Response: {student_data}")

db_print(
    "Users + Students after student registration",
    """
    SELECT u.user_id, u.name, u.role,
           s.student_id, s.cgpa_trend, s.attendance_drop
    FROM Users u
    LEFT JOIN Students s ON u.user_id = s.user_id
    WHERE u.user_id = ?
    """,
    (student_user_id,),
)

# -- Teacher --
teacher_email = f"teacher_{int(time.time())}@uni.edu"
resp = post("/auth/register", {
    "name":         "Dr. Sara Khan",
    "email":        teacher_email,
    "password":     "Test@5678",
    "role":         "teacher",
    "workload_hrs": 24.0,   # 24 hrs/week
    "class_count":  6,
})
_check("POST /auth/register (teacher) → 201", resp.status_code == 201)
teacher_data = resp.json()
teacher_user_id = teacher_data.get("user_id")
print(f"  Response: {teacher_data}")

db_print(
    "Users + Teachers after teacher registration",
    """
    SELECT u.user_id, u.name, u.role,
           t.teacher_id, t.workload_hrs, t.class_count
    FROM Users u
    LEFT JOIN Teachers t ON u.user_id = t.user_id
    WHERE u.user_id = ?
    """,
    (teacher_user_id,),
)

# -- Psychologist --
psychologist_email = f"psych_{int(time.time())}@clinic.edu"
resp = post("/auth/register", {
    "name":     "Dr. Zara Ahmed",
    "email":    psychologist_email,
    "password": "Psych@999",
    "role":     "psychologist",
})
_check("POST /auth/register (psychologist) → 201", resp.status_code == 201)
print(f"  Response: {resp.json()}")

# -- Duplicate email (should fail) --
resp = post("/auth/register", {
    "name": "Duplicate", "email": student_email, "password": "abc123", "role": "student"
})
_check("POST /auth/register (duplicate email) → 409", resp.status_code == 409)
print(f"  Response: {resp.json()}")


# ─────────────────────────────────────────────────────────
# 2. Login
# ─────────────────────────────────────────────────────────

_print_section("2. Auth — Login")

resp = post("/auth/login", {"email": student_email, "password": "Test@1234"})
_check("POST /auth/login (student) → 200",    resp.status_code == 200)
_check("access_token present",                "access_token" in resp.json())
student_token = resp.json().get("access_token", "")
print(f"  Token (first 40 chars): {student_token[:40]}...")

resp = post("/auth/login", {"email": student_email, "password": "WrongPass"})
_check("POST /auth/login (wrong password) → 401", resp.status_code == 401)

resp = post("/auth/login", {"email": "nobody@x.com", "password": "abc123"})
_check("POST /auth/login (unknown email) → 401",  resp.status_code == 401)


# ─────────────────────────────────────────────────────────
# 3. Sessions
# ─────────────────────────────────────────────────────────

_print_section("3. Sessions")

resp = post("/session/start", {"user_id": student_user_id}, token=student_token)
_check("POST /session/start → 200",     resp.status_code == 200)
_check("session_id in response",        "session_id" in resp.json())
session_id = resp.json().get("session_id")
print(f"  session_id = {session_id}")

db_print(
    "Sessions after start",
    "SELECT session_id, user_id, start_time, status FROM Sessions WHERE session_id = ?",
    (session_id,),
)

resp = get(f"/session/{session_id}", token=student_token)
_check("GET /session/{id} → 200",  resp.status_code == 200)
_check("status == 'active'",       resp.json().get("status") == "active")
print(f"  Response: {resp.json()}")

resp = get("/session/9999", token=student_token)
_check("GET /session/9999 (not found) → 404", resp.status_code == 404)


# ─────────────────────────────────────────────────────────
# 4. Questionnaire
# ─────────────────────────────────────────────────────────

_print_section("4. Questionnaire — Stages & Questions")

resp = get("/questionnaire/stages")
_check("GET /questionnaire/stages → 200",  resp.status_code == 200)
stages = resp.json()
_check(f"5 stages returned (got {len(stages)})", len(stages) == 5)
for s in stages:
    print(f"  Stage {s['stage_number']}: {s['stage_name']}  threshold={s['threshold']}")

resp = get("/questionnaire/questions/1")
_check("GET /questionnaire/questions/1 → 200", resp.status_code == 200)
questions_s1 = resp.json()
_check(f"Questions returned (got {len(questions_s1)})", len(questions_s1) > 0)
for q in questions_s1:
    print(f"  Q{q['question_id']}: {q['question_text'][:60]}...")


_print_section("4b. Questionnaire — Submit Stages")

# Build answers for all 5 stages using seed question IDs
# Stage 1 → question_ids 1-4, Stage 2 → 5-7, Stage 3 → 8-10, Stage 4 → 11-13, Stage 5 → 14-16
stage_answers = {
    1: [
        {"question_id": 1, "response_choice": "Often",     "cal_score": 0.75},
        {"question_id": 2, "response_choice": "Sometimes", "cal_score": 0.50},
        {"question_id": 3, "response_choice": "Often",     "cal_score": 0.75},
        {"question_id": 4, "response_choice": "Sometimes", "cal_score": 0.50},
    ],
    2: [
        {"question_id": 5, "response_choice": "Often",     "cal_score": 0.75},
        {"question_id": 6, "response_choice": "Sometimes", "cal_score": 0.50},
        {"question_id": 7, "response_choice": "Often",     "cal_score": 0.75},
    ],
    3: [
        {"question_id": 8,  "response_choice": "Yes",       "cal_score": 0.80},
        {"question_id": 9,  "response_choice": "Yes",       "cal_score": 0.70},
        {"question_id": 10, "response_choice": "Sometimes", "cal_score": 0.50},
    ],
    4: [
        {"question_id": 11, "response_choice": "Often",     "cal_score": 0.75},
        {"question_id": 12, "response_choice": "Rarely",    "cal_score": 0.20},
        {"question_id": 13, "response_choice": "Sometimes", "cal_score": 0.50},
    ],
    5: [
        {"question_id": 14, "response_choice": "Never",  "cal_score": 0.00},
        {"question_id": 15, "response_choice": "Never",  "cal_score": 0.00},
        {"question_id": 16, "response_choice": "Rarely", "cal_score": 0.10},
    ],
}

for stage_num, answers in stage_answers.items():
    resp = post(
        "/questionnaire/submit",
        {"session_id": session_id, "stage_number": stage_num, "answers": answers},
        token=student_token,
    )
    _check(
        f"POST /questionnaire/submit stage {stage_num} → 200",
        resp.status_code == 200,
    )
    r = resp.json()
    print(
        f"  Stage {stage_num}: score={r['total_score']:.2f}  "
        f"passed={r['passed']}  next={r['next_stage']}  msg={r['message']}"
    )

db_print(
    "Q_Responses after all stages",
    """
    SELECT stage_number, COUNT(*) AS answers, SUM(cal_score) AS total_score
    FROM Q_Responses
    WHERE session_id = ?
    GROUP BY stage_number
    ORDER BY stage_number
    """,
    (session_id,),
)


# ─────────────────────────────────────────────────────────
# 5. Sensors — Pulse
# ─────────────────────────────────────────────────────────

_print_section("5. Sensors — Pulse")

for source, rate in [("muse", 72.5), ("bp_machine", 78.0)]:
    resp = post(
        "/sensors/pulse",
        {"session_id": session_id, "pulse_rate": rate, "source": source},
        token=student_token,
    )
    _check(f"POST /sensors/pulse ({source}) → 200", resp.status_code == 200)
    print(f"  Response: {resp.json()}")

resp = post(
    "/sensors/pulse",
    {"session_id": session_id, "pulse_rate": 70.0, "source": "invalid"},
    token=student_token,
)
_check("POST /sensors/pulse (bad source) → 422", resp.status_code == 422)


# ─────────────────────────────────────────────────────────
# 6. Sensors — Blood Pressure
# ─────────────────────────────────────────────────────────

_print_section("6. Sensors — Blood Pressure")

for sys, dia, pulse in [(125, 82, 78), (130, 85, None), (118, 76, 72)]:
    body = {"session_id": session_id, "systolic": sys, "diastolic": dia}
    if pulse:
        body["pulse_rate"] = pulse
    resp = post("/sensors/bp", body, token=student_token)
    _check(f"POST /sensors/bp ({sys}/{dia}) → 200", resp.status_code == 200)
    print(f"  Response: {resp.json()}")

db_print(
    "SensorData — BP + PPG rows",
    """
    SELECT data_type, bp_systolic, bp_diastolic, ppg_value, pulse_rate, recorded_at
    FROM SensorData
    WHERE session_id = ? AND data_type IN ('bp','ppg')
    ORDER BY recorded_at
    """,
    (session_id,),
)


# ─────────────────────────────────────────────────────────
# 7. Sensors — Facial Emotion (synthetic 1×1 pixel image)
# ─────────────────────────────────────────────────────────

_print_section("7. Sensors — Facial Emotion")

# Create a tiny valid JPEG (1×1 white pixel) encoded as base64
# DeepFace will detect no face → enforce_detection=False returns neutral
import io
try:
    import numpy as np
    import cv2

    # Generate a simple 100×100 gray frame (no face — tests graceful fallback)
    dummy_frame = np.ones((100, 100, 3), dtype=np.uint8) * 180
    _, buf = cv2.imencode(".jpg", dummy_frame)
    b64_image = base64.b64encode(buf.tobytes()).decode("utf-8")

    resp = post(
        "/sensors/emotion",
        {"session_id": session_id, "image_base64": b64_image},
        token=student_token,
    )
    # enforce_detection=False means it will succeed with a synthetic emotion result
    if resp.status_code == 200:
        _check("POST /sensors/emotion → 200", True)
        r = resp.json()
        print(f"  Dominant: {r['dominant_emotion']}")
        print(f"  Scores:   {r['scores']}")
    else:
        # 422 is also acceptable when no face is detected on a blank image
        _check(
            f"POST /sensors/emotion → 200 or 422 (got {resp.status_code})",
            resp.status_code in (200, 422),
        )
        print(f"  Response: {resp.json()}")
except ImportError:
    print("  ⚠️  numpy/cv2 not available in test env — skipping emotion test")

# -- Invalid base64 --
resp = post(
    "/sensors/emotion",
    {"session_id": session_id, "image_base64": "NOT_VALID_BASE64!!!"},
    token=student_token,
)
_check("POST /sensors/emotion (bad base64) → 422", resp.status_code == 422)


# ─────────────────────────────────────────────────────────
# 8. End Session → triggers risk engine
# ─────────────────────────────────────────────────────────

_print_section("8. Session End → Risk Scoring")

resp = post(
    "/session/end",
    {"session_id": session_id, "user_id": student_user_id},
    token=student_token,
)
_check("POST /session/end → 200",       resp.status_code == 200)
end_data = resp.json()
_check("risk_class in response",        "risk_class" in end_data)
_check("final_score in response",       "final_score" in end_data)
print(f"  risk_class  = {end_data.get('risk_class')}")
print(f"  final_score = {end_data.get('final_score')}")

# Cannot end the same session twice
resp = post(
    "/session/end",
    {"session_id": session_id, "user_id": student_user_id},
    token=student_token,
)
_check("POST /session/end (already done) → 409", resp.status_code == 409)

db_print(
    "MH_Results after session end",
    """
    SELECT result_id, session_id, user_id,
           emotional_score, functional_score, context_score,
           isolation_score, critical_score,
           eeg_avg, avg_pulse, avg_bp_systolic,
           dominant_emotion, final_score, risk_class
    FROM MH_Results
    WHERE session_id = ?
    """,
    (session_id,),
)


# ─────────────────────────────────────────────────────────
# 9. Results
# ─────────────────────────────────────────────────────────

_print_section("9. Results")

resp = get(f"/results/{session_id}", token=student_token)
_check("GET /results/{session_id} → 200",   resp.status_code == 200)
result = resp.json()
_check("risk_class matches end response",
       result.get("risk_class") == end_data.get("risk_class"))
print(f"  Full result:")
for k, v in result.items():
    print(f"    {k:<22} = {v}")

resp = get(f"/results/{session_id + 9999}", token=student_token)
_check("GET /results/9999 (not found) → 404", resp.status_code == 404)

resp = get(f"/results/user/{student_user_id}", token=student_token)
_check("GET /results/user/{user_id} → 200",    resp.status_code == 200)
history = resp.json()
_check("sessions list not empty",              len(history.get("sessions", [])) > 0)
print(f"\n  User history ({len(history['sessions'])} sessions):")
for s in history["sessions"]:
    print(f"    session_id={s['session_id']}  risk={s['risk_class']}  score={s['final_score']}")

resp = get(f"/results/user/9999", token=student_token)
_check("GET /results/user/9999 (not found) → 404", resp.status_code == 404)


# ─────────────────────────────────────────────────────────
# 10. Full DB snapshot
# ─────────────────────────────────────────────────────────

_print_section("10. Full Database Snapshot")

db_print("All Users",
    "SELECT user_id, name, email, role, created_at FROM Users ORDER BY user_id")

db_print("All Students",
    "SELECT s.student_id, s.user_id, u.name, s.cgpa_trend, s.attendance_drop "
    "FROM Students s JOIN Users u ON s.user_id=u.user_id")

db_print("All Teachers",
    "SELECT t.teacher_id, t.user_id, u.name, t.workload_hrs, t.class_count "
    "FROM Teachers t JOIN Users u ON t.user_id=u.user_id")

db_print("All Sessions",
    "SELECT session_id, user_id, start_time, end_time, status FROM Sessions ORDER BY session_id")

db_print("Q_Responses summary",
    "SELECT session_id, stage_number, COUNT(*) AS answers, SUM(cal_score) AS score "
    "FROM Q_Responses GROUP BY session_id, stage_number ORDER BY session_id, stage_number")

db_print("SensorData summary",
    "SELECT session_id, data_type, COUNT(*) AS rows FROM SensorData "
    "GROUP BY session_id, data_type ORDER BY session_id, data_type")

db_print("FacialEmotions",
    "SELECT emotion_id, session_id, dominant_emotion, happy, sad, neutral, captured_at "
    "FROM FacialEmotions ORDER BY emotion_id")

db_print("MH_Results",
    "SELECT result_id, session_id, user_id, final_score, risk_class, calculated_at "
    "FROM MH_Results ORDER BY result_id")


# ─────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────

_print_section(f"TEST SUMMARY  —  {PASSED} passed  |  {FAILED} failed")
if FAILED == 0:
    print("  🎉  All tests passed!")
else:
    print(f"  ⚠️   {FAILED} test(s) failed — review output above.")
    sys.exit(1)
