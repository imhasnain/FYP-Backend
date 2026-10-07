"""websocket/eeg_handler.py — WebSocket that pushes live EEG data to the Flutter app.

HOW IT WORKS:
  The Flutter app connects to WS /ws/eeg/{session_id}.
  This handler loops every 2 seconds and pushes the latest processed
  EEG values (alpha, beta, theta, stress_index) from the EEGStream object.

  The EEGStream (hardware/eeg_stream.py) runs in a separate thread,
  continuously reading from the Muse headset via BlueMuse/LSL and
  computing band powers. This handler just reads its .latest dict
  and forwards it to the phone over WebSocket.

  If EEG is not connected, we push a "disconnected" status so the
  Flutter app can show a "Connect EEG" prompt.
"""

import json
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from hardware.eeg_stream import get_eeg_stream

logger = logging.getLogger(__name__)


async def eeg_websocket_handler(websocket: WebSocket, session_id: int) -> None:
    """
    Push live EEG snapshot data to the Flutter app every 2 seconds.
    The app shows this in the Live Vitals panel during a session.
    """
    await websocket.accept()
    logger.info("EEG WebSocket connected: session_id=%d", session_id)

    try:
        while True:
            stream = get_eeg_stream(session_id)

            if stream and stream.latest.get("connected"):
                # Real data from Muse headset
                payload = {
                    "connected":    True,
                    "alpha":        stream.latest["alpha"],
                    "beta":         stream.latest["beta"],
                    "theta":        stream.latest["theta"],
                    "stress_index": stream.latest["stress_index"],
                    "question_num": stream.latest.get("question_num"),
                    "timestamp":    datetime.now(timezone.utc).isoformat(),
                }
            elif stream and not stream.latest.get("connected"):
                # Stream started but Muse not yet found
                payload = {
                    "connected": False,
                    "status": "searching",
                    "message": "Looking for Muse headset... Make sure BlueMuse is streaming.",
                }
            else:
                # No stream started yet — waiting for /eeg/connect call
                payload = {
                    "connected": False,
                    "status": "idle",
                    "message": "Press Connect EEG to begin.",
                }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2.0)   # push every 2 seconds

    except WebSocketDisconnect:
        logger.info("EEG WebSocket disconnected: session_id=%d", session_id)
    except Exception as exc:
        logger.exception("EEG WebSocket error (session=%d): %s", session_id, exc)
