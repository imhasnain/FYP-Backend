# ============================================================
# ml/trainer.py — Train student and teacher ML models
#
# Generates synthetic training data using rule-based logic,
# trains a RandomForestClassifier for each role, evaluates,
# and saves the models to ml/saved_models/.
#
# Usage:
#   python -m ml.trainer
#   OR
#   cd backend && python ml/trainer.py
# ============================================================

import os
import sys
import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Label mapping
LABELS = {0: "Normal", 1: "Calm Down", 2: "See Psychologist", 3: "Emergency"}
LABEL_NAMES = list(LABELS.values())

# Output directory for saved models
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_models")

# Feature names (same order as feature_builder.py)
FEATURE_NAMES = [
    "emotional_score",        # 0  (0–4)
    "functional_score",       # 1  (0–4)
    "context_score",          # 2  (0–4)
    "isolation_score",        # 3  (0–4)
    "critical_score",         # 4  (0–4)
    "role_specific_1",        # 5  student: cgpa_trend / teacher: course_load
    "role_specific_2",        # 6  student: attendance_drop / teacher: feedback_trend
    "role_specific_3",        # 7  student: perf_decline / teacher: 0.0
    "eeg_stress_index",       # 8  (0–10+)
    "eeg_alpha_power",        # 9  (0–1)
    "eeg_theta_power",        # 10 (0–1)
    "hr_mean",                # 11 (50–120 bpm)
    "bp_mean_systolic",       # 12 (90–180 mmHg)
    "bp_mean_diastolic",      # 13 (60–120 mmHg)
    "pulse_avg",              # 14 (50–120 bpm)
    "emotion_distress_score", # 15 (0–1)
]


def generate_synthetic_data(role: str, n_samples: int = 5000) -> pd.DataFrame:
    """
    Generate synthetic training data with realistic feature ranges
    and rule-based labels for the given role.

    Generates n_samples total, with approximately equal class distribution
    (at least 1000 per class when n_samples >= 4000).

    The labeling logic mirrors the scoring formula:
      - High questionnaire scores + high stress + high distress → Emergency
      - Moderate values → See Psychologist or Calm Down
      - Low values → Normal

    Args:
        role:      'student' or 'teacher'.
        n_samples: Total number of samples to generate (default 5000).

    Returns:
        DataFrame with 16 feature columns + 'label' column (0–3).
    """
    np.random.seed(42 if role == "student" else 99)
    samples_per_class = n_samples // 4

    all_rows = []

    for target_class in range(4):
        for _ in range(samples_per_class):
            row = _generate_one_sample(role, target_class)
            all_rows.append(row)

    # Add some extra noisy edge cases
    extra = n_samples - (samples_per_class * 4)
    for _ in range(extra):
        target_class = np.random.randint(0, 4)
        row = _generate_one_sample(role, target_class, noisy=True)
        all_rows.append(row)

    df = pd.DataFrame(all_rows, columns=FEATURE_NAMES + ["label"])
    # Shuffle
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    logger.info(
        "Generated %d synthetic samples for role=%s. Class distribution:\n%s",
        len(df), role, df["label"].value_counts().sort_index().to_string(),
    )
    return df


def _generate_one_sample(role: str, target_class: int, noisy: bool = False) -> list:
    """
    Generate a single synthetic sample targeting a specific class.

    Args:
        role:         'student' or 'teacher'.
        target_class: 0 (Normal), 1 (Calm Down), 2 (See Psychologist), 3 (Emergency).
        noisy:        If True, adds more noise to create edge cases.

    Returns:
        List of 17 values (16 features + 1 label).
    """
    noise_scale = 0.5 if noisy else 0.2

    if target_class == 0:  # Normal
        emotional = np.clip(np.random.normal(0.5, 0.3 + noise_scale), 0, 2)
        functional = np.clip(np.random.normal(0.4, 0.3 + noise_scale), 0, 2)
        context = np.clip(np.random.normal(0.5, 0.3 + noise_scale), 0, 2)
        isolation = np.clip(np.random.normal(0.3, 0.3 + noise_scale), 0, 1.5)
        critical = np.clip(np.random.normal(0.1, 0.1), 0, 0.5)
        eeg_stress = np.clip(np.random.normal(0.5, 0.3), 0, 2)
        hr_mean = np.random.normal(72, 8)
        bp_sys = np.random.normal(115, 8)
        bp_dia = np.random.normal(75, 5)
        emotion_distress = np.clip(np.random.normal(0.1, 0.1), 0, 0.3)

    elif target_class == 1:  # Calm Down
        emotional = np.clip(np.random.normal(1.5, 0.4 + noise_scale), 0.5, 3)
        functional = np.clip(np.random.normal(1.2, 0.4 + noise_scale), 0.3, 2.5)
        context = np.clip(np.random.normal(1.3, 0.4 + noise_scale), 0.3, 2.5)
        isolation = np.clip(np.random.normal(1.0, 0.4 + noise_scale), 0.2, 2)
        critical = np.clip(np.random.normal(0.3, 0.2), 0, 1)
        eeg_stress = np.clip(np.random.normal(1.5, 0.5), 0.5, 3)
        hr_mean = np.random.normal(80, 10)
        bp_sys = np.random.normal(125, 10)
        bp_dia = np.random.normal(80, 7)
        emotion_distress = np.clip(np.random.normal(0.3, 0.15), 0.1, 0.5)

    elif target_class == 2:  # See Psychologist
        emotional = np.clip(np.random.normal(2.5, 0.5 + noise_scale), 1.5, 4)
        functional = np.clip(np.random.normal(2.2, 0.5 + noise_scale), 1, 3.5)
        context = np.clip(np.random.normal(2.3, 0.5 + noise_scale), 1, 3.5)
        isolation = np.clip(np.random.normal(2.0, 0.5 + noise_scale), 1, 3)
        critical = np.clip(np.random.normal(1.0, 0.5), 0, 2.5)
        eeg_stress = np.clip(np.random.normal(3.0, 1.0), 1, 6)
        hr_mean = np.random.normal(90, 12)
        bp_sys = np.random.normal(135, 12)
        bp_dia = np.random.normal(88, 8)
        emotion_distress = np.clip(np.random.normal(0.55, 0.15), 0.3, 0.8)

    else:  # Emergency (3)
        emotional = np.clip(np.random.normal(3.5, 0.3 + noise_scale), 2.5, 4)
        functional = np.clip(np.random.normal(3.2, 0.4 + noise_scale), 2, 4)
        context = np.clip(np.random.normal(3.3, 0.4 + noise_scale), 2, 4)
        isolation = np.clip(np.random.normal(3.0, 0.4 + noise_scale), 2, 4)
        critical = np.clip(np.random.normal(3.0, 0.5), 1.5, 4)
        eeg_stress = np.clip(np.random.normal(5.0, 1.5), 3, 10)
        hr_mean = np.random.normal(105, 15)
        bp_sys = np.random.normal(150, 15)
        bp_dia = np.random.normal(95, 10)
        emotion_distress = np.clip(np.random.normal(0.8, 0.1), 0.6, 1.0)

    # Role-specific features
    if role == "student":
        if target_class == 0:
            cgpa_trend = np.random.normal(0.2, 0.3)       # improving
            att_drop = np.clip(np.random.normal(2, 3), 0, 10)
            perf_decline = np.clip(np.random.normal(0.05, 0.05), 0, 0.2)
        elif target_class == 1:
            cgpa_trend = np.random.normal(-0.2, 0.3)
            att_drop = np.clip(np.random.normal(5, 4), 0, 15)
            perf_decline = np.clip(np.random.normal(0.1, 0.1), 0, 0.4)
        elif target_class == 2:
            cgpa_trend = np.random.normal(-0.6, 0.3)
            att_drop = np.clip(np.random.normal(12, 5), 0, 25)
            perf_decline = np.clip(np.random.normal(0.25, 0.15), 0, 0.6)
        else:
            cgpa_trend = np.random.normal(-1.0, 0.3)
            att_drop = np.clip(np.random.normal(20, 7), 5, 40)
            perf_decline = np.clip(np.random.normal(0.5, 0.2), 0.2, 1.0)
        role_f1, role_f2, role_f3 = cgpa_trend, att_drop, perf_decline
    else:  # teacher
        if target_class == 0:
            course_load = np.random.uniform(1, 3)
            feedback = np.random.normal(0.3, 0.3)
        elif target_class == 1:
            course_load = np.random.uniform(2, 4)
            feedback = np.random.normal(-0.1, 0.3)
        elif target_class == 2:
            course_load = np.random.uniform(3, 5)
            feedback = np.random.normal(-0.5, 0.3)
        else:
            course_load = np.random.uniform(4, 6)
            feedback = np.random.normal(-1.0, 0.4)
        role_f1, role_f2, role_f3 = course_load, feedback, 0.0

    # EEG band powers (realistic ranges)
    alpha_power = np.clip(np.random.normal(0.3, 0.15), 0.01, 1.0)
    theta_power = np.clip(np.random.normal(0.2, 0.1), 0.01, 0.8)
    pulse_avg = hr_mean + np.random.normal(0, 3)  # slightly different from hr

    return [
        round(emotional, 3),
        round(functional, 3),
        round(context, 3),
        round(isolation, 3),
        round(critical, 3),
        round(role_f1, 3),
        round(role_f2, 3),
        round(role_f3, 3),
        round(eeg_stress, 3),
        round(alpha_power, 4),
        round(theta_power, 4),
        round(hr_mean, 1),
        round(bp_sys, 1),
        round(bp_dia, 1),
        round(pulse_avg, 1),
        round(emotion_distress, 4),
        target_class,
    ]


def train_model(role: str) -> None:
    """
    Generate synthetic data, train a RandomForestClassifier, evaluate it,
    and save the trained model to disk.

    Args:
        role: 'student' or 'teacher'.
    """
    logger.info("=" * 60)
    logger.info("Training model for role: %s", role.upper())
    logger.info("=" * 60)

    # ── Generate data ────────────────────────────────────────
    df = generate_synthetic_data(role, n_samples=5000)
    X = df[FEATURE_NAMES].values
    y = df["label"].values

    # ── Train/test split ─────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ── Train RandomForestClassifier ─────────────────────────
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    # ── Evaluate ─────────────────────────────────────────────
    metrics = evaluate_model(model, X_test, y_test)
    logger.info("Accuracy: %.4f", metrics["accuracy"])
    logger.info("\nClassification Report:\n%s", metrics["report"])

    # ── Save model ───────────────────────────────────────────
    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, f"model_{role}.pkl")
    joblib.dump(model, model_path)
    logger.info("Model saved to: %s", model_path)


def evaluate_model(model, X_test: np.ndarray, y_test: np.ndarray) -> dict:
    """
    Evaluate a trained model on the test set.

    Args:
        model:  Trained sklearn classifier.
        X_test: Test feature matrix.
        y_test: True labels.

    Returns:
        Dict with 'accuracy' (float) and 'report' (str classification report).
    """
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(
        y_test, y_pred,
        target_names=LABEL_NAMES,
        digits=3,
    )
    return {"accuracy": acc, "report": report}


def retrain_from_db(role: str, conn) -> None:
    """
    Retrain a model using real labelled data from the MH_Results table.

    This function is intended for use after enough real session data
    has accumulated. It loads features and labels from MH_Results,
    trains a new model, and overwrites the saved model file.

    Args:
        role: 'student' or 'teacher'.
        conn: An open pyodbc connection.
    """
    logger.info("Retraining %s model from database...", role)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            emotional_score, functional_score, context_score,
            isolation_score, critical_score, performance_score,
            eeg_stress_index, eeg_alpha_power, eeg_theta_power,
            hr_mean, bp_avg_systolic, bp_avg_diastolic, pulse_avg,
            emotion_distress_score, recommendation
        FROM MH_Results
        WHERE user_role = ?
          AND recommendation IS NOT NULL
        """,
        (role,),
    )
    rows = cursor.fetchall()

    if len(rows) < 100:
        logger.warning(
            "Only %d labelled samples for role=%s. Need at least 100. Skipping retrain.",
            len(rows), role,
        )
        return

    # Build DataFrame
    reverse_labels = {v: k for k, v in LABELS.items()}
    data_rows = []
    for r in rows:
        label = reverse_labels.get(r.recommendation, 0)
        data_rows.append([
            r.emotional_score or 0, r.functional_score or 0,
            r.context_score or 0, r.isolation_score or 0,
            r.critical_score or 0, 0.0, 0.0,
            r.performance_score or 0,
            r.eeg_stress_index or 0, r.eeg_alpha_power or 0,
            r.eeg_theta_power or 0, r.hr_mean or 0,
            r.bp_avg_systolic or 0, r.bp_avg_diastolic or 0,
            r.pulse_avg or 0, r.emotion_distress_score or 0,
            label,
        ])

    df = pd.DataFrame(data_rows, columns=FEATURE_NAMES + ["label"])
    X = df[FEATURE_NAMES].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
    )

    model = RandomForestClassifier(
        n_estimators=200, max_depth=15, random_state=42, n_jobs=-1,
    )
    model.fit(X_train, y_train)

    metrics = evaluate_model(model, X_test, y_test)
    logger.info("Retrained %s model — Accuracy: %.4f", role, metrics["accuracy"])

    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, f"model_{role}.pkl")
    joblib.dump(model, model_path)
    logger.info("Retrained model saved to: %s", model_path)


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    train_model("student")
    print()
    train_model("teacher")
    print()
    print("=" * 60)
    print("Both models trained and saved successfully.")
    print(f"Model directory: {MODELS_DIR}")
    print("=" * 60)
