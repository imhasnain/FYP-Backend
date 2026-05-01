"""preprocessing/emotion_preprocessor.py — Facial emotion aggregation"""

import logging
from typing import Dict
from collections import Counter

logger = logging.getLogger(__name__)

# Distress severity: 0 = no distress, 1 = maximum
EMOTION_DISTRESS_MAP = {
    "happy":      0.0,
    "neutral":    0.1,
    "surprise":   0.2,
    "disgust":    0.4,
    "fear":       0.7,
    "sad":        0.7,
    "angry":      0.8,
    "undetected": 0.3,
}


def preprocess_emotions(session_id: int, conn) -> Dict[str, object]:
    """
    Aggregate all FacialEmotions for a session.
    Returns: dominant_emotion, emotion_distress_score, emotion_counts.
    """
    defaults = {"dominant_emotion": "undetected", "emotion_distress_score": 0.3, "emotion_counts": {}}

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT dominant_emotion, happy, sad, angry, fear, surprise, disgust, neutral FROM FacialEmotions WHERE session_id = ? ORDER BY captured_at ASC",
            (session_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            logger.info("No emotion data for session %d.", session_id)
            return defaults

        labels = []
        weighted_distress_sum = 0.0
        weight_sum = 0.0

        for row in rows:
            label = (row.dominant_emotion or "undetected").lower()
            labels.append(label)

            dom_score = getattr(row, label, None) or 50.0
            norm_conf = (dom_score / 100.0) if dom_score > 1.0 else dom_score

            distress = EMOTION_DISTRESS_MAP.get(label, 0.3)
            weighted_distress_sum += distress * norm_conf
            weight_sum += norm_conf

        emotion_counts = dict(Counter(labels))
        dominant_emotion = max(emotion_counts, key=emotion_counts.get)
        emotion_distress_score = (
            weighted_distress_sum / weight_sum if weight_sum > 0
            else EMOTION_DISTRESS_MAP.get(dominant_emotion, 0.3)
        )
        emotion_distress_score = round(max(0.0, min(1.0, emotion_distress_score)), 4)

        logger.info(
            "Emotions preprocessed for session %d: dominant=%s distress=%.3f counts=%s",
            session_id, dominant_emotion, emotion_distress_score, emotion_counts,
        )
        return {"dominant_emotion": dominant_emotion, "emotion_distress_score": emotion_distress_score, "emotion_counts": emotion_counts}

    except Exception as exc:
        logger.exception("Emotion preprocessing failed for session %d: %s", session_id, exc)
        return defaults
