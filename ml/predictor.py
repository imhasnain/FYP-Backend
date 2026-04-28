# ============================================================
# ml/predictor.py — Load saved models and make predictions
#
# Models are loaded once at startup via load_models() and cached
# in module-level variables. predict() uses the cached models.
# ============================================================

import os
import logging
from typing import Dict, List, Optional

import joblib
import numpy as np

logger = logging.getLogger(__name__)

# ── Module-level model cache ─────────────────────────────────
_models: Dict[str, object] = {}
_models_loaded: bool = False

# Label mapping: index → recommendation string
LABEL_MAP = {
    0: "Normal",
    1: "Calm Down",
    2: "See Psychologist",
    3: "Emergency",
}

# Path to saved models directory
_MODELS_DIR = os.path.join(os.path.dirname(__file__), "saved_models")


def load_models() -> None:
    """
    Load both student and teacher ML models from disk into memory.

    Must be called once at application startup (e.g., in main.py lifespan).
    Models are saved as .pkl files by ml/trainer.py.

    Raises:
        FileNotFoundError: If a model file is missing. Includes a helpful
        message telling the user to run trainer.py first.
    """
    global _models, _models_loaded

    for role in ("student", "teacher"):
        model_path = os.path.join(_MODELS_DIR, f"model_{role}.pkl")
        if not os.path.exists(model_path):
            logger.warning(
                "Model file not found: %s. Run 'python -m ml.trainer' to train models.",
                model_path,
            )
            continue

        _models[role] = joblib.load(model_path)
        logger.info("Loaded ML model for %s from %s", role, model_path)

    _models_loaded = len(_models) > 0
    if _models_loaded:
        logger.info("ML models loaded successfully. Roles available: %s", list(_models.keys()))
    else:
        logger.warning(
            "No ML models loaded. Predictions will use rule-based fallback. "
            "Run 'python -m ml.trainer' to generate models."
        )


def models_loaded() -> bool:
    """
    Check if at least one ML model has been loaded.

    Returns:
        True if load_models() successfully loaded at least one model.
    """
    return _models_loaded


def predict(features: List[float], role: str) -> Dict[str, object]:
    """
    Make a mental health recommendation prediction using the trained model.

    Args:
        features: List of 16 floats — the feature vector built by feature_builder.
        role:     'student' or 'teacher' — selects which model to use.

    Returns:
        Dict with keys:
          - recommendation (str): 'Normal' | 'Calm Down' | 'See Psychologist' | 'Emergency'
          - confidence (float):   Highest class probability 0.0–1.0.
          - class_probabilities (dict): { label_name: probability } for all 4 classes.

    Falls back to rule-based scoring if the model for this role is not loaded.
    """
    model = _models.get(role)

    if model is None:
        logger.warning(
            "No model for role '%s'. Using rule-based fallback.", role
        )
        return _rule_based_fallback(features)

    try:
        X = np.array(features).reshape(1, -1)
        prediction = int(model.predict(X)[0])
        probabilities = model.predict_proba(X)[0]

        recommendation = LABEL_MAP.get(prediction, "Normal")
        confidence = float(np.max(probabilities))

        class_probs = {}
        for idx, prob in enumerate(probabilities):
            label = LABEL_MAP.get(idx, f"Class_{idx}")
            class_probs[label] = round(float(prob), 4)

        logger.info(
            "Prediction for role=%s: %s (confidence=%.2f%%)",
            role, recommendation, confidence * 100,
        )

        return {
            "recommendation": recommendation,
            "confidence": round(confidence, 4),
            "class_probabilities": class_probs,
        }

    except Exception as exc:
        logger.exception("ML prediction failed: %s. Falling back to rules.", exc)
        return _rule_based_fallback(features)


def _rule_based_fallback(features: List[float]) -> Dict[str, object]:
    """
    Rule-based fallback when ML model is not available.

    Uses a simple weighted average of the questionnaire scores (indices 0–4)
    to produce a score in [0, 4], then maps to a recommendation.

    Args:
        features: The 16-element feature vector.

    Returns:
        Dict with recommendation, confidence, and class_probabilities.
    """
    from scoring.questionnaire_scorer import score_to_recommendation

    # Weighted average of questionnaire scores
    if len(features) >= 5:
        q_score = (
            0.30 * features[0]
            + 0.25 * features[1]
            + 0.15 * features[2]
            + 0.20 * features[3]
            + 0.10 * features[4]
        )
    else:
        q_score = 0.0

    # Factor in emotion distress if available
    if len(features) >= 16:
        emotion_factor = features[15] * 0.5  # 0–0.5 addition
        q_score = min(4.0, q_score + emotion_factor)

    recommendation = score_to_recommendation(q_score)
    confidence = 0.60  # Fixed low confidence for rule-based

    class_probs = {
        "Normal": 0.0,
        "Calm Down": 0.0,
        "See Psychologist": 0.0,
        "Emergency": 0.0,
    }
    class_probs[recommendation] = confidence

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "class_probabilities": class_probs,
    }
