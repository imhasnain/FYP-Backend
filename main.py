# ============================================================
# main.py — FastAPI application entry point
#
# Run the server:
#   uvicorn main:app --reload --host 0.0.0.0 --port 8000
#
# Interactive API docs:
#   http://localhost:8000/docs   (Swagger UI)
#   http://localhost:8000/redoc  (ReDoc)
# ============================================================

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

# ── Logging configuration ─────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application lifespan (startup / shutdown) ─────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: verify the database connection, create directories,
    and load ML models.
    Shutdown: log a clean exit message.
    """
    logger.info("=== Virtual Clinic Backend starting up ===")

    # ── Create emotion_images directory ───────────────────
    os.makedirs(settings.EMOTION_IMAGES_DIR, exist_ok=True)
    logger.info("Emotion images directory ready: %s", settings.EMOTION_IMAGES_DIR)

    # ── Test database connection ──────────────────────────
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE() AS now")
        row = cursor.fetchone()
        conn.close()
        logger.info("✅ Database connection OK — SQL Server time: %s", row.now)
    except Exception as exc:
        logger.error("❌ Database connection FAILED on startup: %s", exc)
        logger.error(
            "The server will still start, but all DB operations will fail. "
            "Check your SQL Server settings in config.py / .env"
        )

    # ── Load ML models ────────────────────────────────────
    try:
        load_models()
        if models_loaded():
            logger.info("✅ ML models loaded successfully.")
        else:
            logger.warning(
                "⚠️  ML models not found. Run 'python -m ml.trainer' to train them. "
                "Predictions will use rule-based fallback."
            )
    except Exception as exc:
        logger.error("❌ ML model loading failed: %s", exc)

    logger.info("=== Virtual Clinic Backend is READY ===")

    yield  # Application runs here

    logger.info("=== Virtual Clinic Backend shutting down ===")


# ── FastAPI application instance ──────────────────────────
app = FastAPI(
    title="Multimodal Virtual Clinic API",
    description=(
        "Backend for the FYP: Multimodal Virtual Clinic for Psychologists "
        "using EEG, BP, Pulse Rate, and Facial Emotion detection."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS — allow all origins (FYP / single-machine setup) ─
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # Restrict to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register HTTP routers ─────────────────────────────────
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(questionnaire.router)
app.include_router(sensors.router)
app.include_router(results.router)


# ── WebSocket route — real-time EEG streaming ─────────────
@app.websocket("/ws/eeg/{session_id}")
async def websocket_eeg(websocket: WebSocket, session_id: int):
    """
    WebSocket endpoint for streaming EEG data from the Muse headset.

    The client (EEG script) connects here and sends JSON packets:
        {"session_id": 1, "eeg_value": -12.3, "ppg_value": null, "timestamp": 1700000000.0}

    Samples are buffered and batch-inserted every 50 readings.
    """
    await eeg_websocket_handler(websocket=websocket, session_id=session_id)


# ── Health check ──────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    """
    Simple health-check endpoint.
    Returns server status and link to API documentation.
    """
    return {
        "status": "running",
        "service": "Multimodal Virtual Clinic API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["Health"])
def health_check():
    """
    Detailed health check endpoint.

    Returns:
        - db_connected: Whether the database is reachable.
        - models_loaded: Whether ML models are loaded in memory.
        - server: Always 'running'.
    """
    return {
        "db_connected": test_connection(),
        "models_loaded": models_loaded(),
        "server": "running",
    }


# ── Development entry point ───────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
