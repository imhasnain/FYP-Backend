# ============================================================
# routers/questionnaire.py — Questionnaire endpoints
#   POST /questionnaire/submit
#   GET  /questionnaire/stages
#   GET  /questionnaire/questions/{stage_number}
# ============================================================

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from database import get_connection
from models.questionnaire_models import (
    SubmitStageRequest,
    SubmitStageResponse,
    StageInfo,
    QuestionInfo,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/questionnaire", tags=["Questionnaire"])

# Total number of questionnaire stages
MAX_STAGES = 5


@router.post("/submit", response_model=SubmitStageResponse)
def submit_stage(payload: SubmitStageRequest):
    """
    Submit answers for one questionnaire stage and evaluate whether
    the stage threshold was met.

    Steps:
      1. Verify the session exists.
      2. Bulk-insert all answers into Q_Responses.
      3. Sum cal_score for this stage.
      4. Look up the stage threshold from Q_Stages.
      5. Determine passed/failed and next_stage.
      6. Return SubmitStageResponse.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # ── 1. Verify session ─────────────────────────────
        cursor.execute(
            "SELECT session_id FROM Sessions WHERE session_id = ?",
            (payload.session_id,),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {payload.session_id} not found.",
            )

        # ── 2. Bulk insert answers ────────────────────────
        now = now_utc()
        insert_rows = [
            (
                payload.session_id,
                answer.question_id,
                payload.stage_number,
                str(answer.response_choice),
                answer.cal_score,
                now,
            )
            for answer in payload.answers
        ]
        cursor.executemany(
            """
            INSERT INTO Q_Responses
                (session_id, question_id, stage_number, response_choice, cal_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )

        # ── 3. Sum scores for this stage ──────────────────
        total_score: float = sum(a.cal_score for a in payload.answers)

        # ── 4. Fetch stage threshold ──────────────────────
        cursor.execute(
            "SELECT threshold FROM Q_Stages WHERE stage_number = ?",
            (payload.stage_number,),
        )
        stage_row = cursor.fetchone()
        if not stage_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stage {payload.stage_number} not found in Q_Stages.",
            )
        threshold: float = stage_row.threshold

        conn.commit()

        # ── 5. Evaluate pass/fail + next stage ────────────
        passed = total_score >= threshold

        if passed and payload.stage_number < MAX_STAGES:
            next_stage = payload.stage_number + 1
            message = (
                f"Stage {payload.stage_number} passed (score {total_score:.2f} ≥ "
                f"threshold {threshold:.2f}). Proceed to stage {next_stage}."
            )
        elif passed and payload.stage_number >= MAX_STAGES:
            next_stage = None
            message = (
                f"All {MAX_STAGES} stages completed. "
                f"Session can now be ended to generate the final report."
            )
        else:
            next_stage = None
            message = (
                f"Stage {payload.stage_number} did not meet the threshold "
                f"(score {total_score:.2f} < threshold {threshold:.2f}). "
                "Flagged for manual psychologist review."
            )

        logger.info(
            "Stage %d submitted: session=%d score=%.2f passed=%s",
            payload.stage_number, payload.session_id, total_score, passed,
        )

        return SubmitStageResponse(
            stage_number=payload.stage_number,
            total_score=round(total_score, 4),
            passed=passed,
            next_stage=next_stage,
            message=message,
        )

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("submit_stage error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not submit questionnaire stage.",
        )
    finally:
        conn.close()


@router.get("/stages", response_model=List[StageInfo])
def get_stages():
    """
    Return all questionnaire stages ordered by stage_number.

    Each stage entry includes its threshold score and target role
    ('student', 'teacher', or 'both').
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT stage_id, stage_number, stage_name, target_role, threshold
            FROM Q_Stages
            ORDER BY stage_number ASC
            """
        )
        rows = cursor.fetchall()
        return [
            StageInfo(
                stage_id=r.stage_id,
                stage_number=r.stage_number,
                stage_name=r.stage_name,
                target_role=r.target_role,
                threshold=r.threshold,
            )
            for r in rows
        ]

    except Exception as exc:
        logger.exception("get_stages error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve stages.",
        )
    finally:
        conn.close()


@router.get("/questions/{stage_number}", response_model=List[QuestionInfo])
def get_questions(stage_number: int):
    """
    Return all questions for a given stage number.

    Joins Q_Questions → Q_Stages to filter by stage_number.
    Returns an empty list if the stage has no questions yet.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT q.question_id, q.stage_id, q.question_text, q.weight
            FROM Q_Questions q
            INNER JOIN Q_Stages s ON q.stage_id = s.stage_id
            WHERE s.stage_number = ?
            ORDER BY q.question_id ASC
            """,
            (stage_number,),
        )
        rows = cursor.fetchall()
        return [
            QuestionInfo(
                question_id=r.question_id,
                stage_id=r.stage_id,
                question_text=r.question_text,
                weight=r.weight,
            )
            for r in rows
        ]

    except Exception as exc:
        logger.exception("get_questions error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve questions.",
        )
    finally:
        conn.close()
