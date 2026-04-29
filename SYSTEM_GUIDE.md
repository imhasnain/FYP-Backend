# Multimodal Virtual Clinic — Complete System Guide

## Table of Contents
1. [What the System Does](#1-what-the-system-does)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Folder Structure](#5-folder-structure)
6. [Setup & Running](#6-setup--running)
7. [Session Lifecycle (Full Workflow)](#7-session-lifecycle-full-workflow)
8. [API Reference](#8-api-reference)
9. [ML Pipeline](#9-ml-pipeline)
10. [Preprocessing Modules](#10-preprocessing-modules)
11. [Hardware Integration](#11-hardware-integration)
12. [Scoring Formulas](#12-scoring-formulas)
13. [Key Fixes & DB Constraints](#13-key-fixes--db-constraints)
14. [Test Suite](#14-test-suite)

---

## 1. What the System Does

A university mental health assessment platform. A **student or teacher** opens a Flutter mobile app or React web app, fills out a 5-stage psychological questionnaire, and while answering, three data streams are collected silently:

| Stream | Source | How |
|--------|--------|-----|
| Facial emotions | Webcam (every 5 sec) | Base64 JPEG → DeepFace |
| EEG + Heart Rate | Muse 2 headset | Bluetooth → muselsl → WebSocket |
| Blood Pressure | BLE BP cuff | Bluetooth BLE → REST API |

When the questionnaire ends, all four sources are **fused by a ML model** to output one of:

| Label | Meaning |
|-------|---------|
| `Normal` / `Healthy` | No action needed |
| `Calm Down` / `Mild Stress` | Suggest breathing/relaxation |
| `See Psychologist` / `High Risk` | Recommend professional help |
| `Emergency` / `Critical Risk` | Immediate intervention required |

Two separate models exist — **one for students, one for teachers** — because their stress factors differ.

---

## 2. System Architecture

```
CLIENT LAYER
  Flutter App (mobile) / React Web App
       |
       | REST API (JSON) + WebSocket (EEG)
       v
BACKEND LAYER — Python FastAPI (port 8000)
  /auth          Login, Register, JWT tokens
  /session       Start/End session, get details
  /questionnaire Submit stage answers, get questions
  /sensors       BP, Pulse (PPG), Emotion frames
  /results       Final recommendation + score breakdown
  ws:/ws/eeg     WebSocket — continuous EEG stream
       |
PROCESSING LAYER
  Preprocessing Pipeline
    EEG raw → bandpass filter → band powers → stress index
    BP readings → mean systolic/diastolic → hypertension flag
    PPG/heart rate → mean HR
    Facial emotions → dominant emotion + distress score
    Questionnaire → weighted stage scores
  ML Models
    model_student.pkl  RandomForestClassifier (99.8% accuracy)
    model_teacher.pkl  RandomForestClassifier (99.8% accuracy)
    DeepFace           Pre-trained emotion detection
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
| `passlib[bcrypt]` | Password hashing |
| `pydantic` | Request/response validation |

### ML / AI
| Package | Purpose |
|---------|---------|
| `deepface` | Facial emotion detection (pre-trained) |
| `scikit-learn` | RandomForestClassifier for student/teacher models |
| `joblib` | Save/load .pkl model files |
| `numpy` / `scipy` | EEG signal filtering & FFT |
| `pandas` | Synthetic data generation for training |

### Hardware
| Package | Purpose |
|---------|---------|
| `muselsl` | CLI — streams Muse headset via LSL protocol |
| `pylsl` | Python — reads EEG/PPG streams from muselsl |
| `bleak` | Python BLE client — reads BP cuff |
| `opencv-python` | Webcam frame decode |

---

## 4. Database Schema

### Core Tables (pre-existing)

```sql
Users        (user_id PK, name, email, password, role)
             role: 'student' | 'teacher' | 'psychologist'

Students     (student_id PK → Users.user_id,
              user_id, cgpa_trend, attendance_drop)

Teachers     (teacher_id PK → Users.user_id,
              user_id, workload_hrs, class_count)

Sessions     (session_id PK, user_id FK, start_time, end_time)

SensorData   (sensor_id PK, session_id FK, pulse_rate,
              eeg_value, stress_lvl, heart_rate,
              recorded_at, bp_systolic, bp_diastolic,
              data_type)
              -- CHECK: data_type IN ('eeg','ppg','bp','emotion')

FacialEmotions (emotion_id PK, session_id FK,
                dominant_emotion, happy, sad, angry,
                fear, surprise, disgust, neutral,
                captured_at, image_id FK)

EmotionImages  (image_id PK, user_id FK, session_id FK,
                image_name, captured_at)

Q_Stages     (stage_id PK, stage_number, stage_name,
              target_role, threshold)

Q_Questions  (question_id PK, stage_id FK,
              question_text, weight)

Q_Responses  (response_id PK, session_id FK, question_id FK,
              stage_number, response_choice, cal_score, timestamp)
```

### MH_Results Table (created by db_migrations.py)

```sql
MH_Results (
  result_id        INT IDENTITY PK,
  session_id       INT FK → Sessions,
  user_id          INT NOT NULL,
  emotional_score  FLOAT NOT NULL,
  functional_score FLOAT NOT NULL,
  context_score    FLOAT NOT NULL,
  isolation_score  FLOAT NOT NULL,
  critical_score   FLOAT NOT NULL,
  final_score      FLOAT NOT NULL,
  risk_class       VARCHAR NOT NULL,
  -- CHECK: risk_class IN ('Healthy','Mild Stress','Moderate Risk',
  --                       'High Risk','Critical Risk')
  user_role        VARCHAR,    -- 'student' | 'teacher'
  performance_score FLOAT,
  eeg_stress_index  FLOAT,
  eeg_alpha_power   FLOAT,
  eeg_theta_power   FLOAT,
  hr_mean           FLOAT,
  bp_avg_systolic   FLOAT,
  bp_avg_diastolic  FLOAT,
  pulse_avg         FLOAT,
  dominant_emotion  VARCHAR,
  emotion_distress_score FLOAT,
  recommendation    VARCHAR,   -- human-readable label
  confidence        FLOAT,
  calculated_at     DATETIME DEFAULT GETDATE()
)
```

### Recommendation → risk_class Mapping

| ML Output | risk_class stored in DB |
|-----------|------------------------|
| Normal | Healthy |
| Calm Down | Mild Stress |
| See Psychologist | High Risk |
| Emergency | Critical Risk |

---

## 5. Folder Structure

```
Backend/
├── main.py                    App entry point, router registration, startup
├── config.py                  All settings (DB, JWT, paths)
├── database.py                get_connection(), test_connection(), db_cursor()
├── db_migrations.py           Idempotent schema migrations (safe to re-run)
├── requirements.txt
├── test_endpoints.py          13-step API integration test suite
│
├── models/                    Pydantic request/response schemas
│   ├── auth_models.py
│   ├── session_models.py
│   ├── questionnaire_models.py
│   ├── sensor_models.py
│   └── result_models.py
│
├── routers/                   FastAPI route handlers
│   ├── auth.py                POST /auth/register, /auth/login
│   ├── sessions.py            POST /session/start, /session/end; GET /session/{id}
│   ├── questionnaire.py       POST /questionnaire/submit; GET /questionnaire/...
│   ├── sensors.py             POST /sensors/bp, /sensors/pulse, /sensors/emotion
│   └── results.py             GET /results/{session_id}, /results/user/{id}, /results/all
│
├── ml/
│   ├── feature_builder.py     Assembles 16-element feature vector from all sources
│   ├── predictor.py           Loads models at startup, predict(features, role)
│   ├── trainer.py             Generates synthetic data, trains & saves models
│   └── saved_models/
│       ├── model_student.pkl  (generated by: python -m ml.trainer)
│       └── model_teacher.pkl
│
├── preprocessing/
│   ├── eeg_preprocessor.py    Bandpass filter → FFT → band powers → stress index
│   ├── bp_preprocessor.py     Mean BP, hypertension flag
│   └── emotion_preprocessor.py Dominant emotion + distress score from FacialEmotions
│
├── scoring/
│   ├── questionnaire_scorer.py Stage score normalization + weighted formula
│   └── risk_engine.py         Rule-based risk classification
│
├── hardware/
│   ├── eeg_stream.py          pylsl inlet for EEG and PPG streams
│   └── bp_reader.py           bleak BLE reader for BP cuff
│
├── websocket/
│   └── eeg_handler.py         Async WebSocket handler — buffers 50 EEG samples → DB
│
├── utils/
│   ├── auth_utils.py          hash_password, verify_password, JWT create/verify
│   ├── response_utils.py      Standard {status, message, data} wrapper
│   └── time_utils.py          now_utc() helper
│
└── emotion_images/            Auto-created; stores JPEG frames from webcam
```

---

## 6. Setup & Running

### Step 1 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Configure Database
Edit `.env` or `config.py`:
```
DB_SERVER   = your_sql_server_name
DB_NAME     = VirtualClinicDB
DB_USER     = your_username
DB_PASSWORD = your_password
DB_DRIVER   = ODBC Driver 17 for SQL Server
SECRET_KEY  = your_jwt_secret_key
```

### Step 3 — Run DB Migrations (once, safe to repeat)
```bash
python db_migrations.py
```
This adds new columns to `SensorData`, `Q_Responses` and creates `MH_Results`, `EmotionImages` tables if missing.

### Step 4 — Train ML Models (once)
```bash
python -m ml.trainer
```
Generates 5000 synthetic samples per role, trains RandomForest (200 trees), saves to `ml/saved_models/`. Takes ~2 minutes. Expected accuracy: ~99.8%.

### Step 5 — Start EEG Stream (if hardware connected)
```bash
muselsl stream --ppg
```
Must be running before the backend starts if you want real EEG data.

### Step 6 — Start the Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 7 — Verify Everything Works
```
GET http://localhost:8000/health
→ { "db_connected": true, "models_loaded": true, "server": "running" }
```

### Step 8 — Run Integration Tests
```bash
python test_endpoints.py
```
Expected: `13/13 passed`

---

## 7. Session Lifecycle (Full Workflow)

```
STEP 1 — User opens app → POST /auth/login → receives JWT token

STEP 2 — App calls POST /session/start
         → Server inserts row in Sessions table
         → Returns session_id

STEP 3 — Three parallel data streams begin:
         a. Camera loop (every 5s):
               App captures webcam frame
               → encodes as base64 JPEG
               → POST /sensors/emotion
               → Server: decode → save JPEG → DeepFace.analyze()
               → INSERT into EmotionImages + FacialEmotions
         b. BP cuff (on user press):
               BLE notification → app or server reads it
               → POST /sensors/bp
               → INSERT into SensorData (data_type='bp')
         c. EEG stream (continuous):
               muselsl → pylsl → backend hardware/eeg_stream.py
               → WebSocket ws:/ws/eeg/{session_id}
               → eeg_handler.py buffers 50 samples → batch INSERT SensorData

STEP 4 — Questionnaire stages shown one by one:
         Stage 1 (6 questions) → POST /questionnaire/submit
         If score >= threshold → Stage 2 shown
         Stage 2 (5 questions) → POST /questionnaire/submit
         Stage 3 branching:
           Students get academic stress questions
           Teachers get workload questions
         Stage 4 (isolation/social risk)
         Stage 5 (critical screening — only if Stage 4 score >= 6
                  OR student cgpa_trend < -0.5
                  OR teacher feedback declining)

STEP 5 — User finishes → App calls POST /session/end
         Server pipeline runs:
           a. Mark Sessions.end_time = NOW
           b. Get user role from Users table
           c. eeg_preprocessor → { alpha_power, theta_power,
                                    beta_power, stress_index }
           d. bp_preprocessor  → { mean_systolic, mean_diastolic,
                                    mean_pulse, hypertension_flag }
           e. emotion_preprocessor → { dominant_emotion,
                                        emotion_distress_score }
           f. questionnaire_scorer  → { stage scores normalized 0-4 }
           g. feature_builder → assemble 16-float vector
           h. predictor.predict(features, role) → recommendation + confidence
           i. INSERT into MH_Results
           j. Return { recommendation, final_score, confidence, ended_at }

STEP 6 — App displays result screen
         GET /results/{session_id} → full score breakdown
         Psychologist views GET /results/all for all sessions
```

---

## 8. API Reference

### Auth
```
POST /auth/register
Body:  { name, email, password, role }
→     { user_id, message }

POST /auth/login
Body:  { email, password }
→     { access_token, token_type, user_id, role, name }
```

### Sessions
```
POST /session/start
Body:  { user_id }
→     { session_id, started_at }

POST /session/end
Body:  { session_id, user_id }
→     { session_id, recommendation, final_score, confidence, ended_at }
       [triggers full ML pipeline]

GET  /session/{session_id}
→    { session_id, user_id, status, start_time, end_time,
       eeg_count, bp_count, emotion_count, questionnaire_stages }
```

### Questionnaire
```
POST /questionnaire/submit
Body:  { session_id, stage_number,
         answers: [{ question_id, response_choice, cal_score }] }
→     { stage_number, total_score, passed, next_stage, message }

GET  /questionnaire/stages
→    [ { stage_id, stage_number, stage_name, target_role, threshold } ]

GET  /questionnaire/questions/{stage_number}
→    [ { question_id, stage_id, question_text, weight } ]
```

### Sensors
```
POST /sensors/bp
Body:  { session_id, systolic, diastolic, pulse_rate }
→     { session_id, systolic, diastolic, pulse_rate, recorded_at }

POST /sensors/pulse
Body:  { session_id, pulse_rate, source="muse" }
→     { session_id, pulse_rate, source, recorded_at }

POST /sensors/emotion
Body:  { session_id, user_id, image_base64 }
→     { session_id, dominant_emotion, scores:{emotion:confidence}, captured_at }
```

### Results
```
GET  /results/{session_id}
→    { session_id, user_id, user_role, recommendation, confidence,
       final_score, score_breakdown:{...}, session_duration_minutes,
       calculated_at }

GET  /results/user/{user_id}
→    { user_id, sessions: [ {session_id, recommendation, final_score, ...} ] }

GET  /results/all?role=student&recommendation=Emergency&limit=50
→    [ { result_id, session_id, user_id, user_role,
          recommendation, final_score, confidence, calculated_at } ]
```

### WebSocket
```
WS  /ws/eeg/{session_id}
Client sends JSON every ~10ms:
  { "session_id": 1, "eeg_channels": [ch1,ch2,ch3,ch4], "timestamp": 1700000000.0 }
Server buffers 50 readings → batch INSERT SensorData
Server sends back: { "received": 50, "status": "ok" }
On disconnect: flush remaining buffer
```

---

## 9. ML Pipeline

### Feature Vector (16 elements — same order for both roles)

| Index | Feature | Student | Teacher |
|-------|---------|---------|---------|
| 0 | emotional_score | Stage 1 normalized | Stage 1 normalized |
| 1 | functional_score | Stage 2 normalized | Stage 2 normalized |
| 2 | context_score | Stage 3 (academic) | Stage 3 (workload) |
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

### Model
- **Algorithm**: `RandomForestClassifier(n_estimators=200, max_depth=15)`
- **Training data**: 5000 synthetic samples per role (1250 per class)
- **Split**: 80% train / 20% test
- **Accuracy**: ~99.8% on synthetic test set
- **Classes**: 0=Normal, 1=Calm Down, 2=See Psychologist, 3=Emergency

### Fallback
If model files not found → rule-based scoring:
```
q_score = 0.30*emotional + 0.25*functional + 0.15*context + 0.20*isolation + 0.10*critical
q_score += emotion_distress * 0.5
0.0–1.0 → Normal | 1.0–2.0 → Calm Down | 2.0–3.5 → See Psychologist | 3.5–4.0 → Emergency
```

### Retrain on Real Data
Once enough real sessions accumulate in MH_Results:
```python
from ml.trainer import retrain_from_db
retrain_from_db("student", conn)
retrain_from_db("teacher", conn)
```

---

## 10. Preprocessing Modules

### EEG Preprocessor (`preprocessing/eeg_preprocessor.py`)
```
1. Load all SensorData rows (data_type='eeg') for session, ordered by recorded_at
2. Bandpass filter: 1–40 Hz using scipy.signal.butter (order=4) + sosfilt
3. FFT → power spectral density
4. Extract band powers:
     Delta: 1–4 Hz   (deep sleep indicator)
     Theta: 4–8 Hz   (drowsiness, meditation)
     Alpha: 8–13 Hz  (relaxed alertness)
     Beta:  13–30 Hz (active thinking, stress)
5. Stress index = (beta_power + theta_power) / alpha_power
6. Returns: { alpha_power, theta_power, beta_power, delta_power, stress_index }
   Returns all zeros if < 2 EEG samples available.
```

### BP Preprocessor (`preprocessing/bp_preprocessor.py`)
```
1. Load SensorData rows (data_type='bp') for session
2. Compute: mean_systolic, mean_diastolic, mean_pulse
3. Hypertension flag = 1 if systolic > 140 OR diastolic > 90
4. Returns: { mean_systolic, mean_diastolic, mean_pulse, hypertension_flag }
   Returns None values if no BP readings.
```

### Emotion Preprocessor (`preprocessing/emotion_preprocessor.py`)
```
1. Load FacialEmotions rows for session
   (columns: dominant_emotion, happy, sad, angry, fear, surprise, disgust, neutral)
2. Count frequency of each dominant_emotion label
3. Dominant = most frequent label
4. For each frame: weight = dominant emotion's score / 100
   distress_score = EMOTION_DISTRESS_MAP[label] * weight
5. Final distress = weighted average across all frames, clamped to [0,1]

EMOTION_DISTRESS_MAP:
  happy=0.0, neutral=0.1, surprise=0.2, disgust=0.4,
  fear=0.7, sad=0.7, angry=0.8, undetected=0.3
```

---

## 11. Hardware Integration

### Muse EEG Headset (Muse 2 / Muse S)
- Connect headset via Bluetooth to laptop
- Run: `muselsl stream --ppg` (must be running before backend)
- Streams two LSL feeds:
  - `type='EEG'` — 4 channels (TP9, AF7, AF8, TP10) at 256 Hz
  - `type='PPG'` — photoplethysmography (heart rate) at 64 Hz
- Backend connects via `pylsl.StreamInlet`
- EEG → WebSocket `/ws/eeg/{session_id}` (continuous)
- PPG → `POST /sensors/pulse` (every 10s)

### Smart BP Cuff (Omron BLE)
- Connects via Bluetooth Low Energy
- Standard GATT UUID: `00002a35-0000-1000-8000-00805f9b34fb`
- User presses button → single reading arrives as BLE notification
- `hardware/bp_reader.py` uses `bleak` to scan, connect, and receive notification
- Reading parsed → `POST /sensors/bp`

### Webcam Emotion Capture
- Flutter/React app captures frame every 5 seconds using device camera
- Frame encoded as base64 JPEG string
- Sent to `POST /sensors/emotion`
- Server: base64 decode → OpenCV → save to `emotion_images/` → DeepFace.analyze()
- `enforce_detection=False` ensures no crash if no face visible

---

## 12. Scoring Formulas

### Stage Normalization
```
normalized = (raw_sum / (num_questions * 4)) * 4
```

### Student Final Score
```
final = (
    0.30 * emotional_normalized  +
    0.20 * functional_normalized +
    0.10 * context_normalized    +
    0.15 * isolation_normalized  +
    0.10 * cgpa_trend_score      +   # max(0, -cgpa_trend) * 2, capped at 4
    0.05 * attendance_score      +   # max(0, attendance_drop) * 0.5, cap 4
    0.05 * performance_score     +   # (failed/total) * 4
    0.05 * critical_normalized
)
```

### Teacher Final Score
```
final = (
    0.30 * emotional_normalized   +
    0.20 * functional_normalized  +
    0.15 * context_normalized     +
    0.15 * isolation_normalized   +
    0.10 * teaching_load_score    +   # (workload_hrs / 5.0) * 4, cap 4
    0.05 * feedback_score         +   # max(0, -feedback_trend) * 2, cap 4
    0.05 * critical_normalized
)
```

### Score → Recommendation (rule-based fallback only)
```
0.0 – 1.0  → Normal
1.0 – 2.0  → Calm Down
2.0 – 3.5  → See Psychologist
3.5 – 4.0  → Emergency
```

---

## 13. Key Fixes & DB Constraints

These were discovered during testing and fixed. Important to know:

### SensorData.data_type CHECK Constraint
```sql
-- ONLY these values are allowed:
data_type IN ('eeg', 'ppg', 'bp', 'emotion')
-- 'pulse' is NOT valid — use 'ppg' for pulse/heart-rate readings
```

### MH_Results.risk_class CHECK Constraint
```sql
-- ONLY these values are allowed:
risk_class IN ('Healthy', 'Mild Stress', 'Moderate Risk', 'High Risk', 'Critical Risk')
-- The ML model outputs different strings — they are mapped before INSERT:
-- 'Normal' → 'Healthy'
-- 'Calm Down' → 'Mild Stress'
-- 'See Psychologist' → 'High Risk'
-- 'Emergency' → 'Critical Risk'
```

### FacialEmotions Schema
The table stores **individual emotion scores** (not a single label+confidence):
```sql
-- Columns: dominant_emotion, happy, sad, angry, fear, surprise, disgust, neutral
-- NOT: emotion_label, confidence (those don't exist)
```

### Teachers Table
```sql
-- Actual columns: workload_hrs, class_count
-- NOT: course_load, feedback_trend (those don't exist)
```

### Students Table
```sql
-- Actual columns: cgpa_trend, attendance_drop
-- Enrollments table does NOT exist — failed-course count is skipped
```

---

## 14. Test Suite

`test_endpoints.py` runs 13 sequential tests covering the full lifecycle:

| Step | Test | What it verifies |
|------|------|-----------------|
| 0 | Health Check | DB connected + ML models loaded |
| 1 | Register Student | User creation + user_id returned |
| 2 | Login | JWT token + correct role |
| 3 | Start Session | session_id created in Sessions table |
| 4 | Submit Stage 1 | 6 answers saved, stage threshold evaluated |
| 5 | Submit Stage 2 | 5 answers saved, next_stage returned |
| 6 | BP Reading | SensorData INSERT (data_type='bp') |
| 7 | Pulse Reading | SensorData INSERT (data_type='ppg') |
| 8 | Emotion Frame | DeepFace runs, FacialEmotions saved |
| 9 | End Session | Full ML pipeline runs, MH_Results saved |
| 10 | Get Results | MH_Results returned with recommendation |
| 11 | Session Detail | Counts of all sensor data collected |
| 12 | User History | All past sessions for a user |

### Running
```bash
# Server must be running first
uvicorn main:app --port 8000

# In another terminal
python test_endpoints.py
```

Expected output:
```
RESULTS:  13/13 passed    0/13 failed
ALL TESTS PASSED -- system is end-to-end functional.
```

---

## Quick Reference Commands

```bash
# Run DB migrations (safe to repeat)
python db_migrations.py

# Train ML models
python -m ml.trainer

# Start EEG hardware stream
muselsl stream --ppg

# Start backend server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run all API tests
python test_endpoints.py

# Check DB schema constraints
python check_schema.py

# Interactive API docs
open http://localhost:8000/docs
```
