"""routers/results.py — Mental health result endpoints."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.result_models import SessionResult, ScoreBreakdown, UserHistory, UserHistoryItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/user/{user_id}", response_model=UserHistory)
def get_user_history(user_id: int):
    """Return all completed session results for a user."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found.")

        cursor.execute("""
            SELECT s.session_id, s.start_time, s.end_time,
                   r.risk_class AS recommendation, r.final_score, r.calculated_at
            FROM Sessions s LEFT JOIN MH_Results r ON s.session_id = r.session_id
            WHERE s.user_id = ? ORDER BY s.start_time DESC""", (user_id,))

        items = [
            UserHistoryItem(session_id=row.session_id, start_time=row.start_time, end_time=row.end_time,
                            recommendation=row.recommendation, final_score=row.final_score,
                            calculated_at=row.calculated_at)
            for row in cursor.fetchall()
        ]
        return UserHistory(user_id=user_id, sessions=items)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_user_history error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve history.")
    finally:
        conn.close()


@router.get("/{session_id}", response_model=SessionResult)
def get_session_result(session_id: int):
    """Return the full mental health result with score breakdown."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.session_id, s.user_id, u.role AS user_role,
                   r.emotional_score, r.functional_score, r.context_score,
                   r.isolation_score, r.critical_score,
                   r.eeg_avg, r.avg_pulse, r.avg_bp_systolic,
                   r.dominant_emotion, r.final_score, r.risk_class,
                   r.calculated_at, s.start_time, s.end_time
            FROM MH_Results r
            INNER JOIN Sessions s ON r.session_id = s.session_id
            INNER JOIN Users u ON s.user_id = u.user_id
            WHERE r.session_id = ?""", (session_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"No result for session {session_id}.")

        duration = None
        if row.start_time and row.end_time:
            duration = round((row.end_time - row.start_time).total_seconds() / 60.0, 2)

        # Estimate q_score and physio from final_score (final = 0.70*q + 0.30*p)
        # We store stage scores directly so we can reconstruct
        q_estimate = round((row.emotional_score or 0) * 0.30 + (row.functional_score or 0) * 0.20 +
                           (row.context_score or 0) * 0.10 + (row.isolation_score or 0) * 0.15, 4)

        breakdown = ScoreBreakdown(
            emotional=row.emotional_score or 0.0,
            functional=row.functional_score or 0.0,
            context=row.context_score or 0.0,
            isolation=row.isolation_score or 0.0,
            critical=row.critical_score,
            questionnaire_score=q_estimate,
            physio_score=round((row.final_score - 0.70 * q_estimate) / 0.30, 4) if row.final_score else 0.0,
            eeg_stress_index=row.eeg_avg or 0.0,
            hr_mean=row.avg_pulse or 0.0,
            bp_avg_systolic=row.avg_bp_systolic,
            dominant_emotion=row.dominant_emotion,
        )

        referral_note = None
        risk_class = row.risk_class or "Healthy"
        if risk_class in ["Mild Stress", "Moderate Risk"]:
            cursor.execute("""
                SELECT u.name FROM Users u 
                JOIN Sections s ON u.user_id = s.advisor_id 
                JOIN Students st ON s.section_id = st.section_id 
                WHERE st.user_id = ?
            """, (row.user_id,))
            adv = cursor.fetchone()
            if adv:
                referral_note = f"Please schedule a meeting with your advisor: {adv[0]}."
        elif risk_class in ["High Risk", "Critical Risk"]:
            cursor.execute("""
                SELECT u.name FROM Users u
                JOIN Appointments a ON u.user_id = a.psychologist_id
                WHERE a.session_id = ?
            """, (session_id,))
            psych = cursor.fetchone()
            if psych:
                referral_note = f"An appointment has been automatically scheduled with Dr. {psych[0]}."

        return SessionResult(
            session_id=row.session_id, user_id=row.user_id, user_role=row.user_role,
            recommendation=risk_class, referral_note=referral_note, final_score=row.final_score or 0.0,
            score_breakdown=breakdown, session_duration_minutes=duration,
            calculated_at=row.calculated_at)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_session_result error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve result.")
    finally:
        conn.close()
