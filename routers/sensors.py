# ============================================================
# routers/sensors.py — Biometric sensor data endpoints
#   POST /sensors/pulse
#   POST /sensors/bp
#   POST /sensors/emotion
#   POST /sensors/bp/baseline
# ============================================================

import base64
import logging
import os
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np
from deepface import DeepFace
from fastapi import APIRouter, HTTPException, status

from config import settings
from database import get_connection
from models.sensor_models import (
    BPRequest,
    BPResponse,
    EmotionRequest,
    EmotionResponse,
    PulseRequest,
    PulseResponse,
)
from utils.time_utils import now_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sensors", tags=["Sensors"])


# =====================================================
# PULSE ENDPOINT
# =====================================================

@router.post("/pulse", response_model=PulseResponse)
def record_pulse(payload: PulseRequest):
    """
    Store a pulse/heart-rate reading.

    Accepts readings from two sources:
      - 'muse'       : Muse headset PPG channel
      - 'bp_machine' : BLE blood pressure cuff (which also reports pulse)

    Inserts a row into SensorData with data_type='ppg'.

    Args:
        payload: PulseRequest with session_id, pulse_rate, and source.

    Returns:
        PulseResponse confirming the saved reading.
    """
    if payload.source not in ("muse", "bp_machine"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="source must be 'muse' or 'bp_machine'.",
        )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        recorded_at = now_utc()

        cursor.execute(
            """
            INSERT INTO SensorData
                (session_id, pulse_rate, data_type, recorded_at)
            VALUES (?, ?, 'ppg', ?)
            """,
            (payload.session_id, int(payload.pulse_rate), recorded_at),
        )
        conn.commit()

        logger.info(
            "Pulse recorded: session=%d rate=%.1f source=%s",
            payload.session_id, payload.pulse_rate, payload.source,
        )

        return PulseResponse(
            session_id=payload.session_id,
            pulse_rate=payload.pulse_rate,
            source=payload.source,
            recorded_at=recorded_at,
        )

    except Exception as exc:
        conn.rollback()
        logger.exception("record_pulse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store pulse reading.",
        )
    finally:
        conn.close()


# =====================================================
# BLOOD PRESSURE ENDPOINT
# =====================================================

@router.post("/bp", response_model=BPResponse)
def record_bp(payload: BPRequest):
    """
    Store a blood pressure reading from the BLE BP machine.

    Inserts into SensorData with:
      - data_type = 'bp'
      - bp_systolic, bp_diastolic, pulse_rate (if provided)

    Also computes delta values if a baseline exists for this session
    (inspired by baseline-delta tracking pattern).

    Args:
        payload: BPRequest with session_id, systolic, diastolic, pulse_rate.

    Returns:
        BPResponse confirming the saved reading.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        recorded_at = now_utc()

        cursor.execute(
            """
            INSERT INTO SensorData
                (session_id, bp_systolic, bp_diastolic, pulse_rate, data_type, recorded_at)
            VALUES (?, ?, ?, ?, 'bp', ?)
            """,
            (
                payload.session_id,
                payload.systolic,
                payload.diastolic,
                payload.pulse_rate,
                recorded_at,
            ),
        )
        conn.commit()

        logger.info(
            "BP recorded: session=%d sys=%d dia=%d pulse=%s",
            payload.session_id, payload.systolic, payload.diastolic, payload.pulse_rate,
        )

        return BPResponse(
            session_id=payload.session_id,
            systolic=payload.systolic,
            diastolic=payload.diastolic,
            pulse_rate=payload.pulse_rate,
            recorded_at=recorded_at,
        )

    except Exception as exc:
        conn.rollback()
        logger.exception("record_bp error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not store BP reading.",
        )
    finally:
        conn.close()


# =====================================================
# EMOTION / CAMERA ENDPOINT
# =====================================================

@router.post("/emotion", response_model=EmotionResponse)
def analyze_emotion(payload: EmotionRequest):
    """
    Analyze facial emotion from a base64-encoded webcam frame.

    This is called every 5 seconds while the student/teacher is filling
    the questionnaire. The flow:

      1. Decode base64 string → numpy image array via OpenCV.
      2. Save the image to disk in emotion_images/ folder with a unique name.
      3. Insert a record into EmotionImages table (user_id, session_id, image_name).
      4. Run DeepFace.analyze() with actions=['emotion'], enforce_detection=False.
      5. Extract dominant_emotion and all emotion confidence scores.
      6. Insert into FacialEmotions table (with image_id reference).
      7. Return EmotionResponse with the detected emotion.

    If no face is detected, returns emotion_label='undetected' with confidence=0.

    Args:
        payload: EmotionRequest with session_id, user_id, image_base64.

    Returns:
        EmotionResponse with dominant_emotion, scores, and captured_at.
    """
    # ── 1. Decode base64 image ────────────────────────────
    try:
        img_bytes = base64.b64decode(payload.image_base64)
        np_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            raise ValueError("OpenCV could not decode the image.")
    except Exception as exc:
        logger.warning("Image decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid image data: {exc}",
        )

    # ── 2. Save image to disk ─────────────────────────────
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
        # Continue even if file save fails — DB records are more important

    # ── 3. Insert into EmotionImages table ────────────────
    conn = get_connection()
    image_id = None
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO EmotionImages
                (user_id, session_id, stage_number, image_name, captured_at)
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
        # Continue — we can still do emotion analysis

    # ── 4. Try Custom Model first, fallback to DeepFace ───────────
    dominant_emotion = "undetected"
    emotion_scores = {}
    confidence = 0.0

    # Check if user has trained their own custom model
    custom_model_path = os.path.join(settings.BASE_DIR, "ml", "saved_models", "custom_emotion_model.h5")
    
    if os.path.exists(custom_model_path):
        try:
            import tensorflow as tf
            # Load custom model lazily to avoid heavy import on startup
            custom_model = tf.keras.models.load_model(custom_model_path)
            
            # Use OpenCV Haar Cascade to find the face
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            if len(faces) > 0:
                # Take the largest detected face
                faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
                (x, y, w, h) = faces[0]
                
                # Expand bounding box slightly (often helps FER2013 models)
                pad_w = int(w * 0.1)
                pad_h = int(h * 0.1)
                x1 = max(0, x - pad_w)
                y1 = max(0, y - pad_h)
                x2 = min(gray.shape[1], x + w + pad_w)
                y2 = min(gray.shape[0], y + h + pad_h)
                
                roi_gray = gray[y1:y2, x1:x2]
                roi_gray = cv2.resize(roi_gray, (48, 48))
                roi_gray = roi_gray.astype('float') / 255.0
                roi_gray = np.expand_dims(roi_gray, axis=0)
                roi_gray = np.expand_dims(roi_gray, axis=-1)
                
                # Predict
                preds = custom_model.predict(roi_gray)[0]
                
                # Hardcoded list from the training script
                EMOTIONS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]
                
                for i, prob in enumerate(preds):
                    emotion_scores[EMOTIONS[i]] = float(prob * 100.0)
                    
                confidence = float(np.max(preds) * 100.0)
                
                # Fallback to DeepFace if the custom model isn't very confident
                if confidence > 55.0:
                    dominant_emotion = EMOTIONS[np.argmax(preds)]
                    logger.info("Used Custom Emotion Model: %s (%.1f%%)", dominant_emotion, confidence)
                else:
                    logger.info("Custom model confidence low (%.1f%%). Falling back to DeepFace.", confidence)
                    dominant_emotion = "undetected" # Triggers fallback
            else:
                raise ValueError("No face detected by Haar Cascade")
                
        except Exception as exc:
            logger.warning("Custom model prediction failed: %s. Falling back to DeepFace.", exc)
            # Proceed to DeepFace fallback below
    
    # If custom model didn't run or failed, use DeepFace
    if dominant_emotion == "undetected":
        try:
            analysis = DeepFace.analyze(
                img_path=frame,
                actions=["emotion"],
                enforce_detection=False,
                silent=True,
            )
            result = analysis[0] if isinstance(analysis, list) else analysis
    
            dominant_emotion = result.get("dominant_emotion", "undetected")
            emotion_scores = result.get("emotion", {})
            confidence = emotion_scores.get(dominant_emotion, 0.0)
    
        except Exception as exc:
            logger.error("DeepFace analysis failed for session %d stage %d: %s", payload.session_id, payload.stage_number, exc)
            dominant_emotion = "undetected"
            confidence = 0.0
            emotion_scores = {}

    # ── 5. Insert into FacialEmotions table ───────────────
    try:
        cursor = conn.cursor()

        # Map DeepFace emotion scores to individual columns
        # DeepFace returns percentages 0–100; store as floats
        scores = emotion_scores  # dict: {emotion: score}
        cursor.execute(
            """
            INSERT INTO FacialEmotions
                (session_id, dominant_emotion,
                 happy, sad, angry, fear, surprise, disgust, neutral,
                 captured_at, image_id, stage_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.session_id,
                dominant_emotion,
                scores.get("happy", 0.0),
                scores.get("sad", 0.0),
                scores.get("angry", 0.0),
                scores.get("fear", 0.0),
                scores.get("surprise", 0.0),
                scores.get("disgust", 0.0),
                scores.get("neutral", 0.0),
                captured_at,
                image_id,
                payload.stage_number,
            ),
        )
        conn.commit()

        logger.info(
            "Emotion captured: session=%d dominant=%s image=%s",
            payload.session_id, dominant_emotion, image_name,
        )

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
