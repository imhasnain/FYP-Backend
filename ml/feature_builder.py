# ============================================================
# ml/feature_builder.py — Assemble the 16-element feature vector
#
# Pulls data from all preprocessing modules and the database
# to build the complete input vector for the ML prediction model.
# ============================================================

import logging
from typing import List

from preprocessing.eeg_preprocessor import preprocess_eeg
from preprocessing.bp_preprocessor import preprocess_bp
from preprocessing.emotion_preprocessor import preprocess_emotions
from scoring.questionnaire_scorer import get_stage_scores, score_student, score_teacher

logger = logging.getLogger(__name__)


def build_features(
    session_id: int,
    user_id: int,
    role: str,
    conn,
) -> List[float]:
    """
    Assemble the complete 16-element feature vector for a session.

    Pipeline:
      1. Run questionnaire_scorer → get normalized stage scores.
      2. Run eeg_preprocessor     → get EEG band powers + stress index.
      3. Run bp_preprocessor      → get BP / pulse averages.
      4. Run emotion_preprocessor → get emotion distress score.
      5. Pull academic/workload data from Students or Teachers table.
      6. Assemble into a 16-float list in the correct order.

    Missing data is gracefully handled with 0.0 defaults — this function
    never raises on missing sensor data.

    Args:
        session_id: The session to build features for.
        user_id:    The user who owns the session.
        role:       'student' or 'teacher'.
        conn:       An open pyodbc connection.

    Returns:
        List of 16 floats ready to pass to predictor.predict().

    Feature order (both roles):
      [0]  emotional_score       (Stage 1, normalized 0–4)
      [1]  functional_score      (Stage 2)
      [2]  context_score         (Stage 3)
      [3]  isolation_score       (Stage 4)
      [4]  critical_score        (Stage 5, 0 if not reached)
      [5]  role_specific_1       (student: cgpa_trend / teacher: course_load)
      [6]  role_specific_2       (student: attendance_drop / teacher: feedback_trend)
      [7]  role_specific_3       (student: performance_decline / teacher: 0.0)
      [8]  eeg_stress_index
      [9]  eeg_alpha_power
      [10] eeg_theta_power
      [11] hr_mean               (mean heart rate from pulse data)
      [12] bp_mean_systolic
      [13] bp_mean_diastolic
      [14] pulse_avg
      [15] emotion_distress_score
    """
    logger.info(
        "Building feature vector: session=%d user=%d role=%s",
        session_id, user_id, role,
    )

    # ── 1. Questionnaire scores ──────────────────────────────
    stage_scores = get_stage_scores(session_id, conn)

    if role == "student":
        q_data = _get_student_academic(user_id, conn)
        q_scores = score_student(
            stage_scores,
            cgpa_trend=q_data["cgpa_trend"],
            attendance_drop=q_data["attendance_drop"],
            failed_courses=q_data["failed_courses"],
            total_courses=q_data["total_courses"],
        )
        role_feat_1 = q_data["cgpa_trend"]
        role_feat_2 = q_data["attendance_drop"]
        role_feat_3 = q_scores["performance_score"]
    else:
        t_data = _get_teacher_workload(user_id, conn)
        q_scores = score_teacher(
            stage_scores,
            course_load=t_data["course_load"],
            feedback_trend=t_data["feedback_trend"],
        )
        role_feat_1 = t_data["course_load"]
        role_feat_2 = t_data["feedback_trend"]
        role_feat_3 = 0.0

    # ── 2. EEG features ─────────────────────────────────────
    eeg = preprocess_eeg(session_id, conn)

    # ── 3. BP / Pulse features ───────────────────────────────
    bp = preprocess_bp(session_id, conn)

    # ── 4. Emotion features ──────────────────────────────────
    emo = preprocess_emotions(session_id, conn)

    # ── 5. Heart rate mean (from pulse data or PPG) ──────────
    hr_mean = _get_hr_mean(session_id, conn)

    # ── 6. Assemble 16-element vector ────────────────────────
    features = [
        q_scores["emotional_score"],           # [0]
        q_scores["functional_score"],          # [1]
        q_scores["context_score"],             # [2]
        q_scores["isolation_score"],           # [3]
        q_scores["critical_score"],            # [4]
        float(role_feat_1),                    # [5]
        float(role_feat_2),                    # [6]
        float(role_feat_3),                    # [7]
        eeg["stress_index"],                   # [8]
        eeg["alpha_power"],                    # [9]
        eeg["theta_power"],                    # [10]
        float(hr_mean or 0.0),                 # [11]
        float(bp["mean_systolic"] or 0.0),     # [12]
        float(bp["mean_diastolic"] or 0.0),    # [13]
        float(bp["mean_pulse"] or 0.0),        # [14]
        float(emo["emotion_distress_score"]),   # [15]
    ]

    logger.info("Feature vector for session %d: %s", session_id, features)
    return features


def get_all_component_scores(
    session_id: int, user_id: int, role: str, conn
) -> dict:
    """
    Return all preprocessed component scores as a dict for saving
    to MH_Results. Combines questionnaire, EEG, BP, and emotion data.

    Args:
        session_id: The session to process.
        user_id:    The user who owns the session.
        role:       'student' or 'teacher'.
        conn:       An open pyodbc connection.

    Returns:
        Dict with all component scores matching MH_Results columns.
    """
    stage_scores = get_stage_scores(session_id, conn)
    eeg = preprocess_eeg(session_id, conn)
    bp = preprocess_bp(session_id, conn)
    emo = preprocess_emotions(session_id, conn)
    hr_mean = _get_hr_mean(session_id, conn)

    if role == "student":
        q_data = _get_student_academic(user_id, conn)
        q_scores = score_student(
            stage_scores,
            cgpa_trend=q_data["cgpa_trend"],
            attendance_drop=q_data["attendance_drop"],
            failed_courses=q_data["failed_courses"],
            total_courses=q_data["total_courses"],
        )
    else:
        t_data = _get_teacher_workload(user_id, conn)
        q_scores = score_teacher(
            stage_scores,
            course_load=t_data["course_load"],
            feedback_trend=t_data["feedback_trend"],
        )

    return {
        "emotional_score": q_scores["emotional_score"],
        "functional_score": q_scores["functional_score"],
        "context_score": q_scores["context_score"],
        "isolation_score": q_scores["isolation_score"],
        "critical_score": q_scores["critical_score"],
        "performance_score": q_scores["performance_score"],
        "eeg_stress_index": eeg["stress_index"],
        "eeg_alpha_power": eeg["alpha_power"],
        "eeg_theta_power": eeg["theta_power"],
        "hr_mean": hr_mean or 0.0,
        "bp_avg_systolic": bp["mean_systolic"],
        "bp_avg_diastolic": bp["mean_diastolic"],
        "pulse_avg": bp["mean_pulse"],
        "dominant_emotion": emo["dominant_emotion"],
        "emotion_distress_score": emo["emotion_distress_score"],
    }


# ── Private helpers ──────────────────────────────────────────

def _get_student_academic(user_id: int, conn) -> dict:
    """
    Fetch student academic data from Students and Enrollments tables.

    Args:
        user_id: The student's user_id.
        conn:    An open pyodbc connection.

    Returns:
        Dict with cgpa_trend, attendance_drop, failed_courses, total_courses.
    """
    defaults = {
        "cgpa_trend": 0.0,
        "attendance_drop": 0.0,
        "failed_courses": 0,
        "total_courses": 1,
    }
    try:
        cursor = conn.cursor()
        # Students actual columns: user_id, cgpa_trend, attendance_drop
        cursor.execute(
            """
            SELECT cgpa_trend, attendance_drop
            FROM Students
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            defaults["cgpa_trend"] = float(row.cgpa_trend or 0.0)
            defaults["attendance_drop"] = float(row.attendance_drop or 0.0)
        # Enrollments table does not exist in this DB -- skip failed-course count

    except Exception as exc:
        logger.warning("Could not fetch student academic data for user %d: %s", user_id, exc)

    return defaults


def _get_teacher_workload(user_id: int, conn) -> dict:
    """
    Fetch teacher workload data from the Teachers table.

    Args:
        user_id: The teacher's user_id.
        conn:    An open pyodbc connection.

    Returns:
        Dict with course_load, feedback_trend.
    """
    defaults = {"course_load": 0.0, "feedback_trend": 0.0}
    try:
        cursor = conn.cursor()
        # Teachers actual columns: user_id, workload_hrs, class_count
        cursor.execute(
            """
            SELECT workload_hrs, class_count
            FROM Teachers
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            # Map workload_hrs -> course_load, class_count -> feedback_trend proxy
            defaults["course_load"] = float(row.workload_hrs or 0.0)
            defaults["feedback_trend"] = float(row.class_count or 0.0)
    except Exception as exc:
        logger.warning("Could not fetch teacher data for user %d: %s", user_id, exc)

    return defaults


def _get_hr_mean(session_id: int, conn) -> float:
    """
    Compute mean heart rate from PPG and pulse sensor readings.

    Args:
        session_id: The session to query.
        conn:       An open pyodbc connection.

    Returns:
        Mean heart rate as float, or 0.0 if no data.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT AVG(CAST(pulse_rate AS FLOAT)) AS hr_avg
            FROM SensorData
            WHERE session_id = ?
              AND pulse_rate IS NOT NULL
              AND pulse_rate > 0
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if row and row.hr_avg is not None:
            return round(float(row.hr_avg), 1)
    except Exception as exc:
        logger.warning("HR mean query failed for session %d: %s", session_id, exc)
    return 0.0
