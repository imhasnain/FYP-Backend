"""processing/emotions.py — Facial emotion aggregation and distress scoring."""

import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Distress map: 0.0 = no distress, 1.0 = maximum distress
DISTRESS_MAP = {
    "happy": 0.0, "neutral": 0.1, "surprise": 0.2,
    "disgust": 0.5, "sad": 0.7, "fear": 0.8,
    "angry": 0.8, "undetected": 0.3,
}


def preprocess_emotions(session_id: int, conn) -> dict:
    """
    Aggregate all FacialEmotions for a session.

    Returns:
        {dominant_emotion, face_distress, face_score}
        face_distress = mean of DISTRESS_MAP values across all captures
        face_score = face_distress * 4   (normalized to 0-4 scale)
    """
    defaults = {"dominant_emotion": "neutral", "face_distress": 0.1, "face_score": 0.4}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT dominant_emotion FROM FacialEmotions "
            "WHERE session_id = ? ORDER BY captured_at ASC", (session_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            logger.info("No emotion data for session %d.", session_id)
            return defaults

        labels = [(r.dominant_emotion or "neutral").lower() for r in rows]
        # Filter out 'undetected' if any actual emotion was detected
        valid_labels = [l for l in labels if l != "undetected"]
        if not valid_labels:
            valid_labels = ["neutral"]

        distress_values = [DISTRESS_MAP.get(lbl, 0.1) for lbl in valid_labels]
        face_distress = sum(distress_values) / len(distress_values)

        counts = Counter(valid_labels)
        dominant = max(counts, key=counts.get)
        face_score = face_distress * 4.0

        logger.info("Emotions session %d: dominant=%s distress=%.3f", session_id, dominant, face_distress)
        return {"dominant_emotion": dominant,
                "face_distress": round(face_distress, 4),
                "face_score": round(face_score, 4)}
    except Exception as exc:
        logger.exception("Emotion preprocessing failed for session %d: %s", session_id, exc)
        return defaults
