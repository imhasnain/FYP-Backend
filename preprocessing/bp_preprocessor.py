# ============================================================
# preprocessing/bp_preprocessor.py — Blood Pressure preprocessing
#
# Aggregates all BP and pulse readings for a session into mean
# values and flags hypertension.
# ============================================================

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def preprocess_bp(session_id: int, conn) -> Dict[str, Optional[float]]:
    """
    Load all BP readings for a session and compute summary statistics.

    Steps:
      1. Query SensorData for rows with data_type='bp'.
      2. Compute mean systolic, mean diastolic, mean pulse.
      3. Flag hypertension if mean systolic > 140 OR mean diastolic > 90.

    Args:
        session_id: The session to process.
        conn:       An open pyodbc connection.

    Returns:
        Dict with keys: mean_systolic, mean_diastolic, mean_pulse,
        hypertension_flag (0 or 1).
        Returns None values if no BP readings are available.
    """
    empty = {
        "mean_systolic": None,
        "mean_diastolic": None,
        "mean_pulse": None,
        "hypertension_flag": 0,
    }

    try:
        cursor = conn.cursor()

        # ── BP readings ──────────────────────────────────────
        cursor.execute(
            """
            SELECT
                AVG(CAST(bp_systolic AS FLOAT))  AS avg_sys,
                AVG(CAST(bp_diastolic AS FLOAT)) AS avg_dia,
                COUNT(*) AS cnt
            FROM SensorData
            WHERE session_id = ?
              AND data_type = 'bp'
              AND bp_systolic IS NOT NULL
            """,
            (session_id,),
        )
        bp_row = cursor.fetchone()

        if not bp_row or bp_row.cnt == 0:
            logger.info("No BP data for session %d.", session_id)
            # Still try to get pulse data from other sources
            pulse_avg = _get_pulse_avg(session_id, cursor)
            if pulse_avg is not None:
                empty["mean_pulse"] = round(pulse_avg, 1)
            return empty

        mean_sys = float(bp_row.avg_sys) if bp_row.avg_sys is not None else None
        mean_dia = float(bp_row.avg_dia) if bp_row.avg_dia is not None else None

        # ── Pulse average (from BP rows + standalone pulse rows) ──
        pulse_avg = _get_pulse_avg(session_id, cursor)

        # ── Hypertension flag ────────────────────────────────
        hypertension = 0
        if mean_sys is not None and mean_sys > 140:
            hypertension = 1
        if mean_dia is not None and mean_dia > 90:
            hypertension = 1

        result = {
            "mean_systolic": round(mean_sys, 1) if mean_sys else None,
            "mean_diastolic": round(mean_dia, 1) if mean_dia else None,
            "mean_pulse": round(pulse_avg, 1) if pulse_avg else None,
            "hypertension_flag": hypertension,
        }

        logger.info(
            "BP preprocessed for session %d: sys=%.1f dia=%.1f pulse=%s hyper=%d",
            session_id,
            mean_sys or 0,
            mean_dia or 0,
            pulse_avg,
            hypertension,
        )
        return result

    except Exception as exc:
        logger.exception("BP preprocessing failed for session %d: %s", session_id, exc)
        return empty


def _get_pulse_avg(session_id: int, cursor) -> Optional[float]:
    """
    Compute average pulse rate across all sensor data sources
    (BP cuff pulse + standalone pulse readings + PPG).

    Args:
        session_id: The session to query.
        cursor:     An open pyodbc cursor.

    Returns:
        Average pulse rate as float, or None if no pulse data exists.
    """
    cursor.execute(
        """
        SELECT AVG(CAST(pulse_rate AS FLOAT)) AS avg_pulse
        FROM SensorData
        WHERE session_id = ?
          AND pulse_rate IS NOT NULL
          AND pulse_rate > 0
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    if row and row.avg_pulse is not None:
        return float(row.avg_pulse)
    return None
