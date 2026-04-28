# ============================================================
# models/result_models.py — Pydantic schemas for MH results
# ============================================================

from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a session result."""

    emotional: float = 0.0
    functional: float = 0.0
    context: float = 0.0
    isolation: float = 0.0
    critical: float = 0.0
    eeg_stress_index: float = 0.0
    hr_mean: float = 0.0
    bp_avg: Optional[float] = None
    pulse_avg: Optional[float] = None
    dominant_emotion: Optional[str] = None
    emotion_distress_score: float = 0.0


class SessionResult(BaseModel):
    """
    Full mental health result for one session.
    Maps to the MH_Results table with score breakdown.
    """

    session_id: int
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    recommendation: str        # 'Normal' | 'Calm Down' | 'See Psychologist' | 'Emergency'
    confidence: float = 0.0
    final_score: float
    score_breakdown: ScoreBreakdown
    session_duration_minutes: Optional[float] = None
    calculated_at: Optional[datetime] = None


class UserHistoryItem(BaseModel):
    """Summary of a single past session shown in user history."""

    session_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    recommendation: Optional[str] = None
    final_score: Optional[float] = None
    confidence: Optional[float] = None
    calculated_at: Optional[datetime] = None


class UserHistory(BaseModel):
    """Ordered list of past sessions for a given user."""

    user_id: int
    sessions: List[UserHistoryItem]


class DashboardResultItem(BaseModel):
    """Single result item for psychologist dashboard view."""

    result_id: int
    session_id: int
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    recommendation: Optional[str] = None
    final_score: Optional[float] = None
    confidence: Optional[float] = None
    calculated_at: Optional[datetime] = None
