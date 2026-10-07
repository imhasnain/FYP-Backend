"""hardware/eeg_stream.py — Strictly REAL Muse EEG & PPG streaming via BlueMuse + pylsl.

RAW DATA PIPELINE (what exactly happens to each sample):
  1. BlueMuse streams raw Muse 2 EEG in microvolts (µV). Typical good values: -100 to +100 µV.
  2. We collect AF7 + AF8 frontal channels and average them every 2 seconds (512 samples).
  3. Artifact Rejection: samples where |value| > 150 µV are dropped (eye blinks, jaw clenches).
  4. Butterworth bandpass filter (1–40 Hz, 4th order) removes DC drift and high-freq muscle noise.
  5. FFT converts the filtered signal to the frequency domain and we extract mean power per band:
       Alpha (8–13 Hz) → Relaxation
       Beta  (13–30 Hz) → Stress / active thinking
       Theta (4–8 Hz)   → Fatigue / deep focus
  6. Stress Index = (Beta + Theta) / Alpha
  7. Snapshot saved to EEG_Snapshots every 2 seconds, tagged with current question number.
  8. WebSocket broadcasts live values to the Flutter app every 2 seconds.
  9. PPG (IR optical channel) → peak detection → real Heart Rate BPM → saved to SensorData.
"""

import threading
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from scipy.signal import butter, sosfilt, find_peaks

logger = logging.getLogger(__name__)

# ── EEG & PPG constants ───────────────────────────────────────────────────
SAMPLE_RATE   = 256.0     # Muse 2 EEG Hz
PPG_RATE      = 64.0      # Muse 2 PPG Hz
BUFFER_SIZE   = int(SAMPLE_RATE * 2)   # 2-second window = 512 samples
SNAPSHOT_SEC  = 2.0       # process + save every 2 seconds

# Frontal channels: AF7=1, AF8=2 (0-indexed in Muse LSL stream)
FRONTAL_CHANNELS = [1, 2]

# Artifact rejection threshold in µV — values outside ±150 µV are blink/jaw artifacts
ARTIFACT_THRESHOLD = 150.0

# Frequency bands in Hz
BANDS = {
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta":  (13.0, 30.0),
}


# ── Signal processing ─────────────────────────────────────────────────────

def _bandpass(data: np.ndarray, low: float, high: float, fs: float) -> np.ndarray:
    """Butterworth bandpass filter using second-order sections for numerical stability."""
    nyq = fs / 2.0
    sos = butter(4, [low / nyq, high / nyq], btype="band", output="sos")
    return sosfilt(sos, data)


def _band_power(signal: np.ndarray, low: float, high: float) -> float:
    """
    Mean spectral power in a frequency band via FFT.
    Result is in µV² (microvolts squared) — typical values: 1–50 µV² for clean EEG.
    """
    n = len(signal)
    if n < 8:
        return 0.0
    # FFT power spectrum
    fft_vals = np.fft.rfft(signal)
    power = (np.abs(fft_vals) ** 2) / n          # power spectral density
    freqs = np.fft.rfftfreq(n, d=1.0 / SAMPLE_RATE)
    mask = (freqs >= low) & (freqs <= high)
    return float(np.mean(power[mask])) if mask.any() else 0.0


def _reject_artifacts(raw: np.ndarray) -> np.ndarray:
    """
    Remove samples exceeding ±ARTIFACT_THRESHOLD µV.
    These are caused by eye blinks, jaw clenches, or electrode disconnections.
    Returns cleaned array; if > 50% bad, returns empty array (not enough data).
    """
    mask = np.abs(raw) <= ARTIFACT_THRESHOLD
    clean = raw[mask]
    if len(clean) < len(raw) * 0.5:
        logger.warning("EEG: >50%% samples are artifacts — headset may not be worn correctly.")
        return np.array([])
    return clean


def _process_eeg(raw: np.ndarray) -> Optional[dict]:
    """
    Full EEG pipeline: artifact rejection → bandpass filter → FFT band powers → stress index.
    Returns None if not enough clean data.
    """
    # Step 1: reject blink/jaw artifacts
    clean = _reject_artifacts(raw)
    if len(clean) < 64:    # need at least 0.25 seconds of data
        return None

    # Step 2: bandpass filter (1–40 Hz)
    filtered = _bandpass(clean, 1.0, 40.0, fs=SAMPLE_RATE)

    # Step 3: extract band powers
    theta = _band_power(filtered, *BANDS["theta"])
    alpha = _band_power(filtered, *BANDS["alpha"])
    beta  = _band_power(filtered, *BANDS["beta"])

    # Step 4: stress index
    stress_index = (beta + theta) / (alpha + 1e-6)

    return {
        "alpha":        round(alpha, 4),
        "beta":         round(beta, 4),
        "theta":        round(theta, 4),
        "stress_index": round(min(stress_index, 20.0), 4),   # cap at 20 for display
    }


def _extract_pulse(ppg_ir: np.ndarray) -> int:
    """
    Extract heart rate (BPM) from Muse PPG IR optical channel.
    Bandpass 0.8–3.5 Hz (48–210 BPM), then count peaks.
    """
    try:
        if len(ppg_ir) < 64:
            return 72
        filtered = _bandpass(ppg_ir, 0.8, 3.5, fs=PPG_RATE)
        peaks, _ = find_peaks(filtered, distance=int(PPG_RATE * 0.4))
        if len(peaks) >= 2:
            intervals = np.diff(peaks) / PPG_RATE
            bpm = int(round(60.0 / float(np.mean(intervals))))
            return max(45, min(180, bpm))
    except Exception:
        pass
    return 72


# ── EEGStream class ───────────────────────────────────────────────────────

class EEGStream:
    """
    Manages live Muse EEG & PPG acquisition for one session.
    No simulation — hardware only.
    """

    def __init__(self, session_id: int, db_conn):
        self.session_id     = session_id
        self._conn          = db_conn
        self._thread        = None
        self._stop_event    = threading.Event()
        self._lock          = threading.Lock()
        self._current_q_id  = None
        self._current_q_num = None

        # Live values read by WebSocket handler and Flutter app
        self.latest: dict = {
            "connected":    False,
            "alpha":        0.0,
            "beta":         0.0,
            "theta":        0.0,
            "stress_index": 0.0,
            "pulse_rate":   72,
            "question_id":  None,
            "question_num": None,
        }

    def set_question(self, question_id: int, question_num: int):
        with self._lock:
            self._current_q_id  = question_id
            self._current_q_num = question_num
        logger.info("EEG marker set: session=%d q_id=%d q_num=%d",
                    self.session_id, question_id, question_num)

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("EEG stream thread started for session %d", self.session_id)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("EEG stream stopped for session %d", self.session_id)

    def _run(self):
        try:
            from pylsl import StreamInlet, resolve_streams
        except ImportError:
            logger.error("pylsl not installed. Run: pip install pylsl")
            return

        logger.info("Resolving real Muse LSL streams (EEG + PPG)...")
        all_streams = resolve_streams(wait_time=5.0)

        eeg_inlet = None
        ppg_inlet = None

        for s in all_streams:
            stype = s.type().upper()
            sname = s.name().upper()
            logger.info("Discovered LSL stream: name='%s' type='%s'", s.name(), s.type())
            if (stype == "EEG" or ("EEG" in sname and "GYRO" not in sname and "ACCEL" not in sname and "TELEMETRY" not in sname and "PPG" not in sname)) and eeg_inlet is None:
                eeg_inlet = StreamInlet(s, max_buflen=30)
                logger.info("Connected to Real Muse EEG: %s (Type: %s)", s.name(), s.type())
            elif (stype == "PPG" or "PPG" in sname) and ppg_inlet is None:
                ppg_inlet = StreamInlet(s, max_buflen=30)
                logger.info("Connected to Real Muse PPG: %s (Type: %s)", s.name(), s.type())

        if eeg_inlet is None:
            logger.warning("No real Muse EEG LSL stream found for session %d. Make sure BlueMuse is streaming.", self.session_id)
            with self._lock:
                self.latest["connected"] = False
            return

        with self._lock:
            self.latest["connected"] = True

        eeg_buffer: deque = deque(maxlen=BUFFER_SIZE)
        ppg_buffer: deque = deque(maxlen=256)
        last_snapshot = time.time()

        while not self._stop_event.is_set():
            # Pull EEG samples
            eeg_samples, _ = eeg_inlet.pull_chunk(timeout=0.05, max_samples=32)
            for sample in (eeg_samples or []):
                if len(sample) >= 3:
                    val = float(np.mean([sample[i] for i in FRONTAL_CHANNELS if i < len(sample)]))
                elif len(sample) >= 1:
                    val = float(sample[0])
                else:
                    continue
                eeg_buffer.append(val)

            # Pull PPG samples
            if ppg_inlet is not None:
                ppg_samples, _ = ppg_inlet.pull_chunk(timeout=0.01, max_samples=16)
                for sample in (ppg_samples or []):
                    # IR channel is index 1 (Muse PPG: ambient=0, IR=1, red=2)
                    ppg_buffer.append(float(sample[1] if len(sample) > 1 else sample[0]))

            # Process snapshot every 2 seconds
            now = time.time()
            if now - last_snapshot >= SNAPSHOT_SEC and len(eeg_buffer) >= BUFFER_SIZE // 2:
                last_snapshot = now

                raw = np.array(list(eeg_buffer), dtype=np.float64)
                result = _process_eeg(raw)

                if result is None:
                    logger.warning("EEG session %d: not enough clean samples (too many artifacts)", self.session_id)
                    continue

                # Extract real PPG heart rate
                pulse = 72
                if len(ppg_buffer) >= 64:
                    pulse = _extract_pulse(np.array(list(ppg_buffer), dtype=np.float64))

                with self._lock:
                    q_id  = self._current_q_id
                    q_num = self._current_q_num
                    self.latest.update({
                        **result,
                        "connected":    True,
                        "pulse_rate":   pulse,
                        "question_id":  q_id,
                        "question_num": q_num,
                    })

                logger.info(
                    "EEG snap session=%d α=%.2f β=%.2f θ=%.2f stress=%.2f HR=%d q=%s",
                    self.session_id, result["alpha"], result["beta"],
                    result["theta"], result["stress_index"], pulse, q_num
                )
                self._save_snapshot(result, pulse, q_id, q_num)

        try:
            eeg_inlet.close_stream()
            if ppg_inlet:
                ppg_inlet.close_stream()
        except Exception:
            pass

    def _save_snapshot(self, result: dict, pulse: int,
                       q_id: Optional[int], q_num: Optional[int]):
        """Save EEG snapshot + PPG pulse to the database."""
        try:
            cursor = self._conn.cursor()

            # Save to EEG_Snapshots (processed bands + question marker)
            cursor.execute(
                """INSERT INTO EEG_Snapshots
                   (session_id, recorded_at, alpha_power, beta_power,
                    theta_power, stress_index, question_id, question_num)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.session_id,
                 datetime.now(timezone.utc),
                 result["alpha"],
                 result["beta"],
                 result["theta"],
                 result["stress_index"],
                 q_id, q_num)
            )

            # Save PPG heart rate to SensorData (data_type must be 'ppg')
            cursor.execute(
                """INSERT INTO SensorData
                   (session_id, pulse_rate, data_type, recorded_at)
                   VALUES (?, ?, 'ppg', ?)""",
                (self.session_id, pulse, datetime.now(timezone.utc))
            )

            self._conn.commit()
        except Exception as exc:
            logger.error("Snapshot save failed: %s", exc)
            try:
                self._conn.rollback()
            except Exception:
                pass


# ── Global registry ───────────────────────────────────────────────────────
_active_streams: dict[int, EEGStream] = {}
_registry_lock = threading.Lock()


def start_eeg_stream(session_id: int, db_conn) -> EEGStream:
    with _registry_lock:
        if session_id in _active_streams:
            return _active_streams[session_id]
        stream = EEGStream(session_id, db_conn)
        stream.start()
        _active_streams[session_id] = stream
        return stream


def stop_eeg_stream(session_id: int):
    with _registry_lock:
        stream = _active_streams.pop(session_id, None)
    if stream:
        stream.stop()


def get_eeg_stream(session_id: int) -> Optional[EEGStream]:
    return _active_streams.get(session_id)


def mark_question(session_id: int, question_id: int, question_num: int):
    stream = get_eeg_stream(session_id)
    if stream:
        stream.set_question(question_id, question_num)
