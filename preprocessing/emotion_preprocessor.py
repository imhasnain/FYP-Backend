# ============================================================
# preprocessing/emotion_preprocessor.py — Facial emotion aggregation
#
# Loads all FacialEmotions records for a session, finds the
# dominant emotion, and computes an emotion distress score.
# ============================================================

import logging
from typing import Dict, Optional
from collections import Counter

logger = logging.getLogger(__name__)

# Maps each emotion label to a distress severity score (0 = no distress, 1 = max)
EMOTION_DISTRESS_MAP = {
    "happy": 0.0,
    "neutral": 0.1,
    "surprise": 0.2,
    "disgust": 0.4,
    "fear": 0.7,
    "sad": 0.7,
    "angry": 0.8,
    "undetected": 0.3,
}


def preprocess_emotions(session_id: int, conn) -> Dict[str, object]:
    """
    Load all FacialEmotions records for a session and compute
    aggregated emotion metrics.

    Steps:
      1. Query FacialEmotions for all rows matching session_id.
      2. Count frequency of each emotion label.
      3. Find dominant emotion (most frequent label).
      4. Compute emotion_distress_score as a confidence-weighted
         average of EMOTION_DISTRESS_MAP values across all readings.

    Args:
        session_id: The session to process.
        conn:       An open pyodbc connection.

    Returns:
        Dict with keys:
          - dominant_emotion (str): Most frequent emotion label.
          - emotion_distress_score (float): Weighted distress score 0.0–1.0.
          - emotion_counts (dict): Frequency of each emotion label.
        Returns defaults if no emotion data exists.
    """
    defaults = {
        "dominant_emotion": "undetected",
        "emotion_distress_score": 0.3,
        "emotion_counts": {},
    }

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT emotion_label, confidence
            FROM FacialEmotions
            WHERE session_id = ?
            ORDER BY captured_at ASC
            """,
            (session_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            logger.info("No emotion data for session %d.", session_id)
            return defaults

        # ── Count each emotion label ─────────────────────────
        labels = []
        weighted_distress_sum = 0.0
        weight_sum = 0.0

        for row in rows:
            label = (row.emotion_label or "undetected").lower()
            confidence = float(row.confidence) if row.confidence is not None else 50.0

            labels.append(label)

            # Weight the distress score by the detection confidence
            distress = EMOTION_DISTRESS_MAP.get(label, 0.3)
            # Confidence from DeepFace is 0–100, normalize to 0–1
            norm_conf = confidence / 100.0 if confidence > 1.0 else confidence
            weighted_distress_sum += distress * norm_conf
            weight_sum += norm_conf

        emotion_counts = dict(Counter(labels))

        # ── Dominant emotion (most frequent) ─────────────────
        dominant_emotion = Counter(labels).most_common(1)[0][0]

        # ── Weighted distress score ──────────────────────────
        if weight_sum > 0:
            emotion_distress_score = weighted_distress_sum / weight_sum
        else:
            emotion_distress_score = EMOTION_DISTRESS_MAP.get(dominant_emotion, 0.3)

        # Clamp to [0, 1]
        emotion_distress_score = max(0.0, min(1.0, emotion_distress_score))

        logger.info(
            "Emotions preprocessed for session %d: dominant=%s distress=%.3f counts=%s",
            session_id,
            dominant_emotion,
            emotion_distress_score,
            emotion_counts,
        )

        return {
            "dominant_emotion": dominant_emotion,
            "emotion_distress_score": round(emotion_distress_score, 4),
            "emotion_counts": emotion_counts,
        }

    except Exception as exc:
        logger.exception(
            "Emotion preprocessing failed for session %d: %s", session_id, exc
        )
        return defaults
