# ============================================================
# models/session_models.py — Pydantic schemas for Sessions
# ============================================================

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class StartSessionRequest(BaseModel):
    """Request body for POST /session/start."""

    user_id: int


class StartSessionResponse(BaseModel):
    """Response body for POST /session/start."""

    session_id: int
    started_at: datetime


class EndSessionRequest(BaseModel):
    """Request body for POST /session/end."""

    session_id: int
    user_id: int


class EndSessionResponse(BaseModel):
    """
    Response body for POST /session/end.
    Includes the ML prediction result after processing all session data.
    """

    session_id: int
    recommendation: str      # 'Normal' | 'Calm Down' | 'See Psychologist' | 'Emergency'
    final_score: float
    confidence: float        # Model prediction confidence 0.0–1.0
    ended_at: datetime


class SessionDetailResponse(BaseModel):
    """Full session details returned by GET /session/{session_id}."""

    session_id: int
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str
    eeg_count: int = 0       # Number of EEG readings collected
    bp_count: int = 0        # Number of BP readings collected
    emotion_count: int = 0   # Number of emotion frames processed
    questionnaire_stages: int = 0  # Number of questionnaire stages completed
