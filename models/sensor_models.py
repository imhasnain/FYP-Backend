# ============================================================
# models/sensor_models.py — Pydantic schemas for sensor data
# ============================================================

from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime


class PulseRequest(BaseModel):
    """
    Request body for POST /sensors/pulse.
    'source' distinguishes Muse PPG from the BLE BP machine.
    """

    session_id: int
    pulse_rate: float
    source: str = "muse"  # 'muse' | 'bp_machine'


class PulseResponse(BaseModel):
    """Confirmation response after storing a pulse reading."""

    session_id: int
    pulse_rate: float
    source: str = "muse"
    recorded_at: datetime


class BPRequest(BaseModel):
    """Request body for POST /sensors/bp."""

    session_id: int
    systolic: int
    diastolic: int
    pulse_rate: Optional[int] = None   # BLE BP machines often include pulse


class BPResponse(BaseModel):
    """Confirmation response after storing a BP reading."""

    session_id: int
    systolic: int
    diastolic: int
    pulse_rate: Optional[int]
    recorded_at: datetime


class EmotionRequest(BaseModel):
    """
    Request body for POST /sensors/emotion.
    Called every 5 seconds while the student/teacher fills the questionnaire.
    'image_base64' is a base64-encoded JPEG/PNG webcam frame.
    'user_id' is needed to save the image with user identification.
    """

    session_id: int
    user_id: int
    stage_number: int = 1
    image_base64: str


class EmotionResponse(BaseModel):
    """
    Response body for POST /sensors/emotion.
    'scores' is a dict of emotion label → confidence (0.0–100.0).
    """

    session_id: int
    dominant_emotion: str
    scores: Dict[str, float]
    captured_at: datetime
