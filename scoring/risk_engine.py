# ============================================================
# scoring/risk_engine.py — Mental Health Risk Score Calculator
#
# Called by POST /session/end after the session is marked complete.
# Reads all collected data for the session and produces a single
# final_score + risk_class, which is saved to MH_Results.
# ============================================================

import logging
from typing import Optional, Dict, Any

import pyodbc

from utils.time_utils import now_utc

logger = logging.getLogger(__name__)

# ── Risk classification thresholds (inclusive upper bound) ─
RISK_BANDS = [
    (1.0, "Healthy"),
    (2.0, "Mild Stress"),
    (3.0, "Moderate Risk"),
    (3.5, "High Risk"),
]
RISK_CRITICAL = "Critical Risk"

# ── EEG normalization range (µV) — adjust to your hardware ─
EEG_MIN_UV = -50.0
EEG_MAX_UV = 50.0


def _classify_risk(score: float) -> str:
    """
    Map a numeric final_score to a risk category string.

    Thresholds (inclusive upper bounds):
      ≤ 1.0 → Healthy
      ≤ 2.0 → Mild Stress
      ≤ 3.0 → Moderate Risk
      ≤ 3.5 → High Risk
      > 3.5 → Critical Risk
    """
    for upper, label in RISK_BANDS:
        if score <= upper:
            return label
    return RISK_CRITICAL


def _normalize_eeg(eeg_avg: Optional[float]) -> float:
    """
    Normalize an average EEG value (µV) to the 0–1 range.

    Higher absolute EEG deviation is interpreted as higher arousal/stress.
    Returns 0.0 if eeg_avg is None (no EEG data collected).
    """
    if eeg_avg is None:
        return 0.0
    # Clamp to the expected range then normalize
    clamped = max(EEG_MIN_UV, min(EEG_MAX_UV, eeg_avg))
    # Map [-50, 50] → [0, 1]; higher absolute value → higher stress factor
    return abs(clamped) / EEG_MAX_UV


def _fetch_questionnaire_scores(
    session_id: int, cursor: pyodbc.Cursor
) -> Dict[str, float]:
    """
    Aggregate questionnaire cal_score by stage for the given session.

    Returns a dict with keys:
        emotional_score  (stage 1)
        functional_score (stage 2)
        context_score    (stage 3)
        isolation_score  (stage 4)
        critical_score   (stage 5)
    All values default to 0.0 if no responses exist for that stage.
    """
    cursor.execute(
        """
        SELECT stage_number, ISNULL(SUM(cal_score), 0) AS stage_total
        FROM Q_Responses
        WHERE session_id = ?
        GROUP BY stage_number
        """,
        (session_id,),
    )
    rows = cursor.fetchall()
    stage_map = {row.stage_number: float(row.stage_total) for row in rows}

    return {
        "emotional_score":  stage_map.get(1, 0.0),
        "functional_score": stage_map.get(2, 0.0),
        "context_score":    stage_map.get(3, 0.0),
        "isolation_score":  stage_map.get(4, 0.0),
        "critical_score":   stage_map.get(5, 0.0),
    }


def _fetch_sensor_averages(
    session_id: int, cursor: pyodbc.Cursor
) -> Dict[str, Optional[float]]:
    """
    Pull average EEG, pulse, and BP systolic for the session.

    EEG average  : AVG(eeg_value)  WHERE data_type = 'eeg'
    Pulse average: AVG across ppg_value (Muse) AND pulse_rate (BP machine)
    BP systolic  : AVG(bp_systolic) WHERE data_type = 'bp'
    """
    # EEG average
    cursor.execute(
        """
        SELECT AVG(eeg_value) AS eeg_avg
        FROM SensorData
        WHERE session_id = ? AND data_type = 'eeg'
        """,
        (session_id,),
    )
    eeg_row = cursor.fetchone()
    eeg_avg = float(eeg_row.eeg_avg) if eeg_row and eeg_row.eeg_avg is not None else None

    # Pulse average (combine both ppg_value and pulse_rate columns)
    cursor.execute(
        """
        SELECT AVG(combined_pulse) AS avg_pulse
        FROM (
            SELECT ppg_value AS combined_pulse
            FROM SensorData
            WHERE session_id = ? AND ppg_value IS NOT NULL

            UNION ALL

            SELECT CAST(pulse_rate AS FLOAT) AS combined_pulse
            FROM SensorData
            WHERE session_id = ? AND pulse_rate IS NOT NULL
        ) AS pulse_union
        """,
        (session_id, session_id),
    )
    pulse_row = cursor.fetchone()
    avg_pulse = float(pulse_row.avg_pulse) if pulse_row and pulse_row.avg_pulse is not None else None

    # BP systolic average
    cursor.execute(
        """
        SELECT AVG(CAST(bp_systolic AS FLOAT)) AS avg_sys
        FROM SensorData
        WHERE session_id = ? AND data_type = 'bp' AND bp_systolic IS NOT NULL
        """,
        (session_id,),
    )
    bp_row = cursor.fetchone()
    avg_bp_systolic = float(bp_row.avg_sys) if bp_row and bp_row.avg_sys is not None else None

    return {
        "eeg_avg": eeg_avg,
        "avg_pulse": avg_pulse,
        "avg_bp_systolic": avg_bp_systolic,
    }


def _fetch_dominant_emotion(
    session_id: int, cursor: pyodbc.Cursor
) -> Optional[str]:
    """
    Find the most frequently occurring dominant_emotion across all
    FacialEmotions rows for this session.

    Returns None if no facial emotion data was captured.
    """
    cursor.execute(
        """
        SELECT TOP 1 dominant_emotion, COUNT(*) AS freq
        FROM FacialEmotions
        WHERE session_id = ?
        GROUP BY dominant_emotion
        ORDER BY freq DESC
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    return row.dominant_emotion if row else None


def _fetch_academic_data(
    session_id: int, cursor: pyodbc.Cursor
) -> Dict[str, float]:
    """
    Retrieve student-specific academic factors (CGPA trend and
    attendance drop) by joining Sessions → Users → Students.

    Returns zero values if the user is a teacher or the student row
    does not exist yet.
    """
    cursor.execute(
        """
        SELECT st.cgpa_trend, st.attendance_drop
        FROM Sessions ses
        INNER JOIN Users u ON ses.user_id = u.user_id
        LEFT  JOIN Students st ON u.user_id = st.user_id
        WHERE ses.session_id = ? AND u.role = 'student'
        """,
        (session_id,),
    )
    row = cursor.fetchone()

    if not row:
        # Teacher or psychologist — academic factors contribute 0
        return {"cgpa_score": 0.0, "attendance_score": 0.0}

    cgpa_trend = float(row.cgpa_trend or 0.0)
    attendance_drop = float(row.attendance_drop or 0.0)

    # Negative CGPA trend indicates declining GPA → higher stress contribution
    cgpa_score = max(0.0, -cgpa_trend) * 10.0
    # Positive attendance_drop → missing more classes → higher stress
    attendance_score = max(0.0, attendance_drop) * 5.0

    return {"cgpa_score": cgpa_score, "attendance_score": attendance_score}


def calculate_score(session_id: int, conn: pyodbc.Connection) -> Dict[str, Any]:
    """
    Compute the mental health risk score for a completed session.

    Algorithm summary:
      - Gathers stage scores, sensor averages, emotion, and academic data.
      - Applies a weighted formula to produce final_score ∈ [0, ∞).
      - Classifies into one of 5 risk bands.
      - Inserts the result into MH_Results.
      - Returns a result dict.

    Args:
        session_id: The session to score.
        conn:       An open pyodbc connection (caller owns it).

    Returns:
        dict with all MH_Results fields.
    """
    logger.info("Calculating risk score for session_id=%d", session_id)
    cursor = conn.cursor()

    # ── STEP 1: Questionnaire scores by stage ─────────────
    q_scores = _fetch_questionnaire_scores(session_id, cursor)
    emotional_score  = q_scores["emotional_score"]
    functional_score = q_scores["functional_score"]
    context_score    = q_scores["context_score"]
    isolation_score  = q_scores["isolation_score"]
    critical_score   = q_scores["critical_score"]

    # ── STEP 2: Sensor averages ───────────────────────────
    sensor = _fetch_sensor_averages(session_id, cursor)
    eeg_avg       = sensor["eeg_avg"]
    avg_pulse     = sensor["avg_pulse"]
    avg_bp_systolic = sensor["avg_bp_systolic"]

    # ── STEP 3: Dominant emotion ──────────────────────────
    dominant_emotion = _fetch_dominant_emotion(session_id, cursor)

    # ── STEP 4: Academic factors ──────────────────────────
    academic = _fetch_academic_data(session_id, cursor)
    cgpa_score       = academic["cgpa_score"]
    attendance_score = academic["attendance_score"]

    # ── STEP 5: EEG factor (normalized 0–1) ──────────────
    eeg_factor = _normalize_eeg(eeg_avg)

    # ── STEP 5: Weighted scoring formula ─────────────────
    #
    #  Weight breakdown:
    #    30% emotional (PHQ-style anxiety/depression)
    #    20% functional (daily functioning impairment)
    #    10% context (life stressors / environment)
    #    15% isolation (social withdrawal)
    #     5% critical (suicidal ideation / crisis flags)
    #    10% CGPA trend (academic performance decline)  [students only]
    #     5% attendance drop                            [students only]
    #     5% EEG biometric factor
    #
    final_score = (
        0.30 * emotional_score
        + 0.20 * functional_score
        + 0.10 * context_score
        + 0.15 * isolation_score
        + 0.05 * critical_score
        + 0.10 * cgpa_score
        + 0.05 * attendance_score
        + 0.05 * eeg_factor
    )
    final_score = round(final_score, 4)

    # ── STEP 6: Classify risk ─────────────────────────────
    risk_class = _classify_risk(final_score)

    # ── STEP 7: Persist to MH_Results ────────────────────
    calculated_at = now_utc()

    # First look up user_id from Sessions
    cursor.execute(
        "SELECT user_id FROM Sessions WHERE session_id = ?", (session_id,)
    )
    session_row = cursor.fetchone()
    if not session_row:
        raise ValueError(f"Session {session_id} not found when saving MH_Results.")
    user_id = session_row.user_id

    cursor.execute(
        """
        INSERT INTO MH_Results (
            session_id, user_id,
            emotional_score, functional_score, context_score,
            isolation_score, critical_score,
            eeg_avg, avg_pulse, avg_bp_systolic,
            dominant_emotion,
            final_score, risk_class, calculated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, user_id,
            emotional_score, functional_score, context_score,
            isolation_score, critical_score,
            eeg_avg, avg_pulse, avg_bp_systolic,
            dominant_emotion,
            final_score, risk_class, calculated_at,
        ),
    )
    conn.commit()

    logger.info(
        "Risk score saved: session=%d user=%d score=%.4f class=%s",
        session_id, user_id, final_score, risk_class,
    )

    return {
        "session_id":       session_id,
        "user_id":          user_id,
        "emotional_score":  emotional_score,
        "functional_score": functional_score,
        "context_score":    context_score,
        "isolation_score":  isolation_score,
        "critical_score":   critical_score,
        "eeg_avg":          eeg_avg,
        "avg_pulse":        avg_pulse,
        "avg_bp_systolic":  avg_bp_systolic,
        "dominant_emotion": dominant_emotion,
        "final_score":      final_score,
        "risk_class":       risk_class,
        "calculated_at":    calculated_at,
    }
