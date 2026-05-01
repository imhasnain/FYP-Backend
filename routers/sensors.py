"""routers/sensors.py — Biometric sensor data endpoints"""

import base64
import logging
import os
import numpy as np
import cv2
from deepface import DeepFace
from fastapi import APIRouter, HTTPException, status

from config import settings
from database import get_connection
from models.sensor_models import (
    BPRequest, BPResponse,
    EmotionRequest, EmotionResponse,
    PulseRequest, PulseResponse,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sensors", tags=["Sensors"])

# ── Custom emotion model — loaded once at first use ────────────────
_custom_model = None
_custom_model_loaded = False
EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]


def _get_custom_model():
    """Lazy-load the custom TF emotion model once, cache it globally."""
    global _custom_model, _custom_model_loaded
    if _custom_model_loaded:
        return _custom_model

    model_path = os.path.join(settings.BASE_DIR, "ml", "saved_models", "custom_emotion_model.h5")
    if os.path.exists(model_path):
        try:
            import tensorflow as tf
            _custom_model = tf.keras.models.load_model(model_path)
            logger.info("Custom emotion model loaded from %s", model_path)
        except Exception as exc:
            logger.warning("Could not load custom emotion model: %s", exc)
            _custom_model = None
    _custom_model_loaded = True
    return _custom_model


def _predict_with_custom_model(frame) -> tuple[str, dict, float]:
    """
    Try to predict emotion using the custom CNN.
    Returns (dominant_emotion, scores_dict, confidence).
    Returns ("undetected", {}, 0.0) on failure.
    """
    model = _get_custom_model()
    if model is None:
        return "undetected", {}, 0.0

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        if len(faces) == 0:
            return "undetected", {}, 0.0

        # Take the largest face
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]

        # Slightly expand bounding box to match FER-2013 training crops
        pad_w, pad_h = int(w * 0.1), int(h * 0.1)
        x1 = max(0, x - pad_w)
        y1 = max(0, y - pad_h)
        x2 = min(gray.shape[1], x + w + pad_w)
        y2 = min(gray.shape[0], y + h + pad_h)

        roi = cv2.resize(gray[y1:y2, x1:x2], (48, 48)).astype("float32") / 255.0
        roi = np.expand_dims(roi, axis=(0, -1))

        preds = model.predict(roi, verbose=0)[0]
        confidence = float(np.max(preds) * 100.0)
        scores = {EMOTIONS[i]: float(preds[i] * 100.0) for i in range(len(EMOTIONS))}

        # Only trust the model if it's confident enough
        if confidence > 55.0:
            dominant = EMOTIONS[int(np.argmax(preds))]
            logger.info("Custom model: %s (%.1f%%)", dominant, confidence)
            return dominant, scores, confidence

        logger.info("Custom model confidence low (%.1f%%) — falling back to DeepFace", confidence)
        return "undetected", {}, 0.0

    except Exception as exc:
        logger.warning("Custom model prediction failed: %s. Falling back to DeepFace.", exc)
        return "undetected", {}, 0.0


# ── Pulse endpoint ─────────────────────────────────────────────────

@router.post("/pulse", response_model=PulseResponse)
def record_pulse(payload: PulseRequest):
    if payload.source not in ("muse", "bp_machine"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source must be 'muse' or 'bp_machine'.")

    conn = get_connection()
    try:
        recorded_at = now_utc()
        conn.cursor().execute(
            "INSERT INTO SensorData (session_id, pulse_rate, data_type, recorded_at) VALUES (?, ?, 'ppg', ?)",
            (payload.session_id, int(payload.pulse_rate), recorded_at),
        )
        conn.commit()
        logger.info("Pulse recorded: session=%d rate=%.1f source=%s", payload.session_id, payload.pulse_rate, payload.source)
        return PulseResponse(session_id=payload.session_id, pulse_rate=payload.pulse_rate, source=payload.source, recorded_at=recorded_at)
    except Exception as exc:
        conn.rollback()
        logger.exception("record_pulse error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store pulse reading.")
    finally:
        conn.close()


# ── Blood pressure endpoint ────────────────────────────────────────

@router.post("/bp", response_model=BPResponse)
def record_bp(payload: BPRequest):
    conn = get_connection()
    try:
        recorded_at = now_utc()
        conn.cursor().execute(
            "INSERT INTO SensorData (session_id, bp_systolic, bp_diastolic, pulse_rate, data_type, recorded_at) VALUES (?, ?, ?, ?, 'bp', ?)",
            (payload.session_id, payload.systolic, payload.diastolic, payload.pulse_rate, recorded_at),
        )
        conn.commit()
        logger.info("BP recorded: session=%d sys=%d dia=%d", payload.session_id, payload.systolic, payload.diastolic)
        return BPResponse(session_id=payload.session_id, systolic=payload.systolic, diastolic=payload.diastolic, pulse_rate=payload.pulse_rate, recorded_at=recorded_at)
    except Exception as exc:
        conn.rollback()
        logger.exception("record_bp error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not store BP reading.")
    finally:
        conn.close()


# ── Emotion endpoint ───────────────────────────────────────────────

@router.post("/emotion", response_model=EmotionResponse)
def analyze_emotion(payload: EmotionRequest):
    # Decode base64 image
    try:
        img_bytes = base64.b64decode(payload.image_base64)
        np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("OpenCV could not decode the image.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid image data: {exc}")

    # Save image to disk
    captured_at = now_utc()
    timestamp_str = captured_at.strftime("%Y%m%d_%H%M%S_%f")
    image_name = f"emotion_{payload.user_id}_{payload.session_id}_{timestamp_str}.jpg"
    image_path = os.path.join(settings.EMOTION_IMAGES_DIR, image_name)
    try:
        os.makedirs(settings.EMOTION_IMAGES_DIR, exist_ok=True)
        cv2.imwrite(image_path, frame)
        logger.info("Emotion image saved: %s", image_path)
    except Exception as exc:
        logger.warning("Could not save emotion image: %s", exc)

    # Insert into EmotionImages
    conn = get_connection()
    image_id = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO EmotionImages (user_id, session_id, stage_number, image_name, captured_at)
            OUTPUT INSERTED.image_id
            VALUES (?, ?, ?, ?, ?)
            """,
            (payload.user_id, payload.session_id, payload.stage_number, image_name, captured_at),
        )
        row = cursor.fetchone()
        if row:
            image_id = row[0]
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.warning("EmotionImages insert failed: %s", exc)

    # Try custom model, fall back to DeepFace
    dominant_emotion, emotion_scores, confidence = _predict_with_custom_model(frame)

    if dominant_emotion == "undetected":
        try:
            analysis = DeepFace.analyze(img_path=frame, actions=["emotion"], enforce_detection=False, silent=True)
            result = analysis[0] if isinstance(analysis, list) else analysis
            dominant_emotion = result.get("dominant_emotion", "undetected")
            emotion_scores = result.get("emotion", {})
            confidence = emotion_scores.get(dominant_emotion, 0.0)
        except Exception as exc:
            logger.error("DeepFace failed for session %d: %s", payload.session_id, exc)
            dominant_emotion = "undetected"
            emotion_scores = {}

    # Insert into FacialEmotions
    try:
        cursor = conn.cursor()
        scores = emotion_scores
        cursor.execute(
            """
            INSERT INTO FacialEmotions
                (session_id, dominant_emotion, happy, sad, angry, fear, surprise, disgust, neutral,
                 captured_at, image_id, stage_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.session_id, dominant_emotion,
                scores.get("happy", 0.0), scores.get("sad", 0.0), scores.get("angry", 0.0),
                scores.get("fear", 0.0), scores.get("surprise", 0.0), scores.get("disgust", 0.0),
                scores.get("neutral", 0.0),
                captured_at, image_id, payload.stage_number,
            ),
        )
        conn.commit()
        logger.info("Emotion captured: session=%d dominant=%s image=%s", payload.session_id, dominant_emotion, image_name)
    except Exception as exc:
        conn.rollback()
        logger.exception("FacialEmotions insert error: %s", exc)

    conn.close()

    return EmotionResponse(
        session_id=payload.session_id,
        dominant_emotion=dominant_emotion,
        scores={k: round(v, 2) for k, v in emotion_scores.items()} if emotion_scores else {},
        captured_at=captured_at,
    )
