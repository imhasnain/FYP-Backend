"""routers/psychologist.py — Psychologist endpoints for appointments and adaptive feedback."""

import logging
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status
from database import get_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/psychologist", tags=["Psychologist"])

class FeedbackRequest(BaseModel):
    psychologist_id: int
    question_id: int
    usefulness_score: int  # 1 to 5
    comments: str = ""

@router.get("/{psychologist_id}/appointments")
def get_appointments(psychologist_id: int):
    """Get all students assigned to this psychologist."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.appointment_id, a.student_id, u.name as student_name, 
                   a.session_id, a.status, a.created_at, m.risk_class as recommendation
            FROM Appointments a
            JOIN Users u ON a.student_id = u.user_id
            LEFT JOIN MH_Results m ON a.session_id = m.session_id
            WHERE a.psychologist_id = ?
            ORDER BY a.created_at DESC
            """, (psychologist_id,)
        )
        rows = cursor.fetchall()
        appointments = []
        for r in rows:
            appointments.append({
                "appointment_id": r[0],
                "student_id": r[1],
                "student_name": r[2],
                "session_id": r[3],
                "status": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "recommendation": r[6] or "Pending"
            })
        return {"appointments": appointments}
    except Exception as exc:
        logger.exception("Error getting appointments: %s", exc)
        raise HTTPException(status_code=500, detail="Could not fetch appointments.")
    finally:
        conn.close()

@router.post("/feedback")
def submit_question_feedback(payload: FeedbackRequest):
    """Psychologist submits feedback on how useful a question was (Adaptive Learning)."""
    if payload.usefulness_score < 1 or payload.usefulness_score > 5:
        raise HTTPException(status_code=400, detail="Score must be between 1 and 5.")
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO QuestionFeedback (psychologist_id, question_id, usefulness_score) VALUES (?, ?, ?)",
            (payload.psychologist_id, payload.question_id, payload.usefulness_score)
        )
        conn.commit()
        return {"message": "Feedback submitted successfully."}
    except Exception as exc:
        conn.rollback()
        logger.exception("Error saving feedback: %s", exc)
        raise HTTPException(status_code=500, detail="Could not save feedback.")
    finally:
        conn.close()

@router.get("/questions/all")
def get_all_questions_for_feedback():
    """Fetch all questions for the psychologist to provide feedback on."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT question_id, stage_id, question_text FROM Q_Questions ORDER BY stage_id, question_id")
        rows = cursor.fetchall()
        return {"questions": [{"question_id": r[0], "stage_id": r[1], "question_text": r[2]} for r in rows]}
    finally:
        conn.close()

@router.get("/session/{session_id}/answers")
def get_session_answers(session_id: int):
    """Fetch the specific questionnaire answers for a session."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT q.question_id, q.question_text, a.answer_text, a.weight 
            FROM Q_Responses r
            JOIN Q_Answers a ON r.answer_id = a.answer_id
            JOIN Q_Questions q ON a.question_id = q.question_id
            WHERE r.session_id = ?
            ORDER BY q.stage_id, q.question_id
        """, (session_id,))
        rows = cursor.fetchall()
        return {"answers": [
            {
                "question_id": r[0],
                "question_text": r[1],
                "answer_text": r[2],
                "weight": r[3]
            } for r in rows
        ]}
    except Exception as exc:
        logger.exception("Error getting answers: %s", exc)
        raise HTTPException(status_code=500, detail="Could not fetch answers.")
    finally:
        conn.close()
