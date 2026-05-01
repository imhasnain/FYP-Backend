# Multimodal Virtual Clinic — Technical Deep Dive

> A complete explanation of every layer of the backend: what we built, why we chose each technology, and how each piece works internally.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Why FastAPI?](#2-why-fastapi)
3. [Project Configuration — config.py](#3-project-configuration--configpy)
4. [Database Layer — database.py](#4-database-layer--databasepy)
5. [Authentication — JWT Tokens](#5-authentication--jwt-tokens)
6. [Pydantic Models — Request & Response Validation](#6-pydantic-models--request--response-validation)
7. [REST API Routers](#7-rest-api-routers)
8. [WebSockets — Why and How](#8-websockets--why-and-how)
9. [Hardware Integration](#9-hardware-integration)
10. [Preprocessing Pipeline](#10-preprocessing-pipeline)
11. [ML Pipeline — Feature Building & Prediction](#11-ml-pipeline--feature-building--prediction)
12. [Facial Emotion Detection — Dual Model System](#12-facial-emotion-detection--dual-model-system)
13. [Scoring Engine](#13-scoring-engine)
14. [Application Startup — Lifespan Events](#14-application-startup--lifespan-events)
15. [Data Flow — End to End](#15-data-flow--end-to-end)

---

## 1. Project Overview

This is the backend of the **Multimodal Virtual Clinic** — a Final Year Project that assesses the mental health of university students and teachers. Instead of relying on a single test, it fuses four data sources simultaneously:

| Source | Data Collected | Technology Used |
|--------|---------------|-----------------|
| Questionnaire | 4-stage psychological screening | REST API + SQL Server |
| Webcam | Facial emotions every 5 seconds | OpenCV + Custom CNN + DeepFace |
| Muse EEG Headset | Brainwave activity (EEG + heart rate) | muselsl + pylsl + WebSocket |
| BLE Blood Pressure Cuff | Systolic/diastolic pressure | bleak (Bluetooth LE) |

All four streams are combined into a **16-element feature vector** which is fed into a **RandomForest ML model** that produces one of four recommendations:

```
Normal → Calm Down → See Psychologist → Emergency
```

Two separate models exist — one trained for students, one for teachers — because their stressors differ (CGPA vs teaching load).

---

## 2. Why FastAPI?

We chose **FastAPI** over Flask or Django for several specific reasons:

### Automatic Data Validation
FastAPI uses **Pydantic** models for request/response. If the client sends wrong data types, FastAPI rejects it automatically before our code runs:
```python
class BPRequest(BaseModel):
    session_id: int
    systolic: int      # FastAPI rejects "abc" automatically
    diastolic: int
```

### Built-in API Documentation
FastAPI auto-generates **Swagger UI** at `/docs` and **ReDoc** at `/redoc` — teammates can test every endpoint directly in the browser without Postman.

### Native WebSocket Support
FastAPI handles WebSocket connections natively in the same server process. This was critical for the EEG streaming feature.

### ASGI + Async
FastAPI runs on **Uvicorn** (ASGI server), which means it can handle many concurrent connections efficiently. Regular Flask uses WSGI which is synchronous and slower for real-time streaming.

### Type Hints → IDE Support
Every function has proper Python type hints, making the code easier to understand and debug.

---

## 3. Project Configuration — config.py

```python
class Settings(BaseSettings):
    DB_SERVER: str = "localhost"
    DB_NAME: str = "VirtualClinicDB"
    DB_TRUSTED_CONNECTION: bool = True
    SECRET_KEY: str = "CHANGE_ME..."
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = 480
    EEG_BATCH_SIZE: int = 50
    EMOTION_INTERVAL_SECONDS: int = 5
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    EMOTION_IMAGES_DIR: str = os.path.join(BASE_DIR, "emotion_images")
```

**How it works:**
- `pydantic-settings` reads values from the `.env` file automatically
- If a value is not in `.env`, the default in the class is used
- The single `settings` object is imported everywhere — no global variables scattered around

**Why `BASE_DIR` matters:**  
Without `BASE_DIR`, loading the ML model file at `ml/saved_models/custom_emotion_model.h5` would fail if the server is started from a different directory. `os.path.abspath(__file__)` always resolves relative to `config.py` itself, not the current working directory.

---

## 4. Database Layer — database.py

We use **Microsoft SQL Server** with **pyodbc** (Python ODBC driver).

### Why SQL Server?
The university environment already has SQL Server available. It supports the complex queries we need (window functions, `OUTPUT INSERTED.id` for getting auto-generated IDs, etc.).

### Connection Strategy
```python
def get_connection() -> pyodbc.Connection:
    conn_str = _build_conn_str()
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            conn = pyodbc.connect(conn_str, timeout=5)
            conn.autocommit = False
            return conn
        except pyodbc.Error:
            time.sleep(_RETRY_DELAY)
    raise last_exc
```

**Why retry logic?**  
SQL Server sometimes takes a moment to accept connections on startup (especially on Windows with cold start). Three retries with a 1-second delay between them prevents the server from crashing just because of a brief DB cold-start delay.

**Why `autocommit = False`?**  
We want to control transactions manually. We call `conn.commit()` after successful writes and `conn.rollback()` on errors. This prevents partial data being saved if something fails mid-operation.

### Connection Pattern — No Connection Pool
Every endpoint opens a connection → does its work → closes it. We do NOT use a connection pool because:
- SQL Server has its own internal connection pooling via ODBC Driver 17
- Our request volume is low (FYP demo scale)
- Simpler code — no pool lifecycle management

### The `db_cursor()` Context Manager
```python
@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```
Used in simpler endpoints where you just need one cursor and automatic cleanup.

---

## 5. Authentication — JWT Tokens

### Why JWT?
We have a mobile frontend (Flutter). Mobile apps can't use server-side sessions (no cookies). **JWT (JSON Web Token)** is stateless — the token is stored on the device, sent with every request, and the server validates it without any database lookup.

### How It Works

**Step 1 — Login:**
```
POST /auth/login { email, password }
```
The server finds the user in the DB, checks the password, then creates a token:

```python
def create_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=480)
    payload = {
        "sub": str(user_id),   # "subject" — who this token belongs to
        "role": role,           # student / teacher / psychologist
        "exp": expire           # expiry time
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
```

The token is a base64-encoded string like:
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6InN0dWRlbnQiLCJleHAiOjE3...
```

**Step 2 — Subsequent Requests:**  
The frontend sends the token in every request header:
```
Authorization: Bearer eyJhbGciOiJ...
```

**Step 3 — Validation:**
```python
def decode_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    return {"user_id": int(payload["sub"]), "role": payload["role"]}
```
`python-jose` verifies the signature and checks expiry automatically.

### Why HS256?
HS256 (HMAC-SHA256) is a symmetric algorithm — same key signs and verifies. Simple and fast. We don't need asymmetric (RS256) because we control both the server that signs and the server that verifies.

### Pre-seeded Accounts
We removed registration. Accounts are inserted directly into the database via `schema.sql`. This simplifies the system — no email verification, no password reset flow needed for a controlled FYP demo.

---

## 6. Pydantic Models — Request & Response Validation

Every API endpoint has a request model and a response model defined in `models/`.

**Example — Emotion endpoint:**
```python
class EmotionRequest(BaseModel):
    session_id: int
    user_id: int
    stage_number: int = 1      # default value
    image_base64: str          # base64-encoded JPEG

class EmotionResponse(BaseModel):
    session_id: int
    dominant_emotion: str
    scores: Dict[str, float]   # { "happy": 78.3, "angry": 2.1, ... }
    captured_at: datetime
```

**What Pydantic does automatically:**
- Rejects requests with missing required fields (HTTP 422)
- Converts types: if `session_id` arrives as `"5"` (string), it becomes `5` (int)
- Serializes `datetime` objects to ISO format strings in responses
- Validates `EmailStr` for email fields (uses email-validator library)

**Why separate Request and Response models?**  
The client sends only what it needs to send. The server returns only what the client needs to see. Internal DB fields (like `recorded_at` generated by the server) are never in the request model.

---

## 7. REST API Routers

FastAPI uses **APIRouter** to split routes into separate files. Each router has a `prefix` that is prepended to all its routes:

```python
router = APIRouter(prefix="/session", tags=["Sessions"])

@router.post("/start")    # full path: POST /session/start
@router.post("/end")      # full path: POST /session/end
@router.get("/{id}")      # full path: GET /session/{id}
```

All routers are registered in `main.py`:
```python
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(questionnaire.router)
app.include_router(sensors.router)
app.include_router(results.router)
```

### Key Pattern — Every Endpoint
```python
@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # ... do work ...
        conn.commit()
        return StartSessionResponse(...)
    except HTTPException:
        raise                    # re-raise our own errors unchanged
    except Exception as exc:
        conn.rollback()
        logger.exception(...)
        raise HTTPException(500, detail="...")
    finally:
        conn.close()             # ALWAYS close, even on error
```

The `finally` block ensures the DB connection is always closed, even if an exception is thrown.

### Getting Auto-Inserted IDs — `OUTPUT INSERTED`
SQL Server doesn't support `cursor.lastrowid` the same way SQLite does. We use the T-SQL `OUTPUT INSERTED` clause:
```sql
INSERT INTO Sessions (user_id, start_time)
OUTPUT INSERTED.session_id
VALUES (?, ?)
```
This returns the newly generated `session_id` immediately in the same query.

---

## 8. WebSockets — Why and How

### The Problem with REST for EEG
The Muse headset streams EEG at **256 samples per second** (256 Hz). If we used a regular REST API for this, the frontend would have to make 256 HTTP POST requests every second. Each HTTP request has significant overhead:
- TCP handshake
- HTTP headers (~500 bytes each)
- Server routing and middleware

At 256 Hz this would be **~128 KB/s of HTTP overhead alone**, plus the server would be overwhelmed with individual requests.

### The WebSocket Solution
WebSocket is a **persistent, bidirectional TCP connection**. Once established, data flows in both directions as raw frames with minimal overhead — no repeated headers.

```
Client                         Server
  |------- WS Handshake -------->|
  |<------ 101 Switching --------|   (one-time HTTP upgrade)
  |                               |
  |-- { eeg_value: -12.3 } ------>|   (very fast, no headers)
  |-- { eeg_value: 8.1 } -------->|
  |-- { eeg_value: -5.7 } ------->|
  ...256 times per second...
  |<-- { status: "batch_saved" }--|   (acknowledgment every 50 samples)
  |                               |
  |------- Disconnect ----------->|   (remaining data flushed to DB)
```

### FastAPI WebSocket Route
```python
@app.websocket("/ws/eeg/{session_id}")
async def websocket_eeg(websocket: WebSocket, session_id: int):
    await eeg_websocket_handler(websocket=websocket, session_id=session_id)
```

The `async` keyword is essential — the handler must be non-blocking so the server can handle other HTTP requests while the WebSocket connection is open.

### The Handler (`websocket/eeg_handler.py`)

```python
async def eeg_websocket_handler(websocket: WebSocket, session_id: int):
    await websocket.accept()           # Accept the connection
    conn = get_connection()            # One DB connection for the whole session
    buffer = []

    try:
        while True:
            raw = await websocket.receive_text()   # Wait for next message
            data = json.loads(raw)

            buffer.append((session_id, data["eeg_value"], data.get("ppg_value"), recorded_at))

            if len(buffer) >= settings.EEG_BATCH_SIZE:   # 50 samples
                _flush_buffer(buffer, conn)               # batch INSERT
                buffer.clear()
                await websocket.send_text('{"status":"batch_saved"}')

    except WebSocketDisconnect:
        if buffer:
            _flush_buffer(buffer, conn)   # flush remaining on disconnect
    finally:
        conn.close()
```

### Why Batch Size 50?
Instead of inserting every single EEG sample to the database individually (256 inserts/second), we collect 50 samples in memory and insert them all at once using `executemany()`. This is roughly a **50× reduction in database writes** with the same data captured.

### Why One DB Connection Per WebSocket?
Opening a new DB connection for every batch would add 50–100ms latency per batch. Keeping one connection open for the entire WebSocket session means batch inserts complete in ~1–2ms.

---

## 9. Hardware Integration

### Muse EEG Headset — How it Works

```
Muse Headset (Bluetooth)
    ↓
muselsl (command-line tool, run separately)
    ↓ publishes two LSL (Lab Streaming Layer) streams
    ↓ type='EEG'  — 4 channels, 256 Hz
    ↓ type='PPG'  — 3 channels, 64 Hz (heart rate)
pylsl (Python library in our backend)
    ↓ resolves streams on localhost
    ↓ reads samples
WebSocket → /ws/eeg/{session_id}
```

**What is LSL?**  
Lab Streaming Layer (LSL) is a protocol for real-time streaming of time-series data in neuroscience research. `muselsl` uses it to broadcast the Muse data on the local network, and `pylsl` reads it.

**`hardware/eeg_stream.py` provides:**
- `auto_start_muse_stream()` — spawns `muselsl stream --ppg` as a subprocess
- `get_eeg_inlet()` — connects to the EEG LSL stream
- `get_ppg_inlet()` — connects to the PPG (heart rate) stream
- `read_eeg_sample(inlet)` — pulls one sample from the stream

**4 EEG Channels from Muse:**
- TP9 (left ear) — temporal lobe
- AF7 (left forehead) — prefrontal cortex
- AF8 (right forehead) — prefrontal cortex
- TP10 (right ear) — temporal lobe

We average all 4 channels to get a single `eeg_value` per sample sent through the WebSocket.

### BLE Blood Pressure Cuff — How it Works

```
Omron BP Cuff (Bluetooth LE)
    ↓ BLE GATT notification on UUID: 00002a35-0000-1000-8000-00805f9b34fb
bleak (Python BLE library)
    ↓ scans for device, connects, subscribes to notifications
    ↓ notification callback triggered on each reading
REST → POST /sensors/bp { systolic, diastolic, pulse_rate }
```

**What is BLE GATT?**  
Bluetooth Low Energy devices expose data through a profile called GATT (Generic Attribute Profile). Each type of data has a standardized UUID. UUID `0x2A35` is the international standard for "Blood Pressure Measurement" — all Omron, Withings, and similar BLE cuffs use this same UUID.

---

## 10. Preprocessing Pipeline

When a session ends (`POST /session/end`), the server runs four preprocessors to summarize all the raw sensor data collected during the session.

### EEG Preprocessing (`preprocessing/eeg_preprocessor.py`)

Raw EEG data is just a stream of voltage readings in microvolts (µV). To extract meaning, we apply:

**Step 1 — Bandpass Filter (1–40 Hz)**  
The raw signal contains noise from muscle movements, eye blinks, and electrical interference. A Butterworth bandpass filter removes everything outside 1–40 Hz:
```python
sos = butter(order=4, Wn=[low, high], btype="band", output="sos")
filtered = sosfilt(sos, raw_signal)
```
We use `output="sos"` (Second-Order Sections) instead of `output="ba"` because SOS is numerically more stable for higher-order filters.

**Step 2 — FFT (Fast Fourier Transform)**  
FFT converts the time-domain signal (voltage vs time) into a frequency-domain representation (power at each frequency). This lets us see which brain frequencies are dominant:
```python
fft_vals = np.fft.rfft(signal)
fft_power = np.abs(fft_vals) ** 2 / n
freqs = np.fft.rfftfreq(n, d=1.0/fs)
```

**Step 3 — Extract Band Powers**

| Band | Hz Range | Brain State |
|------|----------|-------------|
| Delta | 1–4 Hz | Deep sleep, unconscious |
| Theta | 4–8 Hz | Drowsiness, daydreaming |
| Alpha | 8–13 Hz | Relaxed, eyes closed, calm |
| Beta | 13–30 Hz | Active thinking, stress, focus |

**Step 4 — Stress Index**
```
stress_index = (beta_power + theta_power) / alpha_power
```
When a person is stressed: beta↑, theta↑, alpha↓ → stress_index goes up.  
When relaxed: alpha↑, beta↓ → stress_index goes down.

This formula is a well-known neuroscience metric used in clinical EEG research.

### BP Preprocessing (`preprocessing/bp_preprocessor.py`)

Simple aggregation — computes mean systolic, mean diastolic, and mean pulse across all BP readings for the session. Also sets a `hypertension_flag` if systolic > 140 OR diastolic > 90 (standard clinical threshold).

### Emotion Preprocessing (`preprocessing/emotion_preprocessor.py`)

```python
EMOTION_DISTRESS_MAP = {
    "happy": 0.0, "neutral": 0.1, "surprise": 0.2,
    "disgust": 0.4, "fear": 0.7, "sad": 0.7,
    "angry": 0.8, "undetected": 0.3,
}
```

For each captured emotion frame, the distress value is weighted by the model's confidence in that prediction. The final `emotion_distress_score` is a confidence-weighted average across all frames in the session, clamped to [0, 1].

---

## 11. ML Pipeline — Feature Building & Prediction

### Why RandomForest?

| Criterion | RandomForest | Neural Network | SVM |
|-----------|-------------|----------------|-----|
| Needs large data? | No — works well on 5000 samples | Yes — needs 10k+ | No |
| Handles mixed features? | Yes | Needs normalization | Needs normalization |
| Interpretable? | Yes — feature importance | Black box | Partly |
| Training time | ~2 minutes | Hours | Minutes |
| Overfitting risk | Low (ensemble) | High | Medium |

RandomForest builds 200 decision trees on random subsets of data and takes a majority vote. The ensemble is much more robust than a single tree.

### Feature Vector Assembly (`ml/feature_builder.py`)

```
[0]  emotional_score       — normalized Stage 1 questionnaire score (0–4)
[1]  functional_score      — Stage 2
[2]  context_score         — Stage 3
[3]  isolation_score       — Stage 4
[4]  critical_score        — Stage 5 (0 if not reached)
[5]  role_specific_1       — student: cgpa_trend  | teacher: workload_hrs
[6]  role_specific_2       — student: attendance_drop | teacher: class_count
[7]  role_specific_3       — student: performance_decline | teacher: 0.0
[8]  eeg_stress_index      — (beta+theta)/alpha from EEG preprocessor
[9]  eeg_alpha_power       — FFT band power
[10] eeg_theta_power       — FFT band power
[11] hr_mean               — mean heart rate from all pulse readings
[12] bp_mean_systolic      — mean from SensorData (data_type='bp')
[13] bp_mean_diastolic
[14] pulse_avg             — from BP cuff + Muse PPG combined
[15] emotion_distress_score — 0.0 (happy) to 1.0 (angry) weighted average
```

**Key design — missing data defaults to 0.0:**
If no EEG was connected, features [8–10] are 0.0. The model was trained on synthetic data that includes 0.0 values for missing sensors, so it handles partial data gracefully.

### Training (`ml/trainer.py`)

Since we don't have thousands of real clinical sessions, we generate **synthetic training data** using rule-based logic:

```python
# Emergency class — realistic high-stress values
emotional  = normal(mean=3.5, std=0.3)
eeg_stress = normal(mean=5.0, std=1.5)
hr_mean    = normal(mean=105, std=15)
bp_sys     = normal(mean=150, std=15)
emotion    = normal(mean=0.8, std=0.1)   # angry/fear face
```

5000 samples per role (1250 per class), 80/20 train/test split. Accuracy is ~99.8% on synthetic data.

> **Future step:** Once real sessions accumulate in `MH_Results`, call `retrain_from_db(role, conn)` to train on real clinical data.

### Making a Prediction (`ml/predictor.py`)

```python
X = np.array(features).reshape(1, -1)       # shape: (1, 16)
prediction = int(model.predict(X)[0])        # 0, 1, 2, or 3
probabilities = model.predict_proba(X)[0]    # e.g. [0.05, 0.60, 0.30, 0.05]

recommendation = LABEL_MAP[prediction]       # "Calm Down"
confidence = float(np.max(probabilities))    # 0.60
```

`predict_proba` gives the fraction of the 200 trees that voted for each class. A confidence of 0.60 means 60% of trees voted for "Calm Down".

---

## 12. Facial Emotion Detection — Dual Model System

### Why Two Models?

**DeepFace** (fallback) predicts "neutral" very frequently due to FER-2013 dataset imbalance and cannot be fine-tuned without a full retraining pipeline.

**Custom CNN** (primary): Trained on FER-2013, lighter, faster, customizable — but requires the `.h5` file to exist.

### The Dual-Layer Logic (`routers/sensors.py`)

```python
dominant, scores, confidence = _predict_with_custom_model(frame)

if dominant == "undetected":
    # CNN absent, failed, or confidence < 55% → fall back
    result = DeepFace.analyze(img_path=frame, actions=["emotion"],
                              enforce_detection=False)
    dominant = result["dominant_emotion"]
```

### Custom Model — Module-Level Caching

Early versions loaded the model from disk on every API call (500ms per request). Now it loads **once** and is cached:

```python
_custom_model = None
_custom_model_loaded = False

def _get_custom_model():
    global _custom_model, _custom_model_loaded
    if _custom_model_loaded:     # already attempted → return cached result
        return _custom_model
    # load from disk once...
    _custom_model_loaded = True
    return _custom_model
```

### Face Detection + Preprocessing

```python
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5)
faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)  # largest first

# 10% padding to match FER-2013 training data format
pad_w, pad_h = int(w * 0.1), int(h * 0.1)
roi = cv2.resize(gray[y1:y2, x1:x2], (48, 48)).astype("float32") / 255.0
roi = np.expand_dims(roi, axis=(0, -1))   # shape: (1, 48, 48, 1)
preds = model.predict(roi, verbose=0)[0]
```

**Why `enforce_detection=False`?** — If no face is detected and this is `True`, DeepFace raises an exception. With `False`, it analyzes the whole frame — no crash if user moved out of frame.

---

## 13. Scoring Engine

### Dynamic Emotion Multiplier — The Core Innovation

Every questionnaire answer is timestamp-matched to the closest camera frame:

```python
closest = min(emotions, key=lambda e: abs((e.captured_at - row.timestamp).total_seconds()))

if abs_diff <= 60:
    distress = EMOTION_DISTRESS_MAP[closest.dominant_emotion]
    multiplier = 1.0 + (distress - 0.3)
    # angry (0.8) → 1.5×  |  neutral → 0.8×  |  happy (0.0) → 0.7×

adjusted_score = min(4.0, base_score * multiplier)
```

**Why this matters:** A student clicks "I feel fine" (low score) while showing **Fear** on camera. Without multiplier — low risk. With multiplier (1.4×) — flagged as higher risk. This catches the clinical contradiction between self-report and physiological response.

### Stage Normalization
```
normalized = (raw_sum / (num_questions × 4.0)) × 4.0
```

### Student vs Teacher Weights

```
Student:  0.30×emotional + 0.20×functional + 0.10×context + 0.15×isolation
        + 0.10×cgpa_score + 0.05×attendance + 0.05×performance + 0.05×critical

Teacher:  0.30×emotional + 0.20×functional + 0.15×context + 0.15×isolation
        + 0.10×load_score + 0.05×feedback + 0.05×critical
```

---

## 14. Application Startup — Lifespan Events

FastAPI's **lifespan context manager** runs code at startup and shutdown:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.EMOTION_IMAGES_DIR, exist_ok=True)
    test_db_connection()
    load_models()           # load .pkl files into _models dict ONCE

    yield                   # application handles all requests here

    logger.info("Shutting down...")
```

**Why load at startup, not per-request?**
Each `.pkl` takes 100–500ms to load from disk. Loaded once into memory, all predictions are instant. If done per-request, every `POST /session/end` would be half a second slower.

---

## 15. Data Flow — End to End

```
USER OPENS APP
    │
    ▼ POST /auth/login
    SQL: SELECT user_id, password, role FROM Users WHERE email=?
    → JWT created (HS256, 8hr expiry)
    ← { access_token, user_id, role }
    │
    ▼ POST /session/start
    SQL: INSERT INTO Sessions OUTPUT INSERTED.session_id
    ← { session_id: 42 }
    │
    ├─ STREAM 1: Camera (every 5s)
    │    POST /sensors/emotion { image_base64, session_id, user_id }
    │    → decode → face detect → Custom CNN → DeepFace fallback
    │    SQL: INSERT EmotionImages + INSERT FacialEmotions
    │
    ├─ STREAM 2: Blood Pressure
    │    POST /sensors/bp { systolic, diastolic, pulse_rate }
    │    SQL: INSERT SensorData (data_type='bp')
    │
    └─ STREAM 3: EEG (256 Hz continuous)
         WS /ws/eeg/42 — persistent WebSocket
         buffer 50 samples → executemany INSERT SensorData (data_type='eeg')
    │
    ▼ QUESTIONNAIRE (4 stages)
    GET /questionnaire/questions/{stage}
    POST /questionnaire/submit { answers[] }
        → timestamp-match each answer to nearest emotion frame
        → apply distress multiplier
        → executemany INSERT Q_Responses
    ← { passed, next_stage }
    │
    ▼ POST /session/end
    ├─ eeg_preprocessor    → bandpass filter → FFT → stress_index
    ├─ bp_preprocessor     → mean systolic/diastolic/pulse
    ├─ emotion_preprocessor → dominant_emotion, distress_score
    ├─ questionnaire_scorer → normalized stage scores
    ├─ feature_builder     → 16-float vector
    ├─ predictor.predict() → "Calm Down", confidence=0.63
    └─ SQL: INSERT MH_Results
    ← { recommendation: "Calm Down", final_score: 1.73, confidence: 0.63 }
    │
    ▼ GET /results/{session_id}
    SQL: JOIN MH_Results + Sessions + Users
    ← Full score breakdown for user and psychologist dashboard
```

---

## Quick Concepts Reference

| Concept | What It Is | Why We Used It |
|---------|-----------|----------------|
| **FastAPI** | Python web framework | Async, auto-docs, Pydantic built-in |
| **Uvicorn** | ASGI server | Runs FastAPI, handles async + WebSocket |
| **Pydantic** | Data validation library | Auto-validates all API inputs/outputs |
| **JWT / HS256** | Stateless auth token | Works with mobile apps — no cookies needed |
| **pyodbc** | SQL Server ODBC driver | Connects Python to Microsoft SQL Server |
| **WebSocket** | Persistent TCP connection | Stream 256 Hz EEG without per-request HTTP overhead |
| **muselsl** | Muse headset CLI tool | Streams Muse EEG/PPG over LSL protocol |
| **pylsl** | LSL Python reader | Reads EEG/PPG streams published by muselsl |
| **LSL** | Lab Streaming Layer | Neuroscience real-time data streaming standard |
| **bleak** | Bluetooth LE library | Reads BP cuff via BLE GATT notifications |
| **GATT UUID 0x2A35** | BLE standard | International standard UUID for blood pressure measurement |
| **OpenCV** | Computer vision library | Decodes images, Haar cascade face detection |
| **DeepFace** | Emotion detection library | Pre-trained facial emotion recognition (fallback) |
| **TensorFlow/Keras** | Deep learning framework | Runs our custom CNN emotion model |
| **Butterworth filter** | Signal filter | Removes EEG noise outside 1–40 Hz band |
| **FFT** | Fast Fourier Transform | Converts EEG from time domain to frequency bands |
| **RandomForest** | ML ensemble algorithm | Classifies stress from 16 features using 200 trees |
| **joblib** | Python serialization | Save and load trained `.pkl` model files |
| **pydantic-settings** | Config management | Reads `.env` file into a typed Python class |
| **CORS Middleware** | HTTP header policy | Allows Flutter/React apps to call the API |
| **OUTPUT INSERTED** | T-SQL syntax | Returns auto-generated IDs immediately after INSERT |
| **executemany()** | Batch SQL operation | Insert N rows in one DB round trip — much more efficient |
| **FER-2013** | Training dataset | 35,000 facial images across 7 emotion classes |
| **EEG Band Powers** | Frequency band analysis | Alpha/Beta/Theta indicate different mental states |
| **Stress Index** | (Beta+Theta)/Alpha | Standard neuroscience formula for cognitive stress |
| **BASE_DIR** | Absolute path anchor | Ensures ML model paths resolve correctly from any directory |
| **autocommit=False** | Transaction control | Prevents partial data saves on errors |
