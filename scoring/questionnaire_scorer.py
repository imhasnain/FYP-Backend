# ============================================================
# scoring/questionnaire_scorer.py — Questionnaire score calculator
#
# Normalizes raw stage scores and applies role-specific weighted
# formulas to produce a composite questionnaire score (0–4 scale).
# ============================================================

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _normalize_stage(raw_sum: float, num_questions: int) -> float:
    """
    Normalize a raw stage score to the 0–4 scale.

    Formula: (raw_sum / (num_questions * 4)) * 4
    Each question has a max score of 4 (Always), so max raw = num_questions * 4.

    Args:
        raw_sum:       Sum of cal_score values for the stage.
        num_questions: Number of questions answered in the stage.

    Returns:
        Normalized score in range [0, 4]. Returns 0.0 if num_questions is 0.
    """
    if num_questions <= 0:
        return 0.0
    max_possible = num_questions * 4.0
    normalized = (raw_sum / max_possible) * 4.0
    return min(4.0, max(0.0, normalized))


def get_stage_scores(session_id: int, conn) -> Dict[int, Dict[str, float]]:
    """
    Fetch all questionnaire responses for a session and compute
    normalized scores per stage.

    Args:
        session_id: The session to query.
        conn:       An open pyodbc connection.

    Returns:
        Dict mapping stage_number → { 'raw_sum', 'num_questions', 'normalized' }.
        Missing stages will not have entries.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT stage_number,
               SUM(cal_score)  AS raw_sum,
               COUNT(*)        AS num_q
        FROM Q_Responses
        WHERE session_id = ?
          AND stage_number IS NOT NULL
        GROUP BY stage_number
        ORDER BY stage_number
        """,
        (session_id,),
    )
    rows = cursor.fetchall()

    scores = {}
    for row in rows:
        stage = int(row.stage_number)
        raw = float(row.raw_sum or 0.0)
        num_q = int(row.num_q or 0)
        norm = _normalize_stage(raw, num_q)
        scores[stage] = {
            "raw_sum": raw,
            "num_questions": num_q,
            "normalized": round(norm, 4),
        }

    return scores


def score_student(
    stage_scores: Dict[int, Dict[str, float]],
    cgpa_trend: float = 0.0,
    attendance_drop: float = 0.0,
    failed_courses: int = 0,
    total_courses: int = 1,
) -> Dict[str, float]:
    """
    Compute the weighted questionnaire composite score for a student.

    Student formula:
      0.30 * emotional  + 0.20 * functional + 0.10 * context +
      0.15 * isolation  + 0.10 * cgpa_trend_score +
      0.05 * attendance_score + 0.05 * performance_score +
      0.05 * critical

    Args:
        stage_scores:    Dict from get_stage_scores().
        cgpa_trend:      From Students table (-ve = declining).
        attendance_drop: From Students table (+ve = dropping).
        failed_courses:  Number of failed courses from Enrollments.
        total_courses:   Total enrolled courses.

    Returns:
        Dict with all component scores and the final weighted score.
    """
    emotional = stage_scores.get(1, {}).get("normalized", 0.0)
    functional = stage_scores.get(2, {}).get("normalized", 0.0)
    context = stage_scores.get(3, {}).get("normalized", 0.0)
    isolation = stage_scores.get(4, {}).get("normalized", 0.0)
    critical = stage_scores.get(5, {}).get("normalized", 0.0)

    # Academic indicators → 0–4 scale
    cgpa_score = min(4.0, max(0.0, -cgpa_trend) * 2.0)
    att_score = min(4.0, max(0.0, attendance_drop) * 0.5)

    # Performance decline
    if total_courses > 0:
        perf_score = min(4.0, (failed_courses / total_courses) * 4.0)
    else:
        perf_score = 0.0

    final = (
        0.30 * emotional
        + 0.20 * functional
        + 0.10 * context
        + 0.15 * isolation
        + 0.10 * cgpa_score
        + 0.05 * att_score
        + 0.05 * perf_score
        + 0.05 * critical
    )
    final = round(min(4.0, max(0.0, final)), 4)

    return {
        "emotional_score": round(emotional, 4),
        "functional_score": round(functional, 4),
        "context_score": round(context, 4),
        "isolation_score": round(isolation, 4),
        "critical_score": round(critical, 4),
        "cgpa_trend_score": round(cgpa_score, 4),
        "attendance_score": round(att_score, 4),
        "performance_score": round(perf_score, 4),
        "questionnaire_final": final,
    }


def score_teacher(
    stage_scores: Dict[int, Dict[str, float]],
    course_load: float = 0.0,
    feedback_trend: float = 0.0,
) -> Dict[str, float]:
    """
    Compute the weighted questionnaire composite score for a teacher.

    Teacher formula:
      0.30 * emotional  + 0.20 * functional + 0.15 * context +
      0.15 * isolation  + 0.10 * teaching_load_score +
      0.05 * feedback_score + 0.05 * critical

    Args:
        stage_scores:   Dict from get_stage_scores().
        course_load:    Number of courses taught (from Teachers table).
        feedback_trend: From Teachers table (-ve = declining feedback).

    Returns:
        Dict with all component scores and the final weighted score.
    """
    emotional = stage_scores.get(1, {}).get("normalized", 0.0)
    functional = stage_scores.get(2, {}).get("normalized", 0.0)
    context = stage_scores.get(3, {}).get("normalized", 0.0)
    isolation = stage_scores.get(4, {}).get("normalized", 0.0)
    critical = stage_scores.get(5, {}).get("normalized", 0.0)

    # Teaching load → 0–4 scale (5 courses = max stress)
    load_score = min(4.0, (course_load / 5.0) * 4.0)
    # Feedback trend → 0–4 scale (negative trend = stress)
    fb_score = min(4.0, max(0.0, -feedback_trend) * 2.0)

    final = (
        0.30 * emotional
        + 0.20 * functional
        + 0.15 * context
        + 0.15 * isolation
        + 0.10 * load_score
        + 0.05 * fb_score
        + 0.05 * critical
    )
    final = round(min(4.0, max(0.0, final)), 4)

    return {
        "emotional_score": round(emotional, 4),
        "functional_score": round(functional, 4),
        "context_score": round(context, 4),
        "isolation_score": round(isolation, 4),
        "critical_score": round(critical, 4),
        "teaching_load_score": round(load_score, 4),
        "feedback_score": round(fb_score, 4),
        "performance_score": 0.0,  # placeholder for vector alignment
        "questionnaire_final": final,
    }


def score_to_recommendation(score: float) -> str:
    """
    Rule-based fallback: map a final composite score to a recommendation.

    Used when the ML model is not loaded.

    Args:
        score: Final score in range [0, 4].

    Returns:
        One of: 'Normal', 'Calm Down', 'See Psychologist', 'Emergency'.
    """
    if score < 1.0:
        return "Normal"
    elif score < 2.0:
        return "Calm Down"
    elif score < 3.5:
        return "See Psychologist"
    else:
        return "Emergency"
