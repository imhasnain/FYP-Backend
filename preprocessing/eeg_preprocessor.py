# ============================================================
# preprocessing/eeg_preprocessor.py — EEG signal preprocessing
#
# Loads raw EEG data from SensorData, applies bandpass filtering,
# extracts frequency band powers (delta, theta, alpha, beta),
# and computes a stress index.
# ============================================================

import logging
from typing import Dict

import numpy as np
from scipy.signal import butter, sosfilt

logger = logging.getLogger(__name__)

# Muse headset EEG sampling rate (Hz)
EEG_SAMPLE_RATE = 256.0


def bandpass_filter(
    data: np.ndarray,
    lowcut: float,
    highcut: float,
    fs: float = EEG_SAMPLE_RATE,
    order: int = 4,
) -> np.ndarray:
    """
    Apply a Butterworth bandpass filter to an EEG signal.

    Args:
        data:    1-D numpy array of EEG samples.
        lowcut:  Lower frequency bound in Hz.
        highcut: Upper frequency bound in Hz.
        fs:      Sampling frequency in Hz (default 256 for Muse).
        order:   Filter order (default 4).

    Returns:
        Filtered signal as a 1-D numpy array of the same length.
    """
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    sos = butter(order, [low, high], btype="band", output="sos")
    return sosfilt(sos, data)


def compute_band_power(
    signal: np.ndarray, fs: float, low: float, high: float
) -> float:
    """
    Compute the mean power in a specific frequency band using FFT.

    Args:
        signal: 1-D numpy array of filtered EEG samples.
        fs:     Sampling frequency in Hz.
        low:    Lower bound of the frequency band in Hz.
        high:   Upper bound of the frequency band in Hz.

    Returns:
        Mean power (float) in the specified frequency band.
        Returns 0.0 if the signal is empty or the band has no bins.
    """
    if len(signal) == 0:
        return 0.0

    n = len(signal)
    fft_vals = np.fft.rfft(signal)
    fft_power = np.abs(fft_vals) ** 2 / n
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)

    # Select frequency bins within the band
    band_mask = (freqs >= low) & (freqs <= high)
    band_power = fft_power[band_mask]

    if len(band_power) == 0:
        return 0.0

    return float(np.mean(band_power))


def preprocess_eeg(session_id: int, conn) -> Dict[str, float]:
    """
    Load raw EEG data for a session, filter it, extract frequency band
    powers, and compute a stress index.

    Processing pipeline:
      1. Query SensorData for all EEG readings ordered by recorded_at.
      2. Apply a 1–40 Hz Butterworth bandpass filter.
      3. Compute power spectral density via FFT.
      4. Extract band powers: delta (1–4), theta (4–8), alpha (8–13), beta (13–30).
      5. Stress index = (beta + theta) / alpha  (higher = more stress).

    Args:
        session_id: The session to process.
        conn:       An open pyodbc connection.

    Returns:
        Dict with keys: alpha_power, theta_power, beta_power,
        delta_power, stress_index.  All zeros if no EEG data exists.
    """
    zeros = {
        "alpha_power": 0.0,
        "theta_power": 0.0,
        "beta_power": 0.0,
        "delta_power": 0.0,
        "stress_index": 0.0,
    }

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT eeg_value
            FROM SensorData
            WHERE session_id = ?
              AND data_type = 'eeg'
              AND eeg_value IS NOT NULL
            ORDER BY recorded_at ASC
            """,
            (session_id,),
        )
        rows = cursor.fetchall()

        if not rows or len(rows) < 10:
            logger.info(
                "Not enough EEG data for session %d (%d rows). Returning zeros.",
                session_id,
                len(rows) if rows else 0,
            )
            return zeros

        # Build signal array
        raw_signal = np.array([float(r[0]) for r in rows], dtype=np.float64)

        # Step 2: Bandpass filter 1–40 Hz
        filtered = bandpass_filter(raw_signal, lowcut=1.0, highcut=40.0)

        # Steps 3–4: Extract band powers
        delta_power = compute_band_power(filtered, EEG_SAMPLE_RATE, 1.0, 4.0)
        theta_power = compute_band_power(filtered, EEG_SAMPLE_RATE, 4.0, 8.0)
        alpha_power = compute_band_power(filtered, EEG_SAMPLE_RATE, 8.0, 13.0)
        beta_power = compute_band_power(filtered, EEG_SAMPLE_RATE, 13.0, 30.0)

        # Step 5: Stress index
        if alpha_power > 0:
            stress_index = (beta_power + theta_power) / alpha_power
        else:
            stress_index = 0.0

        logger.info(
            "EEG preprocessed for session %d: alpha=%.4f theta=%.4f "
            "beta=%.4f delta=%.4f stress=%.4f",
            session_id,
            alpha_power,
            theta_power,
            beta_power,
            delta_power,
            stress_index,
        )

        return {
            "alpha_power": round(alpha_power, 6),
            "theta_power": round(theta_power, 6),
            "beta_power": round(beta_power, 6),
            "delta_power": round(delta_power, 6),
            "stress_index": round(stress_index, 4),
        }

    except Exception as exc:
        logger.exception("EEG preprocessing failed for session %d: %s", session_id, exc)
        return zeros
