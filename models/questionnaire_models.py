# ============================================================
# models/questionnaire_models.py — Pydantic schemas for Q&A
# ============================================================

from pydantic import BaseModel
from typing import List, Optional


class QuestionnaireAnswer(BaseModel):
    """A single question-answer pair submitted by the patient."""

    question_id: int
    response_choice: str | int   # e.g. 'Never', 'Sometimes', 'Always' or 0-4
    cal_score: float       # Weighted score calculated on the client side


class SubmitStageRequest(BaseModel):
    """Request body for POST /questionnaire/submit."""

    session_id: int
    stage_number: int
    answers: List[QuestionnaireAnswer]


class SubmitStageResponse(BaseModel):
    """
    Response body for POST /questionnaire/submit.
    'passed' indicates whether the stage threshold was met.
    'next_stage' is None when all stages are complete.
    """

    stage_number: int
    total_score: float
    passed: bool
    next_stage: Optional[int] = None
    message: str


class StageInfo(BaseModel):
    """Minimal stage metadata returned by GET /questionnaire/stages."""

    stage_id: int
    stage_number: int
    stage_name: str
    target_role: str
    threshold: float


class QuestionInfo(BaseModel):
    """Single question returned by GET /questionnaire/questions/{stage}."""

    question_id: int
    stage_id: int
    question_text: str
    weight: float
