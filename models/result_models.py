"""models/result_models.py — Pydantic schemas for MH results."""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a session result."""
    emotional: float = 0.0
    functional: float = 0.0
    context: float = 0.0
    isolation: float = 0.0
    critical: Optional[float] = None
    questionnaire_score: float = 0.0
    physio_score: float = 0.0
    eeg_stress_index: float = 0.0
    hr_mean: float = 0.0
    bp_avg_systolic: Optional[float] = None
    bp_systolic_delta: Optional[float] = None
    dominant_emotion: Optional[str] = None
    emotion_distress: float = 0.0


class SessionResult(BaseModel):
    """Full mental health result for one session."""
    session_id: int
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    recommendation: str
    referral_note: Optional[str] = None
    confidence: float = 0.0
    final_score: float
    score_breakdown: ScoreBreakdown
    session_duration_minutes: Optional[float] = None
    calculated_at: Optional[datetime] = None


class UserHistoryItem(BaseModel):
    """Summary of a single past session."""
    session_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    recommendation: Optional[str] = None
    final_score: Optional[float] = None
    calculated_at: Optional[datetime] = None


class UserHistory(BaseModel):
    """Ordered list of past sessions for a user."""
    user_id: int
    sessions: List[UserHistoryItem]
