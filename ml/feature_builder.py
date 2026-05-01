"""ml/feature_builder.py — Assembles the 16-element feature vector for ML prediction"""

import logging
from typing import List

from preprocessing.eeg_preprocessor import preprocess_eeg
from preprocessing.bp_preprocessor import preprocess_bp
from preprocessing.emotion_preprocessor import preprocess_emotions
from scoring.questionnaire_scorer import get_stage_scores, score_student, score_teacher

logger = logging.getLogger(__name__)


def _get_student_academic(user_id: int, conn) -> dict:
    defaults = {"cgpa_trend": 0.0, "attendance_drop": 0.0, "failed_courses": 0, "total_courses": 1}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT cgpa_trend, attendance_drop FROM Students WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            defaults["cgpa_trend"] = float(row.cgpa_trend or 0.0)
            defaults["attendance_drop"] = float(row.attendance_drop or 0.0)
    except Exception as exc:
        logger.warning("Could not fetch student academic data for user %d: %s", user_id, exc)
    return defaults


def _get_teacher_workload(user_id: int, conn) -> dict:
    defaults = {"course_load": 0.0, "feedback_trend": 0.0}
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT workload_hrs, class_count FROM Teachers WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            defaults["course_load"] = float(row.workload_hrs or 0.0)
            defaults["feedback_trend"] = float(row.class_count or 0.0)
    except Exception as exc:
        logger.warning("Could not fetch teacher data for user %d: %s", user_id, exc)
    return defaults


def _get_hr_mean(session_id: int, conn) -> float:
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT AVG(CAST(pulse_rate AS FLOAT)) AS hr_avg FROM SensorData WHERE session_id = ? AND pulse_rate IS NOT NULL AND pulse_rate > 0",
            (session_id,),
        )
        row = cursor.fetchone()
        if row and row.hr_avg is not None:
            return round(float(row.hr_avg), 1)
    except Exception as exc:
        logger.warning("HR mean query failed for session %d: %s", session_id, exc)
    return 0.0


def _get_scores(session_id: int, user_id: int, role: str, conn):
    """Shared helper — returns (q_scores, role_feat_1, role_feat_2, role_feat_3)."""
    stage_scores = get_stage_scores(session_id, conn)
    if role == "student":
        q_data = _get_student_academic(user_id, conn)
        q_scores = score_student(stage_scores, **q_data)
        return q_scores, q_data["cgpa_trend"], q_data["attendance_drop"], q_scores["performance_score"]
    else:
        t_data = _get_teacher_workload(user_id, conn)
        q_scores = score_teacher(stage_scores, course_load=t_data["course_load"], feedback_trend=t_data["feedback_trend"])
        return q_scores, t_data["course_load"], t_data["feedback_trend"], 0.0


def build_features(session_id: int, user_id: int, role: str, conn) -> List[float]:
    """
    Assemble the 16-element feature vector for a session.

    Feature order:
      [0-4]  Questionnaire stage scores (emotional, functional, context, isolation, critical)
      [5-7]  Role-specific features (student: cgpa/attendance/perf | teacher: load/feedback/0)
      [8-10] EEG features (stress_index, alpha_power, theta_power)
      [11]   HR mean
      [12-13] BP (mean_systolic, mean_diastolic)
      [14]   Pulse average
      [15]   Emotion distress score
    """
    logger.info("Building feature vector: session=%d user=%d role=%s", session_id, user_id, role)

    q_scores, rf1, rf2, rf3 = _get_scores(session_id, user_id, role, conn)
    eeg = preprocess_eeg(session_id, conn)
    bp = preprocess_bp(session_id, conn)
    emo = preprocess_emotions(session_id, conn)
    hr_mean = _get_hr_mean(session_id, conn)

    features = [
        q_scores["emotional_score"],
        q_scores["functional_score"],
        q_scores["context_score"],
        q_scores["isolation_score"],
        q_scores["critical_score"],
        float(rf1),
        float(rf2),
        float(rf3),
        eeg["stress_index"],
        eeg["alpha_power"],
        eeg["theta_power"],
        float(hr_mean),
        float(bp["mean_systolic"] or 0.0),
        float(bp["mean_diastolic"] or 0.0),
        float(bp["mean_pulse"] or 0.0),
        float(emo["emotion_distress_score"]),
    ]

    logger.info("Feature vector for session %d: %s", session_id, features)
    return features


def get_all_component_scores(session_id: int, user_id: int, role: str, conn) -> dict:
    """Return all preprocessed component scores as a dict for saving to MH_Results."""
    q_scores, _, _, _ = _get_scores(session_id, user_id, role, conn)
    eeg = preprocess_eeg(session_id, conn)
    bp = preprocess_bp(session_id, conn)
    emo = preprocess_emotions(session_id, conn)
    hr_mean = _get_hr_mean(session_id, conn)

    return {
        "emotional_score":       q_scores["emotional_score"],
        "functional_score":      q_scores["functional_score"],
        "context_score":         q_scores["context_score"],
        "isolation_score":       q_scores["isolation_score"],
        "critical_score":        q_scores["critical_score"],
        "performance_score":     q_scores["performance_score"],
        "eeg_stress_index":      eeg["stress_index"],
        "eeg_alpha_power":       eeg["alpha_power"],
        "eeg_theta_power":       eeg["theta_power"],
        "hr_mean":               hr_mean,
        "bp_avg_systolic":       bp["mean_systolic"],
        "bp_avg_diastolic":      bp["mean_diastolic"],
        "pulse_avg":             bp["mean_pulse"],
        "dominant_emotion":      emo["dominant_emotion"],
        "emotion_distress_score": emo["emotion_distress_score"],
    }
