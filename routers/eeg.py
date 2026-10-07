"""routers/eeg.py — EEG control endpoints.

Endpoints:
  POST /eeg/connect      - Start EEG stream for a session
  POST /eeg/disconnect   - Stop EEG stream for a session
  GET  /eeg/status/{id}  - Is EEG connected for this session?
  POST /eeg/marker       - Tag current EEG with a question marker
  GET  /eeg/timeline/{session_id} - Get all snapshots for psychologist graph
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_connection
from hardware.eeg_stream import start_eeg_stream, stop_eeg_stream, get_eeg_stream, mark_question

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eeg", tags=["EEG"])


class ConnectRequest(BaseModel):
    session_id: int


class MarkerRequest(BaseModel):
    session_id: int
    question_id: int
    question_num: int


@router.post("/connect")
def connect_eeg(req: ConnectRequest):
    """
    Start the EEG stream for a session.
    Call this when the user taps the 'Connect EEG' button in the app.
    BlueMuse must already be running and streaming on this PC.
    """
    conn = get_connection()
    stream = start_eeg_stream(req.session_id, conn)
    return {"status": "starting", "session_id": req.session_id,
            "message": "EEG stream started. Make sure BlueMuse is running."}


@router.post("/disconnect")
def disconnect_eeg(req: ConnectRequest):
    """Stop the EEG stream for a session."""
    stop_eeg_stream(req.session_id)
    return {"status": "stopped", "session_id": req.session_id}


@router.get("/status/{session_id}")
def eeg_status(session_id: int):
    """Check if EEG stream is active and connected for this session."""
    stream = get_eeg_stream(session_id)
    if not stream:
        return {"session_id": session_id, "running": False, "connected": False}
    return {
        "session_id": session_id,
        "running":    True,
        "connected":  stream.latest.get("connected", False),
        "latest":     stream.latest,
    }


@router.post("/marker")
def set_question_marker(req: MarkerRequest):
    """
    Tag the EEG stream with the current question being answered.
    Call this every time the user moves to a new question in the questionnaire.
    This allows the psychologist to see EEG values per question later.
    """
    mark_question(req.session_id, req.question_id, req.question_num)
    return {"status": "ok", "question_id": req.question_id, "question_num": req.question_num}


@router.get("/timeline/{session_id}")
def eeg_timeline(session_id: int):
    """
    Return all EEG snapshots for a session, used by the psychologist graph.
    Each snapshot has alpha, beta, theta, stress_index, and optionally
    which question was being answered at that moment.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT snapshot_id, recorded_at, alpha_power, beta_power,
                      theta_power, stress_index, question_id, question_num
               FROM EEG_Snapshots
               WHERE session_id = ?
               ORDER BY recorded_at ASC""",
            (session_id,)
        )
        rows = cursor.fetchall()
        return {
            "session_id": session_id,
            "count": len(rows),
            "snapshots": [
                {
                    "snapshot_id":  r[0],
                    "recorded_at":  r[1].isoformat() if r[1] else None,
                    "alpha":        round(r[2], 4),
                    "beta":         round(r[3], 4),
                    "theta":        round(r[4], 4),
                    "stress_index": round(r[5], 4),
                    "question_id":  r[6],
                    "question_num": r[7],
                }
                for r in rows
            ]
        }
    except Exception as exc:
        logger.exception("EEG timeline fetch failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not fetch EEG timeline.")
    finally:
        conn.close()
