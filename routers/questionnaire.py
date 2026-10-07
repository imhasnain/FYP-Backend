"""routers/questionnaire.py — Questionnaire endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from database import get_connection
from models.questionnaire_models import (
    SubmitStageRequest, SubmitStageResponse, StageInfo, QuestionInfo,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/questionnaire", tags=["Questionnaire"])

MAX_STAGES = 5


@router.post("/submit", response_model=SubmitStageResponse)
def submit_stage(payload: SubmitStageRequest):
    """Submit answers for one questionnaire stage."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT session_id FROM Sessions WHERE session_id = ?", (payload.session_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        now = now_utc()
        cursor.executemany("""
            INSERT INTO Q_Responses (session_id, question_id, stage_number, response_choice, cal_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [(payload.session_id, a.question_id, payload.stage_number, str(a.response_choice), a.cal_score, now)
             for a in payload.answers])

        total_score = sum(a.cal_score for a in payload.answers)

        cursor.execute("SELECT threshold FROM Q_Stages WHERE stage_number = ?", (payload.stage_number,))
        stage_row = cursor.fetchone()
        if not stage_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Stage {payload.stage_number} not found.")

        conn.commit()
        passed = total_score >= stage_row.threshold

        if passed and payload.stage_number < MAX_STAGES:
            next_stage = payload.stage_number + 1
            message = f"Stage {payload.stage_number} passed. Proceed to stage {next_stage}."
        elif passed:
            next_stage = None
            message = "All stages completed. Session can now be ended."
        else:
            next_stage = None
            message = f"Stage {payload.stage_number} did not meet threshold."

        logger.info("Stage %d submitted: session=%d score=%.2f passed=%s",
                     payload.stage_number, payload.session_id, total_score, passed)
        return SubmitStageResponse(stage_number=payload.stage_number, total_score=round(total_score, 4),
                                    passed=passed, next_stage=next_stage, message=message)
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("submit_stage error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not submit stage.")
    finally:
        conn.close()


@router.get("/stages", response_model=List[StageInfo])
def get_stages():
    """Return all questionnaire stages."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT stage_id, stage_number, stage_name, target_role, threshold FROM Q_Stages ORDER BY stage_number")
        return [StageInfo(stage_id=r.stage_id, stage_number=r.stage_number, stage_name=r.stage_name,
                          target_role=r.target_role, threshold=r.threshold) for r in cursor.fetchall()]
    except Exception as exc:
        logger.exception("get_stages error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve stages.")
    finally:
        conn.close()


@router.get("/questions/{stage_number}", response_model=List[QuestionInfo])
def get_questions(stage_number: int, role: Optional[str] = Query(None, description="Filter: student or teacher")):
    """Return questions for a stage, optionally filtered by role."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if role:
            cursor.execute("""
                SELECT q.question_id, q.stage_id, q.question_text, q.weight
                FROM Q_Questions q INNER JOIN Q_Stages s ON q.stage_id = s.stage_id
                WHERE s.stage_number = ? AND (s.target_role = ? OR s.target_role = 'both')
                ORDER BY q.question_id""", (stage_number, role))
        else:
            cursor.execute("""
                SELECT q.question_id, q.stage_id, q.question_text, q.weight
                FROM Q_Questions q INNER JOIN Q_Stages s ON q.stage_id = s.stage_id
                WHERE s.stage_number = ? ORDER BY q.question_id""", (stage_number,))

        return [QuestionInfo(question_id=r.question_id, stage_id=r.stage_id,
                             question_text=r.question_text, weight=r.weight) for r in cursor.fetchall()]
    except Exception as exc:
        logger.exception("get_questions error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve questions.")
    finally:
        conn.close()
