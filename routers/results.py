# ============================================================
# routers/results.py — Mental Health Results endpoints
#   GET /results/{session_id}
#   GET /results/user/{user_id}
#   GET /results/all
# ============================================================

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from database import get_connection
from models.result_models import (
    SessionResult,
    ScoreBreakdown,
    UserHistory,
    UserHistoryItem,
    DashboardResultItem,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/user/{user_id}", response_model=UserHistory)
def get_user_history(user_id: int):
    """
    Return all completed sessions and their results for a user,
    ordered by most recent first.

    Args:
        user_id: The user to look up.

    Returns:
        UserHistory with a list of past session results.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Verify user exists
        cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found.",
            )

        cursor.execute(
            """
            SELECT
                s.session_id,
                s.start_time,
                s.end_time,
                r.recommendation,
                r.final_score,
                r.confidence,
                r.calculated_at
            FROM Sessions s
            INNER JOIN MH_Results r ON s.session_id = r.session_id
            WHERE s.user_id = ?
            ORDER BY s.start_time DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()

        items = [
            UserHistoryItem(
                session_id=row.session_id,
                start_time=row.start_time,
                end_time=row.end_time,
                recommendation=row.recommendation,
                final_score=row.final_score,
                confidence=row.confidence,
                calculated_at=row.calculated_at,
            )
            for row in rows
        ]

        return UserHistory(user_id=user_id, sessions=items)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_user_history error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user history.",
        )
    finally:
        conn.close()


@router.get("/all", response_model=List[DashboardResultItem])
def get_all_results(
    role: Optional[str] = Query(None, description="Filter by user role: student or teacher"),
    recommendation: Optional[str] = Query(None, description="Filter by recommendation"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
):
    """
    Return all session results with optional filters.
    For the psychologist dashboard — shows all sessions with risk assessments.

    Args:
        role:           Optional filter by user_role ('student' or 'teacher').
        recommendation: Optional filter by recommendation string.
        limit:          Max number of results (default 50).

    Returns:
        List of DashboardResultItem ordered by calculated_at DESC.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Build dynamic query with filters
        query = """
            SELECT TOP (?)
                r.result_id,
                r.session_id,
                s.user_id,
                r.user_role,
                r.recommendation,
                r.final_score,
                r.confidence,
                r.calculated_at
            FROM MH_Results r
            INNER JOIN Sessions s ON r.session_id = s.session_id
            WHERE 1=1
        """
        params = [limit]

        if role:
            query += " AND r.user_role = ?"
            params.append(role)

        if recommendation:
            query += " AND r.recommendation = ?"
            params.append(recommendation)

        query += " ORDER BY r.calculated_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [
            DashboardResultItem(
                result_id=row.result_id,
                session_id=row.session_id,
                user_id=row.user_id,
                user_role=row.user_role,
                recommendation=row.recommendation,
                final_score=row.final_score,
                confidence=row.confidence,
                calculated_at=row.calculated_at,
            )
            for row in rows
        ]

    except Exception as exc:
        logger.exception("get_all_results error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve results.",
        )
    finally:
        conn.close()


@router.get("/{session_id}", response_model=SessionResult)
def get_session_result(session_id: int):
    """
    Return the full mental health result for a specific session,
    including the complete score breakdown.

    Args:
        session_id: The session to look up.

    Returns:
        SessionResult with all score components and recommendation.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                r.session_id,
                s.user_id,
                r.user_role,
                r.emotional_score,
                r.functional_score,
                r.context_score,
                r.isolation_score,
                r.critical_score,
                r.eeg_stress_index,
                r.hr_mean,
                r.bp_avg_systolic,
                r.bp_avg_diastolic,
                r.pulse_avg,
                r.dominant_emotion,
                r.emotion_distress_score,
                r.final_score,
                r.recommendation,
                r.confidence,
                r.calculated_at,
                s.start_time,
                s.end_time
            FROM MH_Results r
            INNER JOIN Sessions s ON r.session_id = s.session_id
            WHERE r.session_id = ?
            """,
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No result found for session {session_id}. "
                    "The session may still be active or scoring may not have run yet."
                ),
            )

        # Calculate session duration in minutes
        duration = None
        if row.start_time and row.end_time:
            delta = row.end_time - row.start_time
            duration = round(delta.total_seconds() / 60.0, 2)

        # Compute bp_avg for breakdown
        bp_avg = None
        if row.bp_avg_systolic is not None and row.bp_avg_diastolic is not None:
            bp_avg = round((row.bp_avg_systolic + row.bp_avg_diastolic) / 2.0, 1)

        breakdown = ScoreBreakdown(
            emotional=row.emotional_score or 0.0,
            functional=row.functional_score or 0.0,
            context=row.context_score or 0.0,
            isolation=row.isolation_score or 0.0,
            critical=row.critical_score or 0.0,
            eeg_stress_index=row.eeg_stress_index or 0.0,
            hr_mean=row.hr_mean or 0.0,
            bp_avg=bp_avg,
            pulse_avg=row.pulse_avg,
            dominant_emotion=row.dominant_emotion,
            emotion_distress_score=row.emotion_distress_score or 0.0,
        )

        return SessionResult(
            session_id=row.session_id,
            user_id=row.user_id,
            user_role=row.user_role,
            recommendation=row.recommendation or "Normal",
            confidence=row.confidence or 0.0,
            final_score=row.final_score or 0.0,
            score_breakdown=breakdown,
            session_duration_minutes=duration,
            calculated_at=row.calculated_at,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_session_result error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve session result.",
        )
    finally:
        conn.close()
