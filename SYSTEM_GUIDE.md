# Multimodal Virtual Clinic — System Guide

## Table of Contents
1. [What the System Does](#1-what-the-system-does)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Folder Structure](#5-folder-structure)
6. [Setup & Running](#6-setup--running)
7. [Session Lifecycle](#7-session-lifecycle)
8. [API Reference](#8-api-reference)
9. [ML Pipeline](#9-ml-pipeline)
10. [Preprocessing Modules](#10-preprocessing-modules)
11. [Hardware Integration](#11-hardware-integration)
12. [Scoring Formulas](#12-scoring-formulas)

---

## 1. What the System Does

A university mental health assessment platform. A **student or teacher** opens a mobile/web app, fills out a 5-stage psychological questionnaire, and while answering, three data streams are collected silently:

| Stream | Source | How |
|--------|--------|-----|
| Facial emotion | Device camera (every 5 sec) | Base64 JPEG → Custom CNN / DeepFace fallback |
| EEG + Heart Rate | Muse 2 headset | Bluetooth → muselsl → WebSocket |
| Blood Pressure | BLE BP cuff | Bluetooth BLE → REST API |

When the questionnaire ends, all four sources are **fused by an ML model** to output one of:

| ML Label | DB `risk_class` | Meaning |
|----------|-----------------|---------|
| `Normal` | `Healthy` | No action needed |
| `Calm Down` | `Mild Stress` | Suggest breathing/relaxation |
| `See Psychologist` | `High Risk` | Recommend professional help |
| `Emergency` | `Critical Risk` | Immediate intervention required |

Two separate models exist — **one for students, one for teachers** — because their stress factors differ.

---

## 2. System Architecture

```
CLIENT LAYER
  Any frontend (Flutter / React / etc.)
       |
       | REST API (JSON) + WebSocket (EEG)
       v
BACKEND LAYER — Python FastAPI (port 8000)
  /auth          Login, JWT tokens
  /session       Start/End session, get details
  /questionnaire Submit stage answers, get questions
  /sensors       BP, Pulse (PPG), Emotion frames
  /results       Final recommendation + score breakdown
  ws:/ws/eeg     WebSocket — continuous EEG stream
       |
PROCESSING LAYER
  Preprocessing Pipeline
    EEG raw → bandpass filter → band powers → stress index
    BP readings → mean systolic/diastolic
    PPG/heart rate → mean HR
    Facial emotions → dominant emotion + distress score
    Questionnaire → weighted stage scores (with emotion multiplier)
  ML Models
    model_student.pkl  RandomForestClassifier
    model_teacher.pkl  RandomForestClassifier
    Custom CNN         Optional trained on FER-2013
    DeepFace           Fallback emotion detection
       |
DATABASE LAYER — Microsoft SQL Server (VirtualClinicDB)
  Users, Students, Teachers, Sessions
  SensorData, FacialEmotions, EmotionImages
  Q_Stages, Q_Questions, Q_Responses
  MH_Results
```

---

## 3. Technology Stack

### Backend
| Package | Purpose |
|---------|---------|
| `fastapi` | REST API + WebSocket framework |
| `uvicorn` | ASGI server |
| `pyodbc` | SQL Server connection (ODBC Driver 17) |
| `python-jose[cryptography]` | JWT tokens |
| `pydantic-settings` | Settings from `.env` |

### ML / AI
| Package | Purpose |
|---------|---------|
| `deepface` | Facial emotion detection (pre-trained fallback) |
| `tensorflow` | Custom CNN emotion model |
| `scikit-learn` | RandomForestClassifier for student/teacher models |
| `joblib` | Save/load `.pkl` model files |
| `opencv-python` | Image decode and face detection |
| `numpy` / `scipy` | EEG signal filtering & FFT |
| `pandas` | Synthetic data generation for training |

### Hardware
| Package | Purpose |
|---------|---------|
| `muselsl` | CLI — streams Muse headset via LSL protocol |
| `pylsl` | Python — reads EEG/PPG streams from muselsl |
| `bleak` | Python BLE client — reads BP cuff |

---

## 4. Database Schema

> **To set up:** Run `database/schema.sql` in SSMS, then run `python db_migrations.py`.

### Core Tables

```sql
Users        (user_id PK, name, email, password, role)
             -- role: 'student' | 'teacher' | 'psychologist'
             -- Pre-seeded accounts — no registration endpoint

Students     (student_id PK, user_id FK → Users, cgpa_trend, attendance_drop)

Teachers     (teacher_id PK, user_id FK → Users, workload_hrs, class_count)

Sessions     (session_id PK, user_id FK, start_time, end_time)

SensorData   (sensor_id PK, session_id FK, pulse_rate, eeg_value,
              bp_systolic, bp_diastolic, data_type, recorded_at)
              -- CHECK: data_type IN ('eeg', 'ppg', 'bp', 'emotion')
              -- NOTE: use 'ppg' for pulse readings — NOT 'pulse'

FacialEmotions (emotion_id PK, session_id FK, dominant_emotion,
                happy, sad, angry, fear, surprise, disgust, neutral,
                captured_at, image_id FK, stage_number)

EmotionImages  (image_id PK, user_id FK, session_id FK,
                stage_number, image_name, captured_at)

Q_Stages     (stage_id PK, stage_number, stage_name, target_role, threshold)

Q_Questions  (question_id PK, stage_id FK, question_text, weight)

Q_Responses  (response_id PK, session_id FK, question_id FK,
              stage_number, response_choice, cal_score, timestamp)
```

### MH_Results Table

```sql
MH_Results (
  result_id        INT IDENTITY PK,
  session_id       INT FK → Sessions,
  user_id          INT NOT NULL,
  emotional_score  FLOAT,
  functional_score FLOAT,
  context_score    FLOAT,
  isolation_score  FLOAT,
  critical_score   FLOAT,
  eeg_avg          FLOAT,
  avg_pulse        FLOAT,
  avg_bp_systolic  FLOAT,
  dominant_emotion VARCHAR,
  final_score      FLOAT,
  risk_class       VARCHAR,  -- CHECK: 'Healthy'|'Mild Stress'|'Moderate Risk'|'High Risk'|'Critical Risk'
  calculated_at    DATETIME DEFAULT GETDATE()
)
```

### ML Label → risk_class Mapping

| ML Output | Stored in DB |
|-----------|-------------|
| Normal | Healthy |
| Calm Down | Mild Stress |
| See Psychologist | High Risk |
| Emergency | Critical Risk |

---

## 5. Folder Structure

```
Backend/
├── main.py                    App entry point, router registration, startup/shutdown
├── config.py                  All settings (DB, JWT, paths, BASE_DIR)
├── database.py                get_connection(), test_connection(), db_cursor()
├── db_migrations.py           Idempotent schema migrations (safe to re-run)
├── start_server.ps1           Windows launcher — prints LAN IP, starts uvicorn
├── requirements.txt
├── test_endpoints.py          API integration test suite
│
├── models/                    Pydantic request/response schemas
│   ├── user_models.py         LoginRequest, LoginResponse
│   ├── session_models.py
│   ├── questionnaire_models.py
│   ├── sensor_models.py
│   └── result_models.py
│
├── routers/                   FastAPI route handlers
│   ├── auth.py                POST /auth/login
│   ├── sessions.py            POST /session/start, /session/end; GET /session/{id}
│   ├── questionnaire.py       POST /questionnaire/submit; GET /questionnaire/...
│   ├── sensors.py             POST /sensors/bp, /sensors/pulse, /sensors/emotion
│   └── results.py             GET /results/{session_id}, /results/user/{id}, /results/all
│
├── ml/
│   ├── feature_builder.py     Assembles 16-element feature vector from all sources
│   ├── predictor.py           Loads models at startup, predict(features, role)
│   ├── trainer.py             Generates synthetic data, trains & saves models
│   ├── train_custom_emotion.py Train a custom CNN on FER-2013 dataset
│   └── saved_models/
│       ├── model_student.pkl        (run: python -m ml.trainer)
│       ├── model_teacher.pkl        (run: python -m ml.trainer)
│       ├── custom_emotion_model.h5  (run: python ml/train_custom_emotion.py)
│       └── emotion_classes.txt
│
├── preprocessing/
│   ├── eeg_preprocessor.py    Bandpass filter → FFT → band powers → stress index
│   ├── bp_preprocessor.py     Mean BP
│   └── emotion_preprocessor.py Dominant emotion + distress score from FacialEmotions
│
├── scoring/
│   ├── questionnaire_scorer.py Stage normalization, emotion multiplier, weighted formulas
│   └── risk_engine.py          Additional risk classification logic
│
├── hardware/
│   ├── eeg_stream.py           pylsl inlet for EEG and PPG streams
│   └── bp_reader.py            bleak BLE reader for BP cuff
│
├── websocket/
│   └── eeg_handler.py          Async WebSocket handler — buffers 50 EEG samples → DB
│
├── utils/
│   ├── auth_utils.py           JWT create/decode, FastAPI get_current_user dependency
│   ├── response_utils.py       Standard response wrapper helpers
│   └── time_utils.py           now_utc() helper
│
├── database/
│   └── schema.sql              Full SQL Server schema — run this first in SSMS
│
└── emotion_images/             Auto-created at startup; stores JPEG frames from camera
```

---

## 6. Setup & Running

### Step 1 — Clone & Create Virtual Environment
```bash
git clone https://github.com/imhasnain/FYP-Backend.git
cd FYP-Backend
python -m venv venv
.\venv\Scripts\activate   # Windows PowerShell
```

### Step 2 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Create `.env` File
Create a `.env` file in the project root (never commit this):
```env
DB_SERVER=localhost
DB_NAME=VirtualClinicDB
DB_TRUSTED_CONNECTION=true
SECRET_KEY=your-long-random-secret-key
```

For SQL Server Authentication (instead of Windows Auth):
```env
DB_TRUSTED_CONNECTION=false
DB_USER=your_username
DB_PASSWORD=your_password
```

### Step 4 — Set Up Database
Open SSMS → New Query → paste and run `database/schema.sql`. Then run migrations:
```bash
python db_migrations.py
```

### Step 5 — Train ML Models
```bash
python -m ml.trainer
```
Generates synthetic data, trains two RandomForest classifiers, saves to `ml/saved_models/`. Takes ~2 minutes.

### Step 6 — (Optional) Train Custom Emotion Model
```bash
# Download FER-2013 from Kaggle, place images at ml/dataset/train/ and ml/dataset/test/
python ml/train_custom_emotion.py
```

### Step 7 — Start the Server

**Windows (recommended):**
```powershell
.\start_server.ps1
```
This prints your LAN IP for use in your frontend's API base URL.

**Manual:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 8 — Verify
```
GET http://localhost:8000/health
→ { "db_connected": true, "models_loaded": true }
```

### Step 9 — Run Tests
```bash
python test_endpoints.py
```

---

## 7. Session Lifecycle

```
1. User opens app
   → POST /auth/login { email, password }
   ← { access_token, user_id, role }

2. App starts a session
   → POST /session/start { user_id }
   ← { session_id, started_at }

3. Three parallel data streams begin:

   📷 Camera loop (every 5 seconds)
      App captures frame → base64 JPEG → POST /sensors/emotion
      Server: decode → save JPEG → Custom CNN (if trained)
              → DeepFace fallback if CNN is absent/low-confidence
              → INSERT EmotionImages + FacialEmotions

   💓 BP cuff (on user trigger)
      BLE notification → POST /sensors/bp { session_id, systolic, diastolic }
      → INSERT SensorData (data_type='bp')

   🧠 EEG stream (continuous, if Muse connected)
      muselsl stream → pylsl → WS /ws/eeg/{session_id}
      → eeg_handler buffers 50 samples → batch INSERT SensorData (data_type='eeg')

4. Questionnaire (4 active stages)
   GET /questionnaire/questions/{stage_number}
   User answers → POST /questionnaire/submit { session_id, stage_number, answers[] }
   ← { total_score, passed, next_stage }
   If passed → next stage shown. If failed → session can still be ended.

5. App ends the session
   → POST /session/end { session_id, user_id }

   Server pipeline:
     a. Mark Sessions.end_time = NOW
     b. Get user role
     c. eeg_preprocessor   → alpha/theta/beta powers + stress_index
     d. bp_preprocessor    → mean_systolic, mean_diastolic, mean_pulse
     e. emotion_preprocessor → dominant_emotion, emotion_distress_score
     f. questionnaire_scorer  → normalized stage scores (with emotion multiplier)
     g. feature_builder   → 16-float vector assembled
     h. predictor.predict(features, role) → recommendation + confidence
     i. INSERT MH_Results

   ← { recommendation, final_score, confidence, ended_at }

6. App shows result screen
   → GET /results/{session_id}
   ← Full score breakdown

   Psychologist dashboard:
   → GET /results/all?role=student&limit=50
```

---

## 8. API Reference

### Authentication
```
POST /auth/login
Body:  { "email": "student@clinic.com", "password": "student123" }
→     { "access_token": "...", "token_type": "bearer", "user_id": 1, "role": "student" }
```

Pre-seeded accounts (no registration — accounts are set up in the DB):

| Email | Password | Role |
|-------|----------|------|
| `student@clinic.com` | `student123` | student |
| `teacher@clinic.com` | `teacher123` | teacher |
| `psychologist@clinic.com` | `psych123` | psychologist |

### Sessions
```
POST /session/start
Body:  { "user_id": 1 }
→     { "session_id": 5, "started_at": "2026-05-01T12:00:00Z" }

POST /session/end
Body:  { "session_id": 5, "user_id": 1 }
→     { "session_id": 5, "recommendation": "Calm Down",
        "final_score": 1.73, "confidence": 0.63, "ended_at": "..." }

GET  /session/{session_id}
→    { "session_id", "user_id", "status", "start_time", "end_time",
       "eeg_count", "bp_count", "emotion_count", "questionnaire_stages" }
```

### Questionnaire
```
GET  /questionnaire/stages
→    [ { "stage_id", "stage_number", "stage_name", "target_role", "threshold" } ]

GET  /questionnaire/questions/{stage_number}
→    [ { "question_id", "stage_id", "question_text", "weight" } ]

POST /questionnaire/submit
Body: {
  "session_id": 5,
  "stage_number": 1,
  "answers": [
    { "question_id": 1, "response_choice": "Often", "cal_score": 3.0 },
    ...
  ]
}
→    { "stage_number": 1, "total_score": 16.0, "passed": true,
       "next_stage": 2, "message": "..." }
```

### Sensors
```
POST /sensors/emotion
Body:  { "session_id": 5, "user_id": 1, "stage_number": 2, "image_base64": "..." }
→     { "session_id", "dominant_emotion": "happy",
        "scores": { "happy": 78.3, "neutral": 12.1, ... }, "captured_at": "..." }

POST /sensors/bp
Body:  { "session_id": 5, "systolic": 125, "diastolic": 82, "pulse_rate": 74 }
→     { "session_id", "systolic", "diastolic", "pulse_rate", "recorded_at" }

POST /sensors/pulse
Body:  { "session_id": 5, "pulse_rate": 74, "source": "muse" }
       -- source must be "muse" or "bp_machine"
→     { "session_id", "pulse_rate", "source", "recorded_at" }
```

### Results
```
GET  /results/{session_id}
→    { "session_id", "user_id", "user_role", "recommendation",
       "confidence", "final_score",
       "score_breakdown": {
         "emotional", "functional", "context", "isolation", "critical",
         "eeg_stress_index", "hr_mean", "bp_avg", "dominant_emotion",
         "emotion_distress_score"
       },
       "session_duration_minutes", "calculated_at" }

GET  /results/user/{user_id}
→    { "user_id", "sessions": [ { "session_id", "recommendation", "final_score", ... } ] }

GET  /results/all?role=student&recommendation=Emergency&limit=50
→    [ { "result_id", "session_id", "user_id", "user_role",
         "recommendation", "final_score", "calculated_at" } ]
```

### WebSocket — EEG
```
WS  /ws/eeg/{session_id}
Client sends JSON every ~10ms:
  { "session_id": 5, "eeg_channels": [ch1, ch2, ch3, ch4], "timestamp": 1700000000.0 }
Server buffers 50 readings → batch INSERT SensorData (data_type='eeg')
Server replies: { "received": 50, "status": "ok" }
```

---

## 9. ML Pipeline

### Feature Vector — 16 elements (same for both roles)

| Index | Feature | Student | Teacher |
|-------|---------|---------|---------|
| 0 | emotional_score | Stage 1 normalized | Stage 1 normalized |
| 1 | functional_score | Stage 2 normalized | Stage 2 normalized |
| 2 | context_score | Stage 3 normalized | Stage 3 normalized |
| 3 | isolation_score | Stage 4 normalized | Stage 4 normalized |
| 4 | critical_score | Stage 5 (0 if skipped) | Stage 5 |
| 5 | role_specific_1 | cgpa_trend | workload_hrs |
| 6 | role_specific_2 | attendance_drop | class_count |
| 7 | role_specific_3 | performance_decline | 0.0 |
| 8 | eeg_stress_index | (beta+theta)/alpha | same |
| 9 | eeg_alpha_power | FFT band power | same |
| 10 | eeg_theta_power | FFT band power | same |
| 11 | hr_mean | mean pulse_rate | same |
| 12 | bp_mean_systolic | from SensorData | same |
| 13 | bp_mean_diastolic | from SensorData | same |
| 14 | pulse_avg | from SensorData | same |
| 15 | emotion_distress_score | 0.0=happy → 1.0=angry | same |

### Model Config
- **Algorithm**: `RandomForestClassifier(n_estimators=200, max_depth=15)`
- **Training data**: 5000 synthetic samples per role (1250 per class)
- **Split**: 80% train / 20% test
- **Classes**: 0=Normal, 1=Calm Down, 2=See Psychologist, 3=Emergency

### Emotion Detection (Dual-Layer)
1. **Custom CNN** (`ml/saved_models/custom_emotion_model.h5`) — FER-2013 trained, 48×48 grayscale. Used if confidence > 55%.
2. **DeepFace** — Fallback if custom model is absent, fails, or is low confidence.

### Rule-Based Fallback
If model `.pkl` files are not found:
```
q_score = 0.30*emotional + 0.25*functional + 0.15*context + 0.20*isolation + 0.10*critical
q_score += emotion_distress * 0.5   (capped at 4.0)

0.0–1.0 → Normal
1.0–2.0 → Calm Down
2.0–3.5 → See Psychologist
3.5–4.0 → Emergency
```

---

## 10. Preprocessing Modules

### EEG (`preprocessing/eeg_preprocessor.py`)
```
1. Load SensorData rows (data_type='eeg') for session, ordered by recorded_at
2. Bandpass filter: 1–40 Hz using scipy.signal.butter (order=4) + sosfilt
3. FFT → power spectral density
4. Extract band powers:
     Delta: 1–4 Hz   (deep sleep)
     Theta: 4–8 Hz   (drowsiness)
     Alpha: 8–13 Hz  (relaxed alertness)
     Beta:  13–30 Hz (stress, active thinking)
5. Stress index = (beta_power + theta_power) / alpha_power
6. Returns: { alpha_power, theta_power, beta_power, delta_power, stress_index }
   Returns all zeros if < 2 EEG samples available.
```

### BP (`preprocessing/bp_preprocessor.py`)
```
1. Load SensorData rows (data_type='bp') for session
2. Compute: mean_systolic, mean_diastolic, mean_pulse
3. Returns: { mean_systolic, mean_diastolic, mean_pulse }
   Returns None values if no BP readings.
```

### Emotion (`preprocessing/emotion_preprocessor.py`)
```
1. Load FacialEmotions rows for session
2. Count frequency of each dominant_emotion label
3. Dominant = most frequent label
4. Distress = confidence-weighted average of EMOTION_DISTRESS_MAP values

EMOTION_DISTRESS_MAP:
  happy=0.0, neutral=0.1, surprise=0.2, disgust=0.4,
  fear=0.7,  sad=0.7,    angry=0.8,   undetected=0.3
```

---

## 11. Hardware Integration

### Muse EEG Headset (Muse 2 / Muse S)
- Connect headset via Bluetooth to laptop
- Run: `muselsl stream --ppg` (must be running before the session starts)
- Streams two LSL feeds:
  - `type='EEG'` — 4 channels (TP9, AF7, AF8, TP10) at 256 Hz
  - `type='PPG'` — photoplethysmography (heart rate) at 64 Hz
- EEG → WebSocket `/ws/eeg/{session_id}`
- PPG → `POST /sensors/pulse`

### BP Cuff (Omron BLE)
- Bluetooth Low Energy, standard GATT UUID: `00002a35-0000-1000-8000-00805f9b34fb`
- User presses button → BLE notification received
- `hardware/bp_reader.py` uses `bleak` to scan, connect, receive notification
- Reading → `POST /sensors/bp`

### Camera (Emotion)
- App captures frame every 5 seconds using device camera
- Frame encoded as base64 JPEG → `POST /sensors/emotion`
- Server: decode → OpenCV → save to `emotion_images/` → Custom CNN / DeepFace
- `enforce_detection=False` — no crash if no face is visible

> **Note:** All hardware is optional. If no sensor data is collected, the ML model scores based on questionnaire answers + whatever emotion frames were captured.

---

## 12. Scoring Formulas

### Dynamic Emotion Multiplier
When a user submits a questionnaire answer, the scorer finds the closest camera frame captured within 60 seconds. The base score for that question is multiplied:

| Emotion | Distress | Multiplier |
|---------|----------|------------|
| Happy | 0.0 | 0.7× (lowers risk) |
| Neutral / Undetected | 0.1 / 0.3 | ~1.0× |
| Fear / Sad | 0.7 | 1.4× |
| Angry | 0.8 | 1.5× |

This allows the system to flag contradictions — e.g. clicking "I'm fine" while showing Fear raises that question's risk score.

### Stage Normalization
```
normalized = (raw_sum / (num_questions × 4)) × 4
```

### Student Final Score
```
final = 0.30 × emotional  + 0.20 × functional + 0.10 × context
      + 0.15 × isolation  + 0.10 × cgpa_score
      + 0.05 × attendance + 0.05 × performance + 0.05 × critical

cgpa_score  = min(4, max(0, -cgpa_trend) × 2)
attendance  = min(4, max(0, attendance_drop) × 0.5)
performance = min(4, (failed_courses / total_courses) × 4)
```

### Teacher Final Score
```
final = 0.30 × emotional  + 0.20 × functional + 0.15 × context
      + 0.15 × isolation  + 0.10 × load_score
      + 0.05 × fb_score   + 0.05 × critical

load_score = min(4, (workload_hrs / 5.0) × 4)
fb_score   = min(4, max(0, -feedback_trend) × 2)
```

---

## Quick Reference

```bash
# Set up DB (first time)
# → Run database/schema.sql in SSMS
python db_migrations.py

# Train ML models
python -m ml.trainer

# Train custom emotion model (optional — needs FER-2013 dataset)
python ml/train_custom_emotion.py

# Start backend (Windows)
.\start_server.ps1

# Start backend (manual)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run API tests
python test_endpoints.py

# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```
