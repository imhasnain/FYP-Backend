"""processing/scorer.py — Mental health scoring pipeline.

Implements the two-track scoring system:
  1. Questionnaire score (q_score)  — weighted stage scores + context data
  2. Physiological score (physio)   — EEG + face + HR + BP
  3. Final fusion: 0.70 * q_score + 0.30 * physio
  4. Classification into 4 recommendation levels
  5. Safety override for Stage 5 critical answers
"""

import logging

logger = logging.getLogger(__name__)


# ── Stage score normalization ──────────────────────────────────

def normalize_stage(raw_sum: float, n_questions: int) -> float:
    """Normalize a raw stage score to the 0-4 scale."""
    if n_questions <= 0:
        return 0.0
    return min(4.0, max(0.0, (raw_sum / (n_questions * 4)) * 4))


def get_stage_scores(session_id: int, conn) -> dict:
    """Pull questionnaire responses and compute normalized scores per stage."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT stage_number, SUM(cal_score) AS raw_sum, COUNT(*) AS n "
        "FROM Q_Responses WHERE session_id = ? GROUP BY stage_number",
        (session_id,)
    )
    scores = {}
    for row in cursor.fetchall():
        stage = int(row.stage_number)
        scores[stage] = normalize_stage(float(row.raw_sum or 0), int(row.n))
    return scores


# ── Questionnaire scoring formulas ─────────────────────────────

def get_feedback_weights(conn) -> dict:
    """Read average psychologist feedback ratings per stage and convert to weights.

    Psychologists rate 1-5 stars. Higher rating = this stage is more important.
    Returns a dict {stage_number: weight} normalized so they sum to 1.0.
    Falls back to default weights if no feedback exists yet.
    """
    defaults = {1: 0.30, 2: 0.20, 3: 0.10, 4: 0.15, 5: 0.05}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT q.stage_id, AVG(CAST(f.usefulness_score AS FLOAT)) as avg_rating "
            "FROM QuestionFeedback f "
            "JOIN Q_Questions q ON f.question_id = q.question_id "
            "GROUP BY q.stage_id"
        )
        rows = cursor.fetchall()
        if not rows:
            return defaults

        raw = {}
        for row in rows:
            raw[int(row.stage_id)] = float(row.avg_rating)

        # Fill missing stages with default rating of 3
        for stage in range(1, 6):
            if stage not in raw:
                raw[stage] = 3.0

        total = sum(raw.values())
        return {s: round(v / total, 4) for s, v in raw.items()}
    except Exception as exc:
        logger.warning("Could not load feedback weights, using defaults: %s", exc)
        return defaults


def calc_student_score(stages: dict, cgpa_trend: float = 0.0,
                       attendance_drop: float = 0.0,
                       failed_courses: int = 0, total_courses: int = 1,
                       weights: dict = None) -> float:
    """Compute weighted questionnaire score for a student (0-4 scale)."""
    w = weights or {1: 0.30, 2: 0.20, 3: 0.10, 4: 0.15, 5: 0.05}
    s1 = stages.get(1, 0.0)
    s2 = stages.get(2, 0.0)
    s3 = stages.get(3, 0.0)
    s4 = stages.get(4, 0.0)
    s5 = stages.get(5, 0.0)

    cgpa_score = min(4.0, max(0.0, -cgpa_trend) * 2)
    attend_score = min(4.0, max(0.0, attendance_drop * 0.4))
    fail_ratio = failed_courses / max(total_courses, 1)
    perf_score = min(4.0, fail_ratio * 4)

    stage_total = w[1]*s1 + w[2]*s2 + w[3]*s3 + w[4]*s4 + w[5]*s5
    context_total = 0.10*cgpa_score + 0.05*attend_score + 0.05*perf_score

    return round(min(4.0, max(0.0, stage_total + context_total)), 4)


def calc_teacher_score(stages: dict, course_load: float = 0.0,
                       feedback_trend: float = 0.0) -> float:
    """Compute weighted questionnaire score for a teacher (0-4 scale)."""
    s1 = stages.get(1, 0.0)
    s2 = stages.get(2, 0.0)
    s3 = stages.get(3, 0.0)
    s4 = stages.get(4, 0.0)
    s5 = stages.get(5, 0.0)

    load_score = min(4.0, (course_load / 5.0) * 4)
    feedback_score = min(4.0, max(0.0, -feedback_trend) * 2)

    return round(min(4.0, max(0.0,
        0.30 * s1 + 0.20 * s2 + 0.15 * s3 + 0.15 * s4 +
        0.10 * load_score + 0.05 * feedback_score + 0.05 * s5
    )), 4)


# ── Physiological scoring ──────────────────────────────────────

def calc_physio_score(eeg_score: float = 0.0, face_score: float = 0.0,
                     hr_score: float = 0.0, bp_score: float = 0.0) -> float:
    """Combine physiological signals into a single score (0-4 scale).

    Weights: EEG 40%, Face 25%, HR 20%, BP 15%.
    Missing signals default to 0 — formula still runs.
    """
    return round(min(4.0, max(0.0,
        0.40 * eeg_score + 0.25 * face_score +
        0.20 * hr_score + 0.15 * bp_score
    )), 4)


# ── Final fusion and classification ────────────────────────────

def fuse_scores(q_score: float, physio_score: float) -> float:
    """Fuse questionnaire and physiological scores. 70/30 split."""
    return round(0.70 * q_score + 0.30 * physio_score, 4)


def classify(final_score: float) -> str:
    """Map final score to a recommendation label."""
    if final_score <= 1.0:
        return "Normal"
    elif final_score <= 2.0:
        return "Calm Down"
    elif final_score <= 3.0:
        return "See Psychologist"
    else:
        return "Emergency"


def safety_override(session_id: int, conn,
                    recommendation: str, final_score: float) -> tuple:
    """If any Stage 5 answer was 3 or 4 → force Emergency.

    Returns (recommendation, final_score) — possibly overridden.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM Q_Responses "
            "WHERE session_id = ? AND stage_number = 5 AND cal_score >= 3",
            (session_id,)
        )
        row = cursor.fetchone()
        if row and row.cnt > 0:
            logger.warning("SAFETY OVERRIDE: session %d has Stage 5 answer >= 3.", session_id)
            return "Emergency", 4.0
    except Exception as exc:
        logger.error("Safety override check failed: %s", exc)
    return recommendation, final_score
