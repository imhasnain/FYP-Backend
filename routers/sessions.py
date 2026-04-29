# ============================================================
# routers/sessions.py — Session management endpoints
#   POST /session/start
#   POST /session/end
#   GET  /session/{session_id}
# ============================================================

import logging
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.session_models import (
    StartSessionRequest,
    StartSessionResponse,
    EndSessionRequest,
    EndSessionResponse,
    SessionDetailResponse,
)
from ml.feature_builder import build_features, get_all_component_scores
from ml.predictor import predict
from scoring.questionnaire_scorer import score_to_recommendation
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["Sessions"])

# Maps ML recommendation labels → MH_Results.risk_class CHECK constraint values
# DB allows: 'Healthy' | 'Mild Stress' | 'Moderate Risk' | 'High Risk' | 'Critical Risk'
RECOMMENDATION_TO_RISK = {
    "Normal":           "Healthy",
    "Calm Down":        "Mild Stress",
    "See Psychologist": "High Risk",
    "Emergency":        "Critical Risk",
}


@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest):
    """
    Create a new assessment session for a user.

    Inserts a row into Sessions with start_time = current UTC time.
    Returns the new session_id and the start timestamp.

    Args:
        payload: StartSessionRequest with user_id.

    Returns:
        StartSessionResponse with session_id and started_at.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Verify the user exists before creating a session
        cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (payload.user_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {payload.user_id} not found.",
            )

        started_at = now_utc()

        cursor.execute(
            """
            INSERT INTO Sessions (user_id, start_time)
            OUTPUT INSERTED.session_id
            VALUES (?, ?)
            """,
            (payload.user_id, started_at),
        )
        row = cursor.fetchone()
        session_id: int = row[0]

        conn.commit()
        logger.info("Session started: session_id=%d user_id=%d", session_id, payload.user_id)

        return StartSessionResponse(session_id=session_id, started_at=started_at)

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("start_session error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not start session.",
        )
    finally:
        conn.close()


@router.post("/end", response_model=EndSessionResponse)
def end_session(payload: EndSessionRequest):
    """
    End an active session and compute the mental health recommendation.

    Steps:
      1. Verify the session exists and belongs to this user.
      2. Mark the session end_time = now.
      3. Get user role from Users table.
      4. Build the 16-feature vector using feature_builder.
      5. Run ML prediction (or rule-based fallback).
      6. Save all component scores + recommendation to MH_Results.
      7. Return recommendation + confidence to the client.

    Args:
        payload: EndSessionRequest with session_id and user_id.

    Returns:
        EndSessionResponse with recommendation, final_score, confidence.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ── 1. Verify session ownership ───────────────────
        cursor.execute(
            "SELECT session_id, user_id FROM Sessions WHERE session_id = ? AND user_id = ?",
            (payload.session_id, payload.user_id),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or does not belong to this user.",
            )

        # Check if already ended
        cursor.execute(
            "SELECT end_time FROM Sessions WHERE session_id = ?",
            (payload.session_id,),
        )
        end_check = cursor.fetchone()
        if end_check and end_check.end_time is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session is already completed.",
            )

        # ── 2. Mark as completed ──────────────────────────
        ended_at = now_utc()
        cursor.execute(
            "UPDATE Sessions SET end_time = ? WHERE session_id = ?",
            (ended_at, payload.session_id),
        )
        conn.commit()

        # ── 3. Get user role ──────────────────────────────
        cursor.execute(
            "SELECT role FROM Users WHERE user_id = ?",
            (payload.user_id,),
        )
        user_row = cursor.fetchone()
        role = user_row.role if user_row else "student"

        # ── 4. Build feature vector ───────────────────────
        features = build_features(
            session_id=payload.session_id,
            user_id=payload.user_id,
            role=role,
            conn=conn,
        )

        # ── 5. ML prediction ─────────────────────────────
        prediction = predict(features, role)
        recommendation = prediction["recommendation"]
        confidence = prediction["confidence"]

        # ── 6. Get all component scores for saving ────────
        components = get_all_component_scores(
            session_id=payload.session_id,
            user_id=payload.user_id,
            role=role,
            conn=conn,
        )

        # Compute final_score from questionnaire scorer as fallback metric
        q_final = sum(features[0:5]) / 5.0  # average of questionnaire scores
        final_score = round(q_final, 4)

        # ── 7. Save to MH_Results ─────────────────────────
        # Map recommendation -> risk_class (CHECK constrained column)
        risk_class = RECOMMENDATION_TO_RISK.get(recommendation, "Moderate Risk")
        calculated_at = now_utc()
        cursor.execute(
            """
            INSERT INTO MH_Results (
                session_id, user_id,
                emotional_score, functional_score, context_score,
                isolation_score, critical_score,
                final_score, risk_class,
                user_role, performance_score,
                eeg_stress_index, eeg_alpha_power, eeg_theta_power,
                hr_mean, bp_avg_systolic, bp_avg_diastolic, pulse_avg,
                dominant_emotion, emotion_distress_score,
                recommendation, confidence, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.session_id,
                payload.user_id,                          # NOT NULL
                components["emotional_score"],
                components["functional_score"],
                components["context_score"],
                components["isolation_score"],
                components["critical_score"],
                final_score,                              # NOT NULL
                risk_class,                               # risk_class NOT NULL (CHECK constrained)
                role,                                     # user_role
                components["performance_score"],
                components["eeg_stress_index"],
                components["eeg_alpha_power"],
                components["eeg_theta_power"],
                components["hr_mean"],
                components["bp_avg_systolic"],
                components["bp_avg_diastolic"],
                components["pulse_avg"],
                components["dominant_emotion"],
                components["emotion_distress_score"],
                recommendation,                           # recommendation (nullable)
                confidence,
                calculated_at,
            ),
        )
        conn.commit()

        logger.info(
            "Session ended: session_id=%d recommendation=%s score=%.2f confidence=%.2f",
            payload.session_id, recommendation, final_score, confidence,
        )

        return EndSessionResponse(
            session_id=payload.session_id,
            recommendation=recommendation,
            final_score=final_score,
            confidence=confidence,
            ended_at=ended_at,
        )

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("end_session error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not end session.",
        )
    finally:
        conn.close()


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: int):
    """
    Return details of a specific session including data collection counts.

    Args:
        session_id: The session ID to look up.

    Returns:
        SessionDetailResponse with session details and sensor data counts.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT session_id, user_id, start_time, end_time
            FROM Sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )
        row = cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found.",
            )

        # Count sensor data
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'eeg'",
            (session_id,),
        )
        eeg_count = cursor.fetchone().cnt

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'bp'",
            (session_id,),
        )
        bp_count = cursor.fetchone().cnt

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM FacialEmotions WHERE session_id = ?",
            (session_id,),
        )
        emotion_count = cursor.fetchone().cnt

        cursor.execute(
            "SELECT COUNT(DISTINCT stage_number) AS cnt FROM Q_Responses WHERE session_id = ?",
            (session_id,),
        )
        q_stages = cursor.fetchone().cnt

        # Determine status based on end_time
        session_status = "completed" if row.end_time else "active"

        return SessionDetailResponse(
            session_id=row.session_id,
            user_id=row.user_id,
            start_time=row.start_time,
            end_time=row.end_time,
            status=session_status,
            eeg_count=eeg_count,
            bp_count=bp_count,
            emotion_count=emotion_count,
            questionnaire_stages=q_stages,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_session error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve session.",
        )
    finally:
        conn.close()
