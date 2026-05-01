"""scoring/questionnaire_scorer.py — Questionnaire score calculator"""

import logging
from typing import Dict

from preprocessing.emotion_preprocessor import EMOTION_DISTRESS_MAP

logger = logging.getLogger(__name__)


def _normalize_stage(raw_sum: float, num_questions: int) -> float:
    """Normalize raw stage score to [0, 4] scale."""
    if num_questions <= 0:
        return 0.0
    return min(4.0, max(0.0, (raw_sum / (num_questions * 4.0)) * 4.0))


def get_stage_scores(session_id: int, conn) -> Dict[int, Dict[str, float]]:
    """
    Fetch questionnaire responses and compute normalized scores per stage.
    Applies a dynamic emotion multiplier — questions answered while the user
    shows distress (angry/sad/fear) are weighted higher.
    """
    cursor = conn.cursor()

    cursor.execute(
        "SELECT stage_number, cal_score, timestamp FROM Q_Responses WHERE session_id = ? AND stage_number IS NOT NULL",
        (session_id,),
    )
    responses = cursor.fetchall()

    cursor.execute(
        "SELECT dominant_emotion, captured_at FROM FacialEmotions WHERE session_id = ? AND captured_at IS NOT NULL",
        (session_id,),
    )
    emotions = cursor.fetchall()

    stage_totals = {}
    stage_counts = {}

    for row in responses:
        stage = int(row.stage_number)
        base_score = float(row.cal_score or 0.0)
        multiplier = 1.0

        if emotions and row.timestamp:
            closest = min(emotions, key=lambda e: abs((e.captured_at - row.timestamp).total_seconds()))
            if abs((closest.captured_at - row.timestamp).total_seconds()) <= 60:
                distress = EMOTION_DISTRESS_MAP.get((closest.dominant_emotion or "undetected").lower(), 0.3)
                # distress 0.0 (happy) → 0.7x, 0.3 (neutral/undetected) → 1.0x, 0.8 (angry) → 1.5x
                multiplier = 1.0 + (distress - 0.3)

        adjusted_score = min(4.0, base_score * multiplier)
        stage_totals[stage] = stage_totals.get(stage, 0.0) + adjusted_score
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    return {
        stage: {
            "raw_sum": round(stage_totals[stage], 4),
            "num_questions": stage_counts[stage],
            "normalized": round(_normalize_stage(stage_totals[stage], stage_counts[stage]), 4),
        }
        for stage in stage_totals
    }


def score_student(
    stage_scores: Dict[int, Dict[str, float]],
    cgpa_trend: float = 0.0,
    attendance_drop: float = 0.0,
    failed_courses: int = 0,
    total_courses: int = 1,
) -> Dict[str, float]:
    """Compute weighted composite score for a student."""
    emotional  = stage_scores.get(1, {}).get("normalized", 0.0)
    functional = stage_scores.get(2, {}).get("normalized", 0.0)
    context    = stage_scores.get(3, {}).get("normalized", 0.0)
    isolation  = stage_scores.get(4, {}).get("normalized", 0.0)
    critical   = stage_scores.get(5, {}).get("normalized", 0.0)

    cgpa_score = min(4.0, max(0.0, -cgpa_trend) * 2.0)
    att_score  = min(4.0, max(0.0, attendance_drop) * 0.5)
    perf_score = min(4.0, (failed_courses / total_courses) * 4.0) if total_courses > 0 else 0.0

    final = round(min(4.0, max(0.0,
        0.30 * emotional + 0.20 * functional + 0.10 * context +
        0.15 * isolation + 0.10 * cgpa_score + 0.05 * att_score +
        0.05 * perf_score + 0.05 * critical
    )), 4)

    return {
        "emotional_score":   round(emotional, 4),
        "functional_score":  round(functional, 4),
        "context_score":     round(context, 4),
        "isolation_score":   round(isolation, 4),
        "critical_score":    round(critical, 4),
        "cgpa_trend_score":  round(cgpa_score, 4),
        "attendance_score":  round(att_score, 4),
        "performance_score": round(perf_score, 4),
        "questionnaire_final": final,
    }


def score_teacher(
    stage_scores: Dict[int, Dict[str, float]],
    course_load: float = 0.0,
    feedback_trend: float = 0.0,
) -> Dict[str, float]:
    """Compute weighted composite score for a teacher."""
    emotional  = stage_scores.get(1, {}).get("normalized", 0.0)
    functional = stage_scores.get(2, {}).get("normalized", 0.0)
    context    = stage_scores.get(3, {}).get("normalized", 0.0)
    isolation  = stage_scores.get(4, {}).get("normalized", 0.0)
    critical   = stage_scores.get(5, {}).get("normalized", 0.0)

    load_score = min(4.0, (course_load / 5.0) * 4.0)
    fb_score   = min(4.0, max(0.0, -feedback_trend) * 2.0)

    final = round(min(4.0, max(0.0,
        0.30 * emotional + 0.20 * functional + 0.15 * context +
        0.15 * isolation + 0.10 * load_score + 0.05 * fb_score + 0.05 * critical
    )), 4)

    return {
        "emotional_score":     round(emotional, 4),
        "functional_score":    round(functional, 4),
        "context_score":       round(context, 4),
        "isolation_score":     round(isolation, 4),
        "critical_score":      round(critical, 4),
        "teaching_load_score": round(load_score, 4),
        "feedback_score":      round(fb_score, 4),
        "performance_score":   0.0,
        "questionnaire_final": final,
    }


def score_to_recommendation(score: float) -> str:
    """Map a final composite score (0–4) to a recommendation label."""
    if score < 1.0:
        return "Normal"
    elif score < 2.0:
        return "Calm Down"
    elif score < 3.5:
        return "See Psychologist"
    else:
        return "Emergency"
