"""routers/sensors.py — Biometric sensor data endpoints (pulse, BP, emotion)."""

import base64
import logging
import os

import cv2
import numpy as np
from deepface import DeepFace
from fastapi import APIRouter, HTTPException, status

from config import settings
from database import get_connection
from models.sensor_models import (
    BPRequest, BPResponse, EmotionRequest, EmotionResponse,
    PulseRequest, PulseResponse,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sensors", tags=["Sensors"])


@router.post("/pulse", response_model=PulseResponse)
def record_pulse(payload: PulseRequest):
    """Save a pulse/heart-rate reading to SensorData."""
    conn = get_connection()
    try:
        recorded_at = now_utc()
        conn.cursor().execute(
            "INSERT INTO SensorData (session_id, pulse_rate, data_type, recorded_at) VALUES (?, ?, 'ppg', ?)",
            (payload.session_id, int(payload.pulse_rate), recorded_at),
        )
        conn.commit()
        logger.info("Pulse recorded: session=%d rate=%.1f", payload.session_id, payload.pulse_rate)
        return PulseResponse(session_id=payload.session_id, pulse_rate=payload.pulse_rate,
                             source=payload.source, recorded_at=recorded_at)
    except Exception as exc:
        conn.rollback()
        logger.exception("record_pulse error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store pulse.")
    finally:
        conn.close()


@router.post("/bp", response_model=BPResponse)
def record_bp(payload: BPRequest):
    """Save a blood pressure reading to SensorData."""
    conn = get_connection()
    try:
        recorded_at = now_utc()
        conn.cursor().execute(
            "INSERT INTO SensorData (session_id, bp_systolic, bp_diastolic, pulse_rate, data_type, recorded_at) "
            "VALUES (?, ?, ?, ?, 'bp', ?)",
            (payload.session_id, payload.systolic, payload.diastolic, payload.pulse_rate, recorded_at),
        )
        conn.commit()
        logger.info("BP recorded: session=%d sys=%d dia=%d", payload.session_id, payload.systolic, payload.diastolic)
        return BPResponse(session_id=payload.session_id, systolic=payload.systolic,
                          diastolic=payload.diastolic, pulse_rate=payload.pulse_rate, recorded_at=recorded_at)
    except Exception as exc:
        conn.rollback()
        logger.exception("record_bp error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store BP.")
    finally:
        conn.close()


@router.post("/emotion", response_model=EmotionResponse)
def analyze_emotion(payload: EmotionRequest):
    """Decode a base64 camera frame, run DeepFace, save emotion to DB."""
    try:
        img_bytes = base64.b64decode(payload.image_base64)
        np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("OpenCV could not decode the image.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid image: {exc}")

    # Save image to disk
    captured_at = now_utc()
    ts_str = captured_at.strftime("%Y%m%d_%H%M%S_%f")
    q_str = f"_q{payload.question_id}" if payload.question_id else ""
    image_name = f"emotion_{payload.user_id}_{payload.session_id}{q_str}_{ts_str}.jpg"
    try:
        os.makedirs(settings.EMOTION_IMAGES_DIR, exist_ok=True)
        cv2.imwrite(os.path.join(settings.EMOTION_IMAGES_DIR, image_name), frame)
    except Exception as exc:
        logger.warning("Could not save emotion image: %s", exc)

    # Run DeepFace
    dominant_emotion = "neutral"
    emotion_scores = {}
    try:
        analysis = DeepFace.analyze(img_path=frame, actions=["emotion"], enforce_detection=False, silent=True)
        result = analysis[0] if isinstance(analysis, list) else analysis
        dominant_emotion = result.get("dominant_emotion", "neutral")
        emotion_scores = result.get("emotion", {})
    except Exception as exc:
        logger.error("DeepFace failed for session %d: %s", payload.session_id, exc)

    # Save to FacialEmotions
    conn = get_connection()
    try:
        conn.cursor().execute("""
            INSERT INTO FacialEmotions
                (session_id, dominant_emotion, happy, sad, angry, fear, surprise, disgust, neutral, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.session_id, dominant_emotion,
             emotion_scores.get("happy", 0.0), emotion_scores.get("sad", 0.0),
             emotion_scores.get("angry", 0.0), emotion_scores.get("fear", 0.0),
             emotion_scores.get("surprise", 0.0), emotion_scores.get("disgust", 0.0),
             emotion_scores.get("neutral", 0.0), captured_at))
        conn.commit()
        logger.info("Emotion captured: session=%d dominant=%s", payload.session_id, dominant_emotion)
    except Exception as exc:
        conn.rollback()
        logger.exception("FacialEmotions insert error: %s", exc)
    finally:
        conn.close()

    return EmotionResponse(
        session_id=payload.session_id, dominant_emotion=dominant_emotion,
        scores={k: round(v, 2) for k, v in emotion_scores.items()} if emotion_scores else {},
        captured_at=captured_at)
