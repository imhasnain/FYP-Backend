"""routers/sessions.py — Session management endpoints"""

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
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["Sessions"])

# Maps ML recommendation labels → MH_Results.risk_class CHECK constraint values
RECOMMENDATION_TO_RISK = {
    "Normal":           "Healthy",
    "Calm Down":        "Mild Stress",
    "See Psychologist": "High Risk",
    "Emergency":        "Critical Risk",
}


@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM Users WHERE user_id = ?", (payload.user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {payload.user_id} not found.")

        started_at = now_utc()
        cursor.execute(
            "INSERT INTO Sessions (user_id, start_time) OUTPUT INSERTED.session_id VALUES (?, ?)",
            (payload.user_id, started_at),
        )
        session_id: int = cursor.fetchone()[0]
        conn.commit()

        logger.info("Session started: session_id=%d user_id=%d", session_id, payload.user_id)
        return StartSessionResponse(session_id=session_id, started_at=started_at)

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("start_session error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not start session.")
    finally:
        conn.close()


@router.post("/end", response_model=EndSessionResponse)
def end_session(payload: EndSessionRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Verify session belongs to this user
        cursor.execute(
            "SELECT session_id FROM Sessions WHERE session_id = ? AND user_id = ?",
            (payload.session_id, payload.user_id),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or does not belong to this user.")

        # Check not already ended
        cursor.execute("SELECT end_time FROM Sessions WHERE session_id = ?", (payload.session_id,))
        row = cursor.fetchone()
        if row and row.end_time is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is already completed.")

        # Mark as ended
        ended_at = now_utc()
        cursor.execute("UPDATE Sessions SET end_time = ? WHERE session_id = ?", (ended_at, payload.session_id))
        conn.commit()

        # Get user role
        cursor.execute("SELECT role FROM Users WHERE user_id = ?", (payload.user_id,))
        user_row = cursor.fetchone()
        role = user_row.role if user_row else "student"

        # Build feature vector & run prediction
        features = build_features(session_id=payload.session_id, user_id=payload.user_id, role=role, conn=conn)
        prediction = predict(features, role)
        recommendation = prediction["recommendation"]
        confidence = prediction["confidence"]

        # Get component scores for saving
        components = get_all_component_scores(session_id=payload.session_id, user_id=payload.user_id, role=role, conn=conn)
        final_score = round(sum(features[0:5]) / 5.0, 4)

        risk_class = RECOMMENDATION_TO_RISK.get(recommendation, "Moderate Risk")
        calculated_at = now_utc()
        cursor.execute(
            """
            INSERT INTO MH_Results (
                session_id, user_id,
                emotional_score, functional_score, context_score,
                isolation_score, critical_score,
                eeg_avg, avg_pulse, avg_bp_systolic,
                dominant_emotion, final_score, risk_class, calculated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.session_id, payload.user_id,
                components["emotional_score"], components["functional_score"],
                components["context_score"], components["isolation_score"],
                components["critical_score"], components["eeg_stress_index"],
                components["pulse_avg"], components["bp_avg_systolic"],
                components["dominant_emotion"], final_score, risk_class, calculated_at,
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not end session.")
    finally:
        conn.close()


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: int):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, user_id, start_time, end_time FROM Sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'eeg'", (session_id,)
        )
        eeg_count = cursor.fetchone().cnt

        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'bp'", (session_id,)
        )
        bp_count = cursor.fetchone().cnt

        cursor.execute("SELECT COUNT(*) AS cnt FROM FacialEmotions WHERE session_id = ?", (session_id,))
        emotion_count = cursor.fetchone().cnt

        cursor.execute(
            "SELECT COUNT(DISTINCT stage_number) AS cnt FROM Q_Responses WHERE session_id = ?", (session_id,)
        )
        q_stages = cursor.fetchone().cnt

        return SessionDetailResponse(
            session_id=row.session_id,
            user_id=row.user_id,
            start_time=row.start_time,
            end_time=row.end_time,
            status="completed" if row.end_time else "active",
            eeg_count=eeg_count,
            bp_count=bp_count,
            emotion_count=emotion_count,
            questionnaire_stages=q_stages,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_session error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve session.")
    finally:
        conn.close()
