"""
main.py — FastAPI application entry point

Run:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Docs:
    http://localhost:8000/docs
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import get_connection, test_connection
from routers import auth, sessions, questionnaire, sensors, results
from websocket.eeg_handler import eeg_websocket_handler
from ml.predictor import load_models, models_loaded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Virtual Clinic Backend starting up ===")

    os.makedirs(settings.EMOTION_IMAGES_DIR, exist_ok=True)

    # Verify DB connection
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE() AS now")
        row = cursor.fetchone()
        conn.close()
        logger.info("✅ Database connection OK — SQL Server time: %s", row.now)
    except Exception as exc:
        logger.error("❌ Database connection FAILED: %s", exc)

    # Load ML models
    try:
        load_models()
        if models_loaded():
            logger.info("✅ ML models loaded successfully.")
        else:
            logger.warning("⚠️  ML models not found. Run 'python -m ml.trainer' to train them.")
    except Exception as exc:
        logger.error("❌ ML model loading failed: %s", exc)

    logger.info("=== Virtual Clinic Backend is READY ===")
    yield
    logger.info("=== Virtual Clinic Backend shutting down ===")


app = FastAPI(
    title="Multimodal Virtual Clinic API",
    description="FYP Backend — EEG, BP, Facial Emotion & Questionnaire mental health assessment.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(questionnaire.router)
app.include_router(sensors.router)
app.include_router(results.router)


@app.websocket("/ws/eeg/{session_id}")
async def websocket_eeg(websocket: WebSocket, session_id: int):
    await eeg_websocket_handler(websocket=websocket, session_id=session_id)


@app.get("/", tags=["Health"])
def root():
    return {"status": "running", "service": "Multimodal Virtual Clinic API", "docs": "/docs"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"db_connected": test_connection(), "models_loaded": models_loaded()}
