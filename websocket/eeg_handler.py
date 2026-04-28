# ============================================================
# websocket/eeg_handler.py — Real-time EEG WebSocket handler
#
# Route: WS /ws/eeg/{session_id}
#
# Protocol (client → server):
#   JSON message per EEG sample:
#   {
#     "session_id": 42,
#     "eeg_value":  -12.34,   ← µV reading from Muse channel average
#     "ppg_value":  null,     ← optional PPG value from same packet
#     "timestamp":  1700000000.123  ← LSL timestamp (float)
#   }
#
# The handler buffers samples and flushes to the database every
# EEG_BATCH_SIZE (default 50) samples using executemany() for
# efficiency. Remaining samples are flushed on client disconnect.
# ============================================================

import json
import logging
from typing import List, Tuple
from datetime import datetime, timezone

import pyodbc
from fastapi import WebSocket, WebSocketDisconnect

from config import settings
from database import get_connection

logger = logging.getLogger(__name__)

# Type alias: each buffer item is (session_id, eeg_value, ppg_value, recorded_at)
_BufferRow = Tuple[int, float, object, datetime]


def _flush_buffer(buffer: List[_BufferRow], conn: pyodbc.Connection) -> None:
    """
    Insert all buffered EEG/PPG rows into SensorData using executemany()
    for efficient batch insertion.

    Each row in the buffer is a tuple:
        (session_id, eeg_value, ppg_value, recorded_at)

    After insertion the caller should clear the buffer.
    """
    if not buffer:
        return

    rows_to_insert = [
        (
            row[0],          # session_id
            row[1],          # eeg_value
            row[2],          # ppg_value (may be None)
            "eeg",           # data_type
            row[3],          # recorded_at
        )
        for row in buffer
    ]

    try:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO SensorData
                (session_id, eeg_value, ppg_value, data_type, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
        conn.commit()
        logger.debug("Flushed %d EEG rows to database.", len(rows_to_insert))
    except pyodbc.Error as exc:
        conn.rollback()
        logger.error("EEG batch insert failed: %s", exc)


async def eeg_websocket_handler(websocket: WebSocket, session_id: int) -> None:
    """
    Main WebSocket handler for real-time EEG streaming.

    Lifecycle:
      1. Accept the WebSocket connection.
      2. Open a database connection for this session's lifetime.
      3. Receive JSON messages in a loop, buffering EEG samples.
      4. When buffer reaches EEG_BATCH_SIZE → flush to DB.
      5. On client disconnect → flush remaining buffer → close DB conn.

    Args:
        websocket:  The FastAPI WebSocket object.
        session_id: The active session this stream belongs to.
    """
    await websocket.accept()
    logger.info("EEG WebSocket connected: session_id=%d", session_id)

    # Open one persistent DB connection for the entire WebSocket session
    conn = get_connection()
    buffer: List[_BufferRow] = []

    try:
        while True:
            # Receive a JSON string from the client
            raw = await websocket.receive_text()

            # ── Parse the incoming message ────────────────
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(
                    "session=%d: received non-JSON message, skipping.", session_id
                )
                continue

            eeg_value = data.get("eeg_value")
            ppg_value = data.get("ppg_value")   # optional
            lsl_ts = data.get("timestamp")

            # Convert LSL timestamp to UTC datetime
            if lsl_ts is not None:
                recorded_at = datetime.fromtimestamp(float(lsl_ts), tz=timezone.utc)
            else:
                recorded_at = datetime.now(timezone.utc)

            # Validate EEG value before buffering
            if eeg_value is None:
                logger.warning(
                    "session=%d: message missing eeg_value, skipping.", session_id
                )
                continue

            buffer.append((session_id, float(eeg_value), ppg_value, recorded_at))

            # ── Flush when batch size reached ─────────────
            if len(buffer) >= settings.EEG_BATCH_SIZE:
                _flush_buffer(buffer, conn)
                buffer.clear()

                # Acknowledge the batch to the client
                await websocket.send_text(
                    json.dumps({"status": "batch_saved", "count": settings.EEG_BATCH_SIZE})
                )

    except WebSocketDisconnect:
        logger.info(
            "EEG WebSocket disconnected: session_id=%d. Flushing %d remaining rows.",
            session_id, len(buffer),
        )
    except Exception as exc:
        logger.exception("EEG WebSocket error (session=%d): %s", session_id, exc)
    finally:
        # ── Always flush remaining samples on disconnect ──
        if buffer:
            _flush_buffer(buffer, conn)
            logger.info(
                "Flushed %d remaining EEG rows for session=%d", len(buffer), session_id
            )

        conn.close()
        logger.info("DB connection closed for EEG session=%d", session_id)
