# 🏥 Multimodal Virtual Clinic — Backend

> **FYP Project | BSAI-7A**  
> A multimodal mental health assessment platform for university students and teachers.  
> Built with **FastAPI** · **SQL Server** · **TensorFlow** · **Scikit-learn** · **DeepFace**

---

## 📌 What This Is

The backend for a **Multimodal Virtual Clinic** that assesses mental health by combining multiple data streams in real-time:

- 🧠 **EEG** (Muse 2/S headset) — brainwave activity via WebSocket
- 💓 **Blood Pressure & Pulse** — BLE Omron cuff
- 😐 **Facial Emotion** — webcam frames analyzed with a custom CNN or DeepFace
- 📋 **Questionnaire** — 4-stage adaptive scoring (PHQ-9, GAD-7, PSS, MBI style)

All streams are fused by an **ML pipeline** (Random Forest) to produce one of four clinical recommendations:

| Recommendation | Meaning |
|---|---|
| ✅ Normal | No significant stress detected |
| 😌 Calm Down | Mild stress — relaxation advised |
| 🧑‍⚕️ See Psychologist | Moderate risk — professional consultation |
| 🚨 Emergency | High risk — urgent intervention |

---

## 🚀 Quick Start (For Teammates)

### Prerequisites

- Python **3.10 – 3.11** (Python 3.12+ has TensorFlow compatibility issues)
- **Microsoft SQL Server** (Express is fine) with Windows Authentication enabled
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/imhasnain/FYP-Backend.git
cd FYP-Backend
```

### 2. Create & Activate Virtual Environment

```bash
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ TensorFlow takes a few minutes to install — this is expected.

### 4. Configure the Database

Create a `.env` file in the project root (it is gitignored — never commit this):

```env
DB_SERVER=localhost
DB_NAME=VirtualClinicDB
DB_TRUSTED_CONNECTION=true
SECRET_KEY=your-long-random-secret-key
```

**Using SQL Server Authentication instead of Windows Auth?**
```env
DB_TRUSTED_CONNECTION=false
DB_USER=your_username
DB_PASSWORD=your_password
```

### 5. Set Up the Database Schema

Open SQL Server Management Studio (SSMS), paste and run the full script:

```
database/schema.sql
```

This creates the `VirtualClinicDB` database and all tables from scratch. Safe to re-run.

### 6. Run Migrations (add any new columns)

```bash
python db_migrations.py
```

### 7. Train the ML Models

```bash
python -m ml.trainer
```

This generates synthetic data and trains two RandomForest classifiers:
- `ml/saved_models/model_student.pkl`
- `ml/saved_models/model_teacher.pkl`

### 8. Start the Server

**Option A — PowerShell launcher (recommended on Windows):**
```powershell
.\start_server.ps1
```
This auto-detects your LAN IP and prints it for you to use in your frontend.

**Option B — Manual:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 9. Verify It's Running

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc:      [http://localhost:8000/redoc](http://localhost:8000/redoc)
- Health:     [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Reference

> **Base URL for mobile/frontend on the same network:** `http://<YOUR_LAN_IP>:8000`

### 🔐 Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login → returns JWT token |

**Login Request Body:**
```json
{
  "username": "student@clinic.com",
  "password": "student123"
}
```

**Pre-seeded test accounts:**

| Email | Password | Role |
|---|---|---|
| `student@clinic.com` | `student123` | Student |
| `teacher@clinic.com` | `teacher123` | Teacher |
| `psychologist@clinic.com` | `psych123` | Psychologist |

### 🩺 Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/session/start` | Start a new assessment session |
| POST | `/session/end` | End session → triggers ML prediction |
| GET | `/session/{id}` | Get session details |

### 📋 Questionnaire

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/questionnaire/stages` | List all stages |
| GET | `/questionnaire/questions/{stage_number}` | Get questions for a stage |
| POST | `/questionnaire/submit` | Submit one stage of answers |

### 📷 Sensors

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sensors/emotion` | Analyze facial emotion (base64 JPEG) |
| POST | `/sensors/bp` | Submit blood pressure reading |
| POST | `/sensors/pulse` | Submit pulse/heart rate |

**Emotion Request Body:**
```json
{
  "session_id": 1,
  "user_id": 1,
  "stage_number": 2,
  "image_base64": "<base64-encoded JPEG string>"
}
```

### 📊 Results

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/results/{session_id}` | Full result for a session |
| GET | `/results/user/{user_id}` | All sessions for a user |
| GET | `/results/all` | All results (psychologist dashboard) |

### 🌐 WebSocket

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| WS | `/ws/eeg/{session_id}` | Real-time EEG data stream |

---

## 🤖 ML & Emotion Pipeline

### Emotion Detection (Dual-Model)

The `/sensors/emotion` endpoint runs a **2-layer fallback system**:

1. **Custom CNN** (`ml/saved_models/custom_emotion_model.h5`) — Trained on FER-2013 (48×48 grayscale). If it detects a face with **>55% confidence**, it uses that result.
2. **DeepFace fallback** — If the custom model is absent, fails, or is low-confidence, DeepFace analyzes the frame automatically.

**Training your own custom emotion model** (optional, improves accuracy):
```bash
# First, download FER-2013 dataset from Kaggle and place it at:
# ml/dataset/train/ and ml/dataset/test/

python ml/train_custom_emotion.py
```

### Prediction Feature Vector (16 features)

| # | Feature | Source |
|---|---------|--------|
| 1–5 | Questionnaire stage scores | Questionnaire |
| 6 | Age | User profile |
| 7 | Experience (years) | User profile |
| 8–12 | EEG band powers (delta, theta, alpha, beta, gamma) | Muse headset |
| 13–14 | Systolic/Diastolic BP delta from baseline | BP machine |
| 15 | Pulse rate | BP or Muse PPG |
| 16 | Emotion distress score | Facial emotion |

---

## 📁 Project Structure

```
FYP-Backend/
├── main.py                    # FastAPI app entry point & startup
├── config.py                  # All settings (env-configurable)
├── database.py                # SQL Server connection factory
├── db_migrations.py           # Safe, idempotent schema migrations
├── start_server.ps1           # Windows launcher script
│
├── routers/                   # API route handlers
│   ├── auth.py                # Login / JWT
│   ├── sessions.py            # Session lifecycle
│   ├── questionnaire.py       # Questionnaire flow
│   ├── sensors.py             # Emotion, BP, pulse endpoints
│   └── results.py             # Result retrieval
│
├── models/                    # Pydantic request/response schemas
│
├── ml/                        # Machine learning pipeline
│   ├── trainer.py             # Trains student & teacher models
│   ├── predictor.py           # Runs prediction on feature vector
│   ├── feature_builder.py     # Assembles 16-feature vector from DB
│   ├── train_custom_emotion.py  # Trains custom FER CNN
│   └── saved_models/          # .pkl and .h5 model files
│
├── preprocessing/             # Signal preprocessing
│   ├── eeg_preprocessor.py
│   ├── bp_preprocessor.py
│   └── emotion_preprocessor.py
│
├── scoring/
│   └── questionnaire_scorer.py  # Weighted scoring per stage
│
├── hardware/                  # Hardware integration scripts
│   ├── eeg_stream.py          # Muse headset via muselsl
│   └── bp_reader.py           # BLE BP cuff via bleak
│
├── websocket/
│   └── eeg_handler.py         # WebSocket EEG ingestion
│
├── utils/                     # Auth, time, response helpers
│
├── database/
│   └── schema.sql             # Full SQL Server schema (run this first!)
│
└── test_endpoints.py          # Integration test suite
```

---

## 🛠 Hardware (Optional)

The backend works without hardware — sensors just won't have data, and the ML model falls back to questionnaire-only scoring.

| Hardware | Connection | Setup |
|---|---|---|
| Muse 2 / Muse S EEG | Bluetooth → `muselsl` | `pip install muselsl` → `muselsl stream --ppg` |
| Omron BLE BP Cuff | Bluetooth LE | Auto-discovered via GATT UUID `0x2A35` |
| Webcam | USB / Built-in | Used directly by the frontend app |

---

## 🔄 Session Lifecycle

```
1.  User logs in           → JWT token returned
2.  POST /session/start    → session_id assigned
3.  Data streams begin (parallel):
      📷 Camera  → POST /sensors/emotion  every 5s
      💓 BP Cuff → POST /sensors/bp       on reading
      🧠 EEG     → WS /ws/eeg/{id}        continuous
4.  User answers questionnaire stages 1–4
      → Each stage score dynamically weighted by
        the facial emotion captured at that moment
5.  POST /session/end      → ML pipeline runs
      → 16-feature vector assembled from DB
      → RandomForest predicts recommendation
6.  GET /results/{session_id} → Full report returned
```

---

## 🧪 Running Tests

```bash
python test_endpoints.py
```

Tests cover: login, session start/end, questionnaire submission, emotion upload, BP/pulse recording, and results retrieval.

---

## 📝 Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `DB_SERVER` | `localhost` | SQL Server host |
| `DB_NAME` | `VirtualClinicDB` | Database name |
| `DB_TRUSTED_CONNECTION` | `true` | Windows Auth (`true`) or SQL Auth (`false`) |
| `DB_USER` | *(empty)* | SQL Auth username |
| `DB_PASSWORD` | *(empty)* | SQL Auth password |
| `SECRET_KEY` | *(must change!)* | JWT signing key |
| `TOKEN_EXPIRE_MINUTES` | `480` | JWT expiry (8 hours) |
| `EMOTION_INTERVAL_SECONDS` | `5` | Seconds between emotion captures |

---

## 👥 Team

**BSAI-7A — Final Year Project**  
Multimodal Virtual Clinic for University Mental Health Assessment

---

> ⚠️ **Note:** The `frontend/` folder, `venv/`, `.env`, `emotion_images/`, and `ml/dataset/` are excluded from this repository via `.gitignore`. Each team member builds their own frontend (Flutter, React, etc.) that connects to this backend via the REST API documented above.
