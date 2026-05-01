# Multimodal Virtual Clinic — Backend

A university mental health assessment platform backend built with **FastAPI**, integrating
EEG, Blood Pressure, Facial Emotion Detection, and Questionnaire-based screening.

## Architecture Overview

```
Client (Flutter / React)
    │
    ▼  REST + WebSocket
FastAPI Backend
    │
    ├── Preprocessing Pipeline (EEG, BP, Emotion)
    ├── ML Models (Student + Teacher RandomForest)
    ├── Scoring Engine (Questionnaire weighted formulas)
    │
    ▼
Microsoft SQL Server (FYP_Project database)
```

## Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn pyodbc python-jose[cryptography] passlib[bcrypt] python-multipart pydantic[email] pydantic-settings deepface opencv-python numpy scipy scikit-learn joblib pandas pylsl bleak requests pillow
```

### 2. Configure Database

Edit `config.py` or create a `.env` file in the project root:

```env
DB_SERVER=localhost
DB_NAME=FYP_Project
DB_TRUSTED_CONNECTION=true
SECRET_KEY=your-secret-key-here
```

For SQL Server Authentication (instead of Windows Auth):

```env
DB_TRUSTED_CONNECTION=false
DB_USER=your_username
DB_PASSWORD=your_password
```

### 3. Run Database Migrations

```bash
python db_migrations.py
```

This will add new columns to `SensorData` and `Q_Responses`, and create the `MH_Results` table.
Safe to run multiple times (idempotent).

### 4. Train ML Models

```bash
python -m ml.trainer
```

This generates synthetic training data and trains two RandomForest models:
- `ml/saved_models/model_student.pkl`
- `ml/saved_models/model_teacher.pkl`

### 5. Start Muse EEG Stream (optional, only if hardware is connected)

If you have a Muse headset connected via Bluetooth, the backend can **automatically start** the background `muselsl stream --ppg` process. Alternatively, you can run it manually:

```bash
muselsl stream --ppg
```

### 6. Start the Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 7. View API Documentation

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### 8. Run Integration Tests

```bash
python test_endpoints.py
```

## API Endpoints

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login and get JWT token |

### Sessions
| Method | Path | Description |
|--------|------|-------------|
| POST | `/session/start` | Start a new assessment session |
| POST | `/session/end` | End session → triggers ML prediction |
| GET | `/session/{id}` | Get session details with data counts |

### Questionnaire
| Method | Path | Description |
|--------|------|-------------|
| POST | `/questionnaire/submit` | Submit one stage of answers |
| GET | `/questionnaire/stages` | List all stages |
| GET | `/questionnaire/questions/{stage}` | Get questions for a stage |

### Sensors
| Method | Path | Description |
|--------|------|-------------|
| POST | `/sensors/emotion` | Analyze emotion from base64 image |
| POST | `/sensors/bp` | Submit blood pressure reading |
| POST | `/sensors/pulse` | Submit pulse/heart rate reading |

### WebSocket
| Protocol | Path | Description |
|----------|------|-------------|
| WS | `/ws/eeg/{session_id}` | Real-time EEG data stream |

### Results
| Method | Path | Description |
|--------|------|-------------|
| GET | `/results/{session_id}` | Full result with score breakdown |
| GET | `/results/user/{user_id}` | User's session history |
| GET | `/results/all` | All results (psychologist dashboard) |

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Basic health check |
| GET | `/health` | Detailed health (DB + models status) |

## ML Model Details

- **Algorithm**: RandomForestClassifier (200 trees, max_depth=15)
- **Training**: Synthetic data (5000 samples per role, balanced classes)
- **Feature Vector**: 16 features (questionnaire + EEG + BP + emotion)
- **Output**: 4 classes → Normal, Calm Down, See Psychologist, Emergency
- **Fallback**: Rule-based scoring when models are not loaded

## Folder Structure

```
backend/
├── main.py                    # FastAPI app entry point
├── config.py                  # All configuration settings
├── database.py                # SQL Server connection factory
├── db_migrations.py           # Idempotent schema migrations
├── models/                    # Pydantic request/response schemas
├── routers/                   # API route handlers
├── hardware/                  # EEG stream + BP reader
├── websocket/                 # WebSocket EEG handler
├── preprocessing/             # EEG, BP, emotion preprocessing
├── ml/                        # Feature builder, predictor, trainer
│   └── saved_models/          # Trained .pkl model files
├── scoring/                   # Questionnaire scoring formulas
├── utils/                     # Auth, response, time utilities
├── emotion_images/            # Saved webcam frames (auto-created)
├── test_endpoints.py          # API integration tests
└── README.md                  # This file
```

## Hardware Requirements

- **Muse 2/S EEG Headset**: Pair via Bluetooth, run `muselsl stream`
- **Omron BLE BP Cuff**: Any model with GATT UUID `0x2A35`
- **Webcam**: Built-in or USB camera for facial emotion detection

## Session Lifecycle

1. User logs in → gets JWT token
2. App starts session → gets session_id
3. Three parallel data streams begin:
   - Camera captures every 5s → `POST /sensors/emotion` (Saves frame to `emotion_images/` & detects emotion)
   - BP cuff readings → `POST /sensors/bp` (Calculates baseline/delta if applicable)
   - EEG via WebSocket → `WS /ws/eeg/{session_id}` (Auto-starts `muselsl` if needed)
4. User completes questionnaire stages 1–5
   - **Dynamic Emotion Mapping**: Each submitted question is precisely timestamp-matched with the closest 5-second webcam frame. If the user's face shows distress (e.g. Fear/Angry) while answering a specific question, that question's risk score is dynamically multiplied!
5. App ends session → backend runs full ML pipeline → returns recommendation
6. Result displayed with confidence and score breakdown
