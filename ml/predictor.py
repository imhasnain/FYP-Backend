"""ml/predictor.py — Load saved models and make predictions"""

import os
import logging
from typing import Dict, List

import joblib
import numpy as np

logger = logging.getLogger(__name__)

_models: Dict[str, object] = {}
_models_loaded: bool = False

LABEL_MAP = {0: "Normal", 1: "Calm Down", 2: "See Psychologist", 3: "Emergency"}
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "saved_models")


def load_models() -> None:
    """Load student and teacher ML models from disk. Called once at startup."""
    global _models, _models_loaded

    for role in ("student", "teacher"):
        model_path = os.path.join(_MODELS_DIR, f"model_{role}.pkl")
        if not os.path.exists(model_path):
            logger.warning("Model file not found: %s. Run 'python -m ml.trainer'.", model_path)
            continue
        _models[role] = joblib.load(model_path)
        logger.info("Loaded ML model for %s from %s", role, model_path)

    _models_loaded = len(_models) > 0
    if _models_loaded:
        logger.info("ML models loaded successfully. Roles available: %s", list(_models.keys()))
    else:
        logger.warning("No ML models loaded. Predictions will use rule-based fallback.")


def models_loaded() -> bool:
    return _models_loaded


def predict(features: List[float], role: str) -> Dict[str, object]:
    """
    Make a prediction using the trained model for the given role.
    Falls back to rule-based scoring if model is not loaded.

    Returns dict: { recommendation, confidence, class_probabilities }
    """
    model = _models.get(role)
    if model is None:
        logger.warning("No model for role '%s'. Using rule-based fallback.", role)
        return _rule_based_fallback(features)

    try:
        X = np.array(features).reshape(1, -1)
        prediction = int(model.predict(X)[0])
        probabilities = model.predict_proba(X)[0]

        recommendation = LABEL_MAP.get(prediction, "Normal")
        confidence = float(np.max(probabilities))
        class_probs = {LABEL_MAP.get(i, f"Class_{i}"): round(float(p), 4) for i, p in enumerate(probabilities)}

        logger.info("Prediction for role=%s: %s (confidence=%.2f%%)", role, recommendation, confidence * 100)
        return {"recommendation": recommendation, "confidence": round(confidence, 4), "class_probabilities": class_probs}

    except Exception as exc:
        logger.exception("ML prediction failed: %s. Falling back to rules.", exc)
        return _rule_based_fallback(features)


def _rule_based_fallback(features: List[float]) -> Dict[str, object]:
    """Simple weighted fallback when no ML model is available."""
    from scoring.questionnaire_scorer import score_to_recommendation

    q_score = 0.0
    if len(features) >= 5:
        q_score = 0.30 * features[0] + 0.25 * features[1] + 0.15 * features[2] + 0.20 * features[3] + 0.10 * features[4]
    if len(features) >= 16:
        q_score = min(4.0, q_score + features[15] * 0.5)

    recommendation = score_to_recommendation(q_score)
    class_probs = {"Normal": 0.0, "Calm Down": 0.0, "See Psychologist": 0.0, "Emergency": 0.0}
    class_probs[recommendation] = 0.60

    return {"recommendation": recommendation, "confidence": 0.60, "class_probabilities": class_probs}
