"""routers/sessions.py — Session lifecycle: start, end (with scoring), and detail."""

import logging
from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.session_models import (
    StartSessionRequest, StartSessionResponse,
    EndSessionRequest, EndSessionResponse, SessionDetailResponse,
)
from processing.scorer import (
    get_stage_scores, calc_student_score, calc_teacher_score,
    calc_physio_score, fuse_scores, classify, safety_override,
    get_feedback_weights,
)
from processing.eeg import preprocess_eeg
from processing.emotions import preprocess_emotions
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["Sessions"])

# Maps recommendation labels to MH_Results.risk_class CHECK constraint values
_RISK_MAP = {
    "Normal": "Healthy",
    "Calm Down": "Mild Stress",
    "See Psychologist": "High Risk",
    "Emergency": "Critical Risk",
}


@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest):
    """Create a new assessment session."""
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
        session_id = cursor.fetchone()[0]
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
    """End a session and run the full scoring pipeline."""
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Verify session
        cursor.execute("SELECT session_id, end_time FROM Sessions WHERE session_id = ? AND user_id = ?",
                        (payload.session_id, payload.user_id))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
        if row.end_time is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already ended.")

        # 2. Mark ended
        ended_at = now_utc()
        cursor.execute("UPDATE Sessions SET end_time = ? WHERE session_id = ?", (ended_at, payload.session_id))
        conn.commit()

        # Stop active EEG stream thread for this session
        try:
            from hardware.eeg_stream import stop_eeg_stream
            stop_eeg_stream(payload.session_id)
        except Exception as _eeg_err:
            logger.warning("Could not stop EEG stream for session %d: %s", payload.session_id, _eeg_err)

        # 3. Get user role
        cursor.execute("SELECT role FROM Users WHERE user_id = ?", (payload.user_id,))
        role = cursor.fetchone().role

        # 4. Questionnaire scores
        stages = get_stage_scores(payload.session_id, conn)

        # Load psychologist feedback weights (adjusts importance of each stage)
        feedback_weights = get_feedback_weights(conn)

        # 5-6. Context data + q_score
        if role == "student":
            cursor.execute("SELECT cgpa_trend, attendance_drop FROM Students WHERE user_id = ?", (payload.user_id,))
            s = cursor.fetchone()
            q_score = calc_student_score(stages,
                                         cgpa_trend=float(s.cgpa_trend or 0) if s else 0.0,
                                         attendance_drop=float(s.attendance_drop or 0) if s else 0.0,
                                         weights=feedback_weights)
        else:
            cursor.execute("SELECT workload_hrs FROM Teachers WHERE user_id = ?", (payload.user_id,))
            t = cursor.fetchone()
            q_score = calc_teacher_score(stages, course_load=float(t.workload_hrs or 0) if t else 0.0)


        # 7. EEG
        eeg = preprocess_eeg(payload.session_id, conn)

        # 8. Heart rate
        cursor.execute("SELECT AVG(CAST(pulse_rate AS FLOAT)) AS avg_hr FROM SensorData "
                        "WHERE session_id = ? AND pulse_rate IS NOT NULL AND pulse_rate > 0",
                        (payload.session_id,))
        hr_row = cursor.fetchone()
        avg_hr = float(hr_row.avg_hr) if hr_row and hr_row.avg_hr else 72.0
        hr_score = min(4.0, max(0.0, (avg_hr - 72.0) / 10.0))

        # 9. Face emotions
        emo = preprocess_emotions(payload.session_id, conn)

        # 10. Blood pressure delta
        cursor.execute("SELECT TOP 1 bp_systolic FROM SensorData "
                        "WHERE session_id = ? AND data_type = 'bp' AND bp_systolic IS NOT NULL "
                        "ORDER BY recorded_at ASC", (payload.session_id,))
        first_bp = cursor.fetchone()
        cursor.execute("SELECT TOP 1 bp_systolic FROM SensorData "
                        "WHERE session_id = ? AND data_type = 'bp' AND bp_systolic IS NOT NULL "
                        "ORDER BY recorded_at DESC", (payload.session_id,))
        last_bp = cursor.fetchone()
        bp_delta = (int(last_bp.bp_systolic) - int(first_bp.bp_systolic)) if first_bp and last_bp else 0
        bp_score = min(4.0, max(0.0, bp_delta / 10.0))

        # 11-14. Physio, fusion, classification, safety
        physio = calc_physio_score(eeg["eeg_score"], emo["face_score"], hr_score, bp_score)
        final = fuse_scores(q_score, physio)
        recommendation = classify(final)
        recommendation, final = safety_override(payload.session_id, conn, recommendation, final)

        # 15-16. Save to MH_Results
        risk_class = _RISK_MAP.get(recommendation, "Moderate Risk")
        cursor.execute("""
            INSERT INTO MH_Results (
                session_id, user_id, emotional_score, functional_score,
                context_score, isolation_score, critical_score,
                eeg_avg, avg_pulse, avg_bp_systolic,
                dominant_emotion, final_score, risk_class, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.session_id, payload.user_id,
             stages.get(1, 0.0), stages.get(2, 0.0), stages.get(3, 0.0),
             stages.get(4, 0.0), stages.get(5, 0.0),
             eeg["stress_index"], avg_hr,
             int(first_bp.bp_systolic) if first_bp else None,
             emo["dominant_emotion"], final, risk_class, now_utc()))
             
        # 17. Referrals & Appointments
        referral_note = None
        if risk_class in ["Mild Stress", "Moderate Risk"]:
            # Find advisor for this student's section
            cursor.execute("""
                SELECT u.user_id, u.name FROM Users u 
                JOIN Sections s ON u.user_id = s.advisor_id 
                JOIN Students st ON s.section_id = st.section_id 
                WHERE st.user_id = ?
            """, (payload.user_id,))
            adv = cursor.fetchone()
            if adv:
                referral_note = f"Please schedule a meeting with your advisor: {adv[1]}."
                # Save notification for the advisor so they can see it
                cursor.execute("""
                    INSERT INTO AdvisorNotifications (advisor_id, student_id, session_id, message)
                    VALUES (?, ?, ?, ?)
                """, (adv[0], payload.user_id, payload.session_id,
                      f"Student has reported Mild Stress in session #{payload.session_id}. Please reach out to them."))

        elif risk_class in ["High Risk", "Critical Risk"]:
            # Load balance to psychologist with fewest appointments
            cursor.execute("""
                SELECT u.user_id, u.name, COUNT(a.appointment_id) as active_loads
                FROM Users u
                LEFT JOIN Appointments a ON u.user_id = a.psychologist_id AND a.status = 'Scheduled'
                WHERE u.role = 'psychologist'
                GROUP BY u.user_id, u.name
                ORDER BY active_loads ASC, u.user_id ASC
            """)
            psych = cursor.fetchone()
            if psych:
                cursor.execute("""
                    INSERT INTO Appointments (student_id, psychologist_id, session_id, status)
                    VALUES (?, ?, ?, 'Scheduled')
                """, (payload.user_id, psych[0], payload.session_id))
                referral_note = f"An appointment has been automatically scheduled with Dr. {psych[1]}."

        conn.commit()

        logger.info("Session %d ended: recommendation=%s score=%.2f", payload.session_id, recommendation, final)
        return EndSessionResponse(
            session_id=payload.session_id, recommendation=recommendation,
            referral_note=referral_note, final_score=final, 
            confidence=1.0, ended_at=ended_at
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
    """Return session details with data counts."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, user_id, start_time, end_time FROM Sessions WHERE session_id = ?",
                        (session_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        cursor.execute("SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'eeg'", (session_id,))
        eeg_count = cursor.fetchone().cnt
        cursor.execute("SELECT COUNT(*) AS cnt FROM SensorData WHERE session_id = ? AND data_type = 'bp'", (session_id,))
        bp_count = cursor.fetchone().cnt
        cursor.execute("SELECT COUNT(*) AS cnt FROM FacialEmotions WHERE session_id = ?", (session_id,))
        emotion_count = cursor.fetchone().cnt
        cursor.execute("SELECT COUNT(DISTINCT stage_number) AS cnt FROM Q_Responses WHERE session_id = ?", (session_id,))
        q_stages = cursor.fetchone().cnt

        return SessionDetailResponse(
            session_id=row.session_id, user_id=row.user_id,
            start_time=row.start_time, end_time=row.end_time,
            status="completed" if row.end_time else "active",
            eeg_count=eeg_count, bp_count=bp_count,
            emotion_count=emotion_count, questionnaire_stages=q_stages)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_session error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve session.")
    finally:
        conn.close()
