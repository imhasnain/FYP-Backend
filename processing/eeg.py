"""processing/eeg.py — EEG signal preprocessing and stress index calculation."""

import logging
import numpy as np
from scipy.signal import butter, sosfilt

logger = logging.getLogger(__name__)

EEG_SAMPLE_RATE = 256.0  # Muse headset sampling rate (Hz)


def bandpass_filter(data: np.ndarray, lowcut: float, highcut: float,
                    fs: float = EEG_SAMPLE_RATE, order: int = 4) -> np.ndarray:
    """Apply a Butterworth bandpass filter to a 1-D EEG signal."""
    nyquist = 0.5 * fs
    sos = butter(order, [lowcut / nyquist, highcut / nyquist], btype="band", output="sos")
    return sosfilt(sos, data)


def compute_band_power(signal: np.ndarray, fs: float, low: float, high: float) -> float:
    """Compute mean spectral power in a frequency band via FFT."""
    if len(signal) == 0:
        return 0.0
    n = len(signal)
    fft_power = np.abs(np.fft.rfft(signal)) ** 2 / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    band_mask = (freqs >= low) & (freqs <= high)
    band = fft_power[band_mask]
    return float(np.mean(band)) if len(band) > 0 else 0.0


def preprocess_eeg(session_id: int, conn) -> dict:
    """
    Load EEG from EEG_Snapshots (real-time stream summaries) or fallback to SensorData.

    Returns:
        {alpha_power, beta_power, theta_power, stress_index, eeg_score}
    """
    zeros = {"alpha_power": 0.0, "beta_power": 0.0, "theta_power": 0.0,
             "stress_index": 0.0, "eeg_score": 0.0}
    try:
        cursor = conn.cursor()
        # 1. Try EEG_Snapshots first (real-time acquisition stream)
        cursor.execute(
            "SELECT AVG(alpha_power), AVG(beta_power), AVG(theta_power), AVG(stress_index) "
            "FROM EEG_Snapshots WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        if row and row[0] is not None and row[0] > 0:
            alpha = float(row[0])
            beta = float(row[1])
            theta = float(row[2])
            stress_index = float(row[3])
            eeg_score = min(4.0, stress_index * 0.8)
            logger.info("EEG session %d from EEG_Snapshots: alpha=%.4f beta=%.4f theta=%.4f stress=%.4f",
                        session_id, alpha, beta, theta, stress_index)
            return {"alpha_power": round(alpha, 6), "beta_power": round(beta, 6),
                    "theta_power": round(theta, 6), "stress_index": round(stress_index, 4),
                    "eeg_score": round(eeg_score, 4)}

        # 2. Fallback to raw SensorData filtering
        cursor.execute(
            "SELECT eeg_value FROM SensorData "
            "WHERE session_id = ? AND data_type = 'eeg' AND eeg_value IS NOT NULL "
            "ORDER BY recorded_at ASC", (session_id,)
        )
        rows = cursor.fetchall()
        if not rows or len(rows) < 10:
            logger.info("Not enough EEG data for session %d (%d rows).", session_id, len(rows) if rows else 0)
            return zeros

        raw = np.array([float(r[0]) for r in rows], dtype=np.float64)
        filtered = bandpass_filter(raw, lowcut=1.0, highcut=40.0)

        alpha = compute_band_power(filtered, EEG_SAMPLE_RATE, 8.0, 13.0)
        beta = compute_band_power(filtered, EEG_SAMPLE_RATE, 13.0, 30.0)
        theta = compute_band_power(filtered, EEG_SAMPLE_RATE, 4.0, 8.0)

        stress_index = (beta + theta) / (alpha + 1e-6)
        eeg_score = min(4.0, stress_index * 0.8)

        logger.info("EEG session %d from SensorData: alpha=%.4f beta=%.4f theta=%.4f stress=%.4f",
                    session_id, alpha, beta, theta, stress_index)
        return {"alpha_power": round(alpha, 6), "beta_power": round(beta, 6),
                "theta_power": round(theta, 6), "stress_index": round(stress_index, 4),
                "eeg_score": round(eeg_score, 4)}
    except Exception as exc:
        logger.exception("EEG preprocessing failed for session %d: %s", session_id, exc)
        return zeros
