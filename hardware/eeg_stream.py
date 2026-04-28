# ============================================================
# hardware/eeg_stream.py — Muse headset LSL stream helpers
#
# Two modes of operation:
#   1. Manual: User runs 'muselsl stream --ppg' in a separate terminal
#   2. Auto:   Call auto_start_muse_stream() to spawn the subprocess
#              automatically (inspired by senior project pattern)
#
# This module reads from the LSL streams that muselsl exposes.
# pylsl resolves streams on localhost automatically.
# ============================================================

import sys
import time
import logging
import subprocess
from typing import Optional, Tuple, List

from pylsl import StreamInlet, StreamInfo, resolve_stream

logger = logging.getLogger(__name__)

# Timeout in seconds when waiting to find an LSL stream
LSL_RESOLVE_TIMEOUT = 5.0

# Global subprocess reference for muselsl
_muse_proc: Optional[subprocess.Popen] = None


def auto_start_muse_stream(wait_seconds: int = 8) -> bool:
    """
    Automatically start the muselsl stream as a subprocess.

    Spawns 'python -m muselsl stream --ppg' in the background,
    waits for the stream to initialize, then returns.

    This is inspired by the senior project pattern where the backend
    manages the muselsl process lifecycle internally.

    Args:
        wait_seconds: How long to wait for the stream to start (default 8s).

    Returns:
        True if the process was started (or is already running), False on error.
    """
    global _muse_proc

    if _muse_proc is not None and _muse_proc.poll() is None:
        logger.info("muselsl process already running (PID=%d).", _muse_proc.pid)
        return True

    try:
        logger.info("Starting muselsl stream subprocess...")
        _muse_proc = subprocess.Popen(
            [sys.executable, "-m", "muselsl", "stream", "--ppg"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("muselsl subprocess started (PID=%d). Waiting %ds...", _muse_proc.pid, wait_seconds)
        time.sleep(wait_seconds)
        return True

    except FileNotFoundError:
        logger.error(
            "muselsl not installed. Install it with: pip install muselsl"
        )
        return False
    except Exception as exc:
        logger.error("Failed to start muselsl stream: %s", exc)
        return False


def stop_muse_stream() -> None:
    """
    Terminate the muselsl subprocess if it was auto-started.

    Safe to call multiple times. Does nothing if no subprocess is running.
    """
    global _muse_proc

    if _muse_proc is not None:
        try:
            _muse_proc.terminate()
            _muse_proc.wait(timeout=5)
            logger.info("muselsl subprocess terminated.")
        except Exception as exc:
            logger.warning("Error stopping muselsl: %s", exc)
        finally:
            _muse_proc = None


def get_eeg_inlet() -> Optional[StreamInlet]:
    """
    Resolve and return a pylsl StreamInlet for the EEG stream
    published by muselsl.

    Blocks for up to LSL_RESOLVE_TIMEOUT seconds while searching.
    Returns None if no EEG stream is found (muselsl not running).

    Returns:
        StreamInlet for EEG data, or None if not available.
    """
    logger.info("Searching for EEG LSL stream (type='EEG')...")
    try:
        streams: List[StreamInfo] = resolve_stream("type", "EEG", timeout=LSL_RESOLVE_TIMEOUT)

        if not streams:
            logger.warning(
                "No EEG LSL stream found. "
                "Make sure 'muselsl stream' is running or call auto_start_muse_stream()."
            )
            return None

        inlet = StreamInlet(streams[0])
        logger.info(
            "Connected to EEG stream: name=%s, channels=%d, srate=%.1f Hz",
            streams[0].name(),
            streams[0].channel_count(),
            streams[0].nominal_srate(),
        )
        return inlet
    except Exception as exc:
        logger.warning("EEG stream resolve failed: %s", exc)
        return None


def get_ppg_inlet() -> Optional[StreamInlet]:
    """
    Resolve and return a pylsl StreamInlet for the PPG (pulse) stream
    published by muselsl.

    The Muse headset exposes PPG data as a separate LSL stream with
    type 'PPG'. This stream contains heart rate / blood volume pulse.

    Returns:
        StreamInlet for PPG data, or None if not available.
    """
    logger.info("Searching for PPG LSL stream (type='PPG')...")
    try:
        streams: List[StreamInfo] = resolve_stream("type", "PPG", timeout=LSL_RESOLVE_TIMEOUT)

        if not streams:
            logger.warning(
                "No PPG LSL stream found. "
                "Ensure your muselsl version supports PPG (use --ppg flag)."
            )
            return None

        inlet = StreamInlet(streams[0])
        logger.info(
            "Connected to PPG stream: name=%s, channels=%d, srate=%.1f Hz",
            streams[0].name(),
            streams[0].channel_count(),
            streams[0].nominal_srate(),
        )
        return inlet
    except Exception as exc:
        logger.warning("PPG stream resolve failed: %s", exc)
        return None


def read_eeg_sample(inlet: StreamInlet) -> Tuple[Optional[List[float]], Optional[float]]:
    """
    Pull a single EEG sample from the given StreamInlet.

    Returns:
        (sample_list, lsl_timestamp) — sample_list contains one float per
        EEG channel (Muse has 4 channels: TP9, AF7, AF8, TP10).
        Returns (None, None) if no new sample is available.

    Note: Call this in a tight loop to drain all available samples.
    """
    sample, timestamp = inlet.pull_sample(timeout=0.0)
    return sample, timestamp


def read_ppg_sample(inlet: StreamInlet) -> Tuple[Optional[float], Optional[float]]:
    """
    Pull a single PPG sample and return the first channel value.

    The Muse PPG stream typically has 3 channels (ambient + IR + red).
    We use channel 0 (ambient / primary) as the PPG value.

    Returns:
        (ppg_value, lsl_timestamp) — (None, None) if no sample ready.
    """
    sample, timestamp = inlet.pull_sample(timeout=0.0)
    if sample is None:
        return None, None
    return float(sample[0]), timestamp


# ── Quick test ────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing EEG/PPG stream connection...")
    print()

    # Try auto-start first
    print("Attempting auto-start of muselsl stream...")
    started = auto_start_muse_stream(wait_seconds=8)

    if started:
        eeg = get_eeg_inlet()
        ppg = get_ppg_inlet()

        if eeg:
            print("EEG stream connected! Reading 10 samples...")
            for i in range(10):
                sample, ts = read_eeg_sample(eeg)
                if sample:
                    print(f"  EEG sample {i}: channels={sample[:4]} ts={ts:.3f}")
                time.sleep(0.1)
        else:
            print("No EEG stream found.")

        if ppg:
            print("\nPPG stream connected! Reading 5 samples...")
            for i in range(5):
                val, ts = read_ppg_sample(ppg)
                if val:
                    print(f"  PPG sample {i}: value={val:.2f} ts={ts:.3f}")
                time.sleep(0.2)
        else:
            print("No PPG stream found.")

        stop_muse_stream()
    else:
        print("Could not start muselsl. Is the Muse headset paired via Bluetooth?")
