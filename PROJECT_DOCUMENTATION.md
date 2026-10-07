# Virtual Clinic — Complete Project Documentation

**Project:** AI-Powered Multimodal Mental Health Monitoring System  
**University:** BIIT  
**Platform:** Android Mobile App + Windows Backend Server

---

## TABLE OF CONTENTS

1. [Project Overview — What Is This?](#1-project-overview)
2. [System Architecture — How Everything Connects](#2-system-architecture)
3. [Hardware Devices & Signal Processing (Basic to Expert)](#3-hardware-devices)
4. [Database — How We Store Everything](#4-database)
5. [Backend — The Brain of the System](#5-backend)
6. [Scoring Engine & EEG Integration — How We Calculate Stress](#6-scoring-engine)
7. [Frontend — The Mobile App](#7-frontend)
8. [User Roles — Who Uses What](#8-user-roles)
9. [Full Session Flow — Step by Step](#9-full-session-flow)
10. [API Endpoints — All Backend Routes](#10-api-endpoints)
11. [Questionnaire — Stages and Questions](#11-questionnaire)
12. [Why We Chose These Technologies](#12-technology-choices)
13. [How to Test the System — Step-by-Step Verification Guide](#13-how-to-test-the-system)

---

## 1. Project Overview

### What Problem Are We Solving?

Mental health issues in university students are very common but often go undetected because:
- Students feel embarrassed to talk about it
- There is no automated, objective way to monitor stress levels
- Advisors and teachers do not know which students need help early

### What Does Our System Do?

Our system is a **multimodal** mental health monitoring system. "Multimodal" means it uses **multiple different methods** to measure mental health, not just one:

1. **EEG Brain Signals** — measures real-time brainwave activity via Muse 2 headset
2. **Blood Pressure** — measures physical stress response
3. **Heart Rate / Pulse** — measures autonomic arousal and anxiety
4. **Facial Emotion Detection** — detects emotional state from face photos using deep learning
5. **Questionnaire** — asks the student about their psychological state directly

By combining all five sources, we get a much more accurate and objective picture than using just one method alone.

### Who Uses the System?

| Role | What They Do |
|------|-------------|
| **Student** | Takes the assessment, streams live EEG, follows wellness plan |
| **Teacher** | Takes the assessment (workload-focused questions) |
| **Advisor** | Monitors students flagged with mild stress alerts |
| **Psychologist** | Reviews high-risk appointments, inspects full session EEG graphs per question, rates question usefulness |

---

## 2. System Architecture

```
[Muse 2 Headset] (Bluetooth)
       │
       ▼
[BlueMuse App (Windows)] ──(LSL Protocol)──► [pylsl StreamInlet]
                                                  │
                                                  ▼
[Android Mobile App] ◄──(WebSocket / HTTP)──► [FastAPI Backend] ──► [SQL Server DB]
```

### How Component Communication Works

- **Bluetooth to LSL:** Muse 2 streams raw brainwaves over Bluetooth LE to **BlueMuse** (Windows application), which creates a **Lab Streaming Layer (LSL)** outlet on the local machine at 256 Hz.
- **Python LSL Ingestion:** The backend (`hardware/eeg_stream.py`) resolves the LSL outlet using `pylsl` and processes rolling 2-second windows.
- **Mobile to Backend:** The Flutter app connects via HTTP REST endpoints and WebSockets (`ws://<backend-ip>:8000/ws/eeg/{session_id}`).
- **Data Persistence:** SQL Server database (`MIRZA\SQLEXPRESS`) stores all users, session records, sensor data, raw EEG snapshots per question, and psychologist feedback.

---

## 3. Hardware Devices & Signal Processing (Basic to Expert)

---

### 3.1 EEG Headset (Brain Waves) — Full Deep Dive

#### **Level 1: Basic Concept (For General Understanding & Demo Presentations)**
- **Device:** Muse 2 Headset (or Muse S).
- **Channels:** 4 dry EEG channels placed according to the international 10–20 system:
  - **AF7** (Left Frontal)
  - **AF8** (Right Frontal)
  - **TP9** (Left Temporal)
  - **TP10** (Right Temporal)
- **Reference:** Fpz (CMS/DRL reference).
- **Sampling Rate:** 256 Hz (256 electrical readings per second per channel).
- **Why Frontal Channels Matter:** The prefrontal cortex (channels AF7 and AF8) regulates emotion, decision-making, and stress responses. We average AF7 and AF8 for calculating mental stress.

**The 4 Main Brain Wave Bands:**

| Brain Wave | Frequency Range | Mental State |
|-----------|-----------------|--------------|
| **Alpha** | 8–13 Hz | Relaxed, calm, peaceful. High Alpha = low stress. |
| **Beta** | 13–30 Hz | Active thinking, focus, anxiety, stress. High Beta = active/stressed. |
| **Theta** | 4–8 Hz | Drowsiness, mental fatigue, deep emotional processing. |
| **Delta** | 0.5–4 Hz | Deep sleep (filtered out in our stress pipeline). |

---

#### **Level 2: Intermediate Signal Processing Pipeline (How Python Calculates Values)**

1. **Windowing / Buffering:**
   - Raw EEG samples are collected into a **rolling 2-second buffer** (512 samples at 256 Hz).
   - A frontal average signal $x[n] = \frac{\text{AF7}[n] + \text{AF8}[n]}{2}$ is constructed.

2. **Noise Reduction (Butterworth Bandpass Filtering):**
   - Muscle artifacts, eye blinks, and 50/60 Hz electrical mains noise corrupt raw EEG.
   - We apply a **4th-order Butterworth Bandpass Filter** with cutoffs at $1.0\text{ Hz}$ to $40.0\text{ Hz}$:
     $$H(s) = \frac{1}{\sum_{k=0}^{N} a_k s^k}$$
   - Applied using Second-Order Sections (`scipy.signal.sosfilt`) for numerical stability.

3. **Spectral Power Extraction via Fast Fourier Transform (FFT):**
   - Converts filtered time-domain signal $x(t)$ into frequency-domain power spectrum $P(f)$:
     $$X[k] = \sum_{n=0}^{N-1} x[n] e^{-j 2\pi k n / N}$$
     $$P[k] = \frac{|X[k]|^2}{N}$$
   - Band power ($\mu\text{V}^2$) is computed as the mean spectral power within each frequency range:
     $$\text{Power}_{\text{band}} = \frac{1}{M} \sum_{f \in \text{band}} P(f)$$

4. **Stress Index Calculation:**
   $$\text{Stress Index} = \frac{\text{Beta Power} + \text{Theta Power}}{\text{Alpha Power} + 10^{-6}}$$
   - High Stress Index $\rightarrow$ High Beta/Theta relative to Alpha.
   - Low Stress Index $\rightarrow$ Dominant Alpha (relaxed state).

---

#### **Level 3: Expert Implementation & Sync Architecture (For Technical Defense)**

- **Background Acquisition Thread:** `EEGStream` class in `hardware/eeg_stream.py` runs an asynchronous non-blocking thread during an active session.
- **Question Marker Synchronization:**
  - When the student views or answers Question $N$ in the Flutter questionnaire, the app posts to `/eeg/marker` with `{"session_id": S, "question_id": Q, "question_num": N}`.
  - The `EEGStream` tags all subsequent 2-second snapshots with `question_id` and `question_num`.
- **Database Persistence (`EEG_Snapshots` Table):**
  - Every 2 seconds, a processed snapshot containing `(alpha_power, beta_power, theta_power, stress_index, question_id, question_num, recorded_at)` is committed to SQL Server.
- **Real-Time WebSocket Push:**
  - The WebSocket handler `/ws/eeg/{session_id}` polls `EEGStream.latest` and broadcasts JSON payloads every 2 seconds to the mobile app UI.
- **Psychologist Scrubber Tool:**
  - The psychologist dashboard fetches `/eeg/timeline/{session_id}` and renders an interactive timeline with a slider and back/forward step buttons.
  - The psychologist can step second-by-second or question-by-question to observe exact brainwave shifts while the student answered sensitive questions.

---

### 3.2 Blood Pressure Monitor

**Device:** Withings BPM Connect (or manual BP cuff)  
**What it measures:** Systolic and Diastolic blood pressure in mmHg  
**Why it matters:** Stress triggers sympathetic nervous system activation, releasing adrenaline and tightening blood vessels, elevating systolic BP.

**Formula:**
```
Systolic Delta = Last Systolic Reading − First Systolic Reading
BP Score = min(4.0, max(0, Systolic Delta / 10))
```

---

### 3.3 Pulse Rate / Heart Rate Monitor

**Device:** PPG Optical Sensor / Withings BPM Connect  
**What it measures:** Heart rate in Beats Per Minute (BPM)  
**Formula:**
```
Average HR = Mean of pulse readings during session
HR Delta = Average HR − 72   (72 BPM baseline)
HR Score = min(4.0, max(0, HR Delta / 10))
```

---

### 3.4 Facial Emotion Detection (Camera)

**Library:** DeepFace (TensorFlow backend)  
**How it works:** Periodic front-camera frames are encoded in Base64 and sent to `/sensors/emotion`. DeepFace detects face geometry and outputs probability scores for 7 primary emotions.

**Distress Mapping:**
```
Happy: 0.0 | Neutral: 0.1 | Surprise: 0.2 | Disgust: 0.5 | Sad: 0.7 | Fear: 0.8 | Angry: 0.8
Face Score = (Mean Distress Across Session Photos) × 4.0
```

---

## 4. Database

**DBMS:** Microsoft SQL Server Express (`MIRZA\SQLEXPRESS`)  
**Database Name:** `VirtualClinicDB`  
**Authentication:** Windows Trusted Connection (`pyodbc`)

### Database Table Schemas

#### 1. `Users` Table
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| user_id | INT (PK) | No | Auto-incremented ID |
| name | VARCHAR | No | Full name |
| email | VARCHAR | No | Login email |
| password | VARCHAR | No | Account password |
| role | VARCHAR | No | `student`, `teacher`, `advisor`, `psychologist` |
| created_at | DATETIME | No | Account creation timestamp |

---

#### 2. `EEG_Snapshots` Table (NEW — EEG Time-Series Sync)
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| snapshot_id | INT (PK) | No | Snapshot record ID |
| session_id | INT (FK) | No | Links to Sessions table |
| recorded_at | DATETIME | No | Timestamp of snapshot |
| alpha_power | FLOAT | No | Alpha power ($\mu\text{V}^2$) |
| beta_power | FLOAT | No | Beta power ($\mu\text{V}^2$) |
| theta_power | FLOAT | No | Theta power ($\mu\text{V}^2$) |
| stress_index | FLOAT | No | Ratio $( \text{Beta} + \text{Theta} ) / \text{Alpha}$ |
| question_id | INT | Yes | Question ID active during snapshot |
| question_num | INT | Yes | Question number (e.g. 1, 2, 3...) |

---

#### 3. `Sessions` Table
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| session_id | INT (PK) | No | Session ID |
| user_id | INT (FK) | No | Student/Teacher user ID |
| start_time | DATETIME | No | Start timestamp |
| end_time | DATETIME | Yes | Completion timestamp |

---

#### 4. `MH_Results` Table
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| result_id | INT (PK) | No | Result record ID |
| session_id | INT (FK) | No | Session ID |
| user_id | INT (FK) | No | User ID |
| emotional_score | FLOAT | Yes | Stage 1 score (0–4) |
| functional_score | FLOAT | Yes | Stage 2 score (0–4) |
| context_score | FLOAT | Yes | Stage 3 score (0–4) |
| isolation_score | FLOAT | Yes | Stage 4 score (0–4) |
| critical_score | FLOAT | Yes | Stage 5 score (0–4) |
| eeg_avg | FLOAT | Yes | Mean session EEG stress index |
| avg_pulse | FLOAT | Yes | Mean session heart rate |
| avg_bp_systolic | INT | Yes | Baseline systolic BP |
| dominant_emotion | VARCHAR | Yes | Most frequent emotion |
| final_score | FLOAT | No | Fused total score (0–4) |
| risk_class | VARCHAR | No | `Healthy`, `Mild Stress`, `High Risk`, `Critical Risk` |
| calculated_at | DATETIME | No | Timestamp |

---

#### 5. `Appointments` Table
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| appointment_id | INT (PK) | No | Appointment ID |
| student_id | INT (FK) | No | Student user ID |
| psychologist_id | INT (FK) | No | Assigned psychologist user ID |
| session_id | INT (FK) | No | Session triggering appointment |
| status | VARCHAR | No | `Scheduled`, `Completed`, `Cancelled` |

---

#### 6. `QuestionFeedback` Table (Psychologist Adaptive Learning)
| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| feedback_id | INT (PK) | No | Feedback record ID |
| psychologist_id | INT (FK) | No | Psychologist user ID |
| question_id | INT (FK) | No | Question evaluated |
| usefulness_score | INT | No | Rating from 1 (least useful) to 5 (most useful) |
| comments | VARCHAR | Yes | Text notes |

---

## 5. Backend

**Framework:** FastAPI  
**Server:** Uvicorn  
**Language:** Python 3.11  
**Key Packages:** `pylsl`, `numpy==1.26.4`, `scipy`, `pyodbc`, `deepface`, `opencv-python`

### Backend File Structure

```
Backend/
├── main.py                  ← FastAPI routes registration & lifespan
├── config.py                ← Central settings & DB string
├── database.py              ← pyodbc SQL Server connection pool
│
├── hardware/
│   ├── eeg_stream.py        ← Muse 2 LSL streaming thread, Butterworth filter, FFT
│   └── withings.py          ← Withings BP API helper
│
├── routers/
│   ├── auth.py              ← /auth/login, /auth/register
│   ├── sessions.py          ← /session/start, /session/end (scoring pipeline)
│   ├── eeg.py               ← /eeg/connect, /eeg/disconnect, /eeg/marker, /eeg/timeline
│   ├── questionnaire.py     ← /questionnaire/stages, /questionnaire/questions, /submit
│   ├── sensors.py           ← /sensors/pulse, /sensors/bp, /sensors/emotion
│   ├── results.py           ← /results/{session_id}, /results/user/{user_id}
│   ├── psychologist.py      ← Appointments, Q-Feedback, session answers
│   └── advisor.py           ← Advisor notification feed
│
├── processing/
│   ├── eeg.py               ← Aggregates EEG_Snapshots for session end scoring
│   ├── emotions.py          ← Aggregates FacialEmotions distress score
│   └── scorer.py            ← 70/30 Fusion, Safety Override, Feedback Weighting
│
└── websocket/
    └── eeg_handler.py       ← WS /ws/eeg/{session_id} real-time push
```

---

## 6. Scoring Engine & EEG Integration

### Step 1: Questionnaire Score ($Q_{\text{score}}$, 70% Weight)

Stage scores $S_1, S_2, S_3, S_4, S_5$ are normalized to $[0, 4]$.

Weights are adjusted dynamically using psychologist ratings in `QuestionFeedback`:
$$w_i = \frac{\text{AvgRating}_{\text{Stage } i}}{\sum_{j=1}^5 \text{AvgRating}_{\text{Stage } j}}$$

For Students:
$$Q_{\text{score}} = \sum_{i=1}^5 w_i S_i + 0.10 \times \text{CGPA}_{\text{Score}} + 0.05 \times \text{Attendance}_{\text{Score}} + 0.05 \times \text{Performance}_{\text{Score}}$$

---

### Step 2: Physiological Score ($\text{Physio}_{\text{score}}$, 30% Weight)

$$\text{Physio}_{\text{score}} = 0.40 \times \text{EEG}_{\text{Score}} + 0.25 \times \text{Face}_{\text{Score}} + 0.20 \times \text{HR}_{\text{Score}} + 0.15 \times \text{BP}_{\text{Score}}$$

Where:
$$\text{EEG}_{\text{Score}} = \min\left(4.0, \text{Mean Stress Index} \times 0.8\right)$$

---

### Step 3: Final Fusion & Risk Classification

$$\text{Final Score} = 0.70 \times Q_{\text{score}} + 0.30 \times \text{Physio}_{\text{score}}$$

| Final Score | Recommendation | DB Risk Class | Automated Action |
|-------------|----------------|---------------|------------------|
| 0.0 – 1.0 | Normal | Healthy | Wellness Center Access |
| 1.0 – 2.0 | Calm Down | Mild Stress | Advisor Alert Notification |
| 2.0 – 3.0 | See Psychologist | High Risk | Psychologist Appointment Auto-Booked |
| 3.0 – 4.0 | Emergency | Critical Risk | Psychologist Appointment Auto-Booked |

---

### Step 4: Crisis Safety Override
If any Stage 5 question (crisis/self-harm screening) receives an answer score $\ge 3$ ("Often" or "Always"):
- Recommendation forced to **Emergency**
- Final score forced to **4.0**
- Psychologist appointment auto-booked instantly regardless of physiological data.

---

## 7. Frontend — Mobile App

**Framework:** Flutter (Dart)  
**State Management:** Provider pattern  

### App Screens Structure

- `screens/auth/login_screen.dart` — Role-based authentication
- `screens/home/home_screen.dart` — Student dashboard, session history, Wellness Center shortcut
- `screens/session/session_screen.dart` — Session status, **Connect EEG** button, WebSocket Live Vitals feed, live Stress Index bar
- `screens/session/questionnaire_screen.dart` — 5-stage questionnaire, automatic `/eeg/marker` submission per question
- `screens/results/result_detail_screen.dart` — Score breakdown, radar breakdown, referral notes
- `screens/home/psychologist_dashboard_screen.dart` — Appointments list, **Q-Answers** feedback, and interactive **EEG Graph** timeline scrubber
- `screens/home/advisor_dashboard_screen.dart` — Mild stress notifications feed
- `screens/home/wellness_screen.dart` — 3-tab post-assessment wellness suite (Action Plan, Breathing Room, Learn)

---

## 8. User Roles & Test Accounts

| Role | Email | Password | Primary Feature |
|------|-------|----------|-----------------|
| **Student 1** | `2023-arid-0167@biit.edu.pk` | `password123` | Start assessment, view wellness plan |
| **Student 2** | `2023-arid-0168@biit.edu.pk` | `password123` | Start assessment, view history |
| **Teacher** | `ali@biit.edu.pk` | `advisor123` | Take teacher questionnaire |
| **Advisor** | `ali@biit.edu.pk` | `advisor123` | Review mild-stress alerted students |
| **Psychologist** | `usman@biit.edu.pk` | `doctor123` | Review high-risk appointments, inspect EEG Timeline per question, rate question usefulness |

---

## 9. Full Session Flow

```
1. Student opens app -> Logs in as 2023-arid-0167@biit.edu.pk
2. Taps "Start Assessment" -> POST /session/start -> Session created
3. Session Screen opens:
   - User taps "Connect EEG" -> Calls POST /eeg/connect
   - Backend starts EEGStream thread -> Resolves BlueMuse LSL stream
   - WebSocket /ws/eeg/{session_id} starts pushing live Alpha, Beta, Theta, Stress Index
4. User taps "Fill Questionnaire" -> Questionnaire Screen opens
5. For each question answered:
   - User selects choice -> App sends POST /eeg/marker -> Tags EEG snapshots with question_num
6. After Stage 2 & Stage 5 -> Blood Pressure prompts appear
7. User taps "End Session & Get Report" -> Calls POST /session/end
   - Backend stops EEGStream thread
   - Computes Q_score, Physio_score (EEG_Snapshots average), Fused Final Score
   - Saves to MH_Results
   - If High Risk -> Auto-creates row in Appointments table for Psychologist Dr. Usman
8. Psychologist logs in as usman@biit.edu.pk
   - Views appointment list -> Taps "EEG Graph"
   - Uses interactive scrubber to view exact brainwave values at each question
```

---

## 10. API Endpoints

Base URL: `http://<backend-ip>:8000`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login user |
| POST | `/auth/register` | Register user |
| POST | `/session/start` | Create assessment session |
| POST | `/session/end` | Stop session & run scoring pipeline |
| GET | `/session/{id}` | Fetch session details |
| POST | `/eeg/connect` | Start EEG stream background thread |
| POST | `/eeg/disconnect` | Stop EEG stream background thread |
| GET | `/eeg/status/{id}` | Check EEG stream connection status |
| POST | `/eeg/marker` | Tag EEG stream with active question ID |
| GET | `/eeg/timeline/{id}` | Fetch all snapshots & question markers for psychologist graph |
| WS | `/ws/eeg/{id}` | Real-time WebSocket live vitals feed |
| POST | `/questionnaire/submit` | Submit stage answers |
| GET | `/questionnaire/questions/{stage}` | Fetch questions for stage |
| POST | `/sensors/pulse` | Record pulse reading |
| POST | `/sensors/bp` | Record blood pressure reading |
| POST | `/sensors/emotion` | Submit camera frame Base64 for DeepFace |
| GET | `/results/{session_id}` | Fetch full session result breakdown |
| GET | `/psychologist/{id}/appointments` | Fetch psychologist appointments |
| POST | `/psychologist/feedback` | Save question usefulness star rating |
| GET | `/psychologist/session/{id}/answers` | Fetch student's questionnaire answers |
| GET | `/advisor/{id}/students` | Fetch advisor's alerted students |

---

## 11. Questionnaire Stages

- **Stage 1 (Emotional Health):** Stress, mood swings, anxiety, panic feelings (30%)
- **Stage 2 (Functional Health):** Sleep quality, focus, mental fatigue, routine (20%)
- **Stage 3 (Context & Environment):** Academic/family pressure for students; workload for teachers (10% / 15%)
- **Stage 4 (Social Isolation):** Social withdrawal, feeling alone (15%)
- **Stage 5 (Crisis Screening):** Hopelessness, self-harm thoughts (5%) — **Safety Override Trigger**

---

## 12. Technology Choices

- **Python + FastAPI:** High-performance async REST + WebSocket framework; native scientific library support (`numpy`, `scipy`).
- **BlueMuse + LSL (Lab Streaming Layer):** Standard biomedical research protocol for real-time high-rate EEG transmission over BLE on Windows.
- **Butterworth Bandpass Filter:** Maximally flat passband filter (1–40 Hz) eliminating powerline hum and motion noise without phase distortion.
- **Fast Fourier Transform (FFT):** Mathematically optimal conversion from time-domain voltage to frequency-domain spectral power spectrum ($\mu\text{V}^2$).
- **Flutter + Provider:** Reactive cross-platform UI with clean separation of presentation and business logic.
- **Microsoft SQL Server:** Industrial relational storage with full relational integrity constraints and transaction isolation.

---

## 13. How to Test the System — Step-by-Step Verification Guide

Follow these exact steps to test the entire end-to-end workflow:

### Step 1: Start BlueMuse (Windows EEG Bridge)
1. Turn on your **Muse 2 / Muse S** headset.
2. Open **BlueMuse** on your Windows PC.
3. Wait for your headset to appear in the device list.
4. Click **Start Streaming**.
5. Confirm BlueMuse displays: `Streaming... (LSL Outlet: Muse-EEG)`.

---

### Step 2: Start the FastAPI Backend Server
Open a terminal in the project backend folder:
```powershell
venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000 --reload
```
Verify terminal output says:
```
=== Virtual Clinic Backend starting up ===
Database connection OK — SQL Server time: ...
=== Virtual Clinic Backend is READY ===
```

---

### Step 3: Launch the Flutter Mobile App
In another terminal:
```powershell
cd frontend
flutter run
```

---

### Step 4: Test Student Assessment & Real-Time EEG Stream
1. Log in as a student:
   - **Email:** `2023-arid-0167@biit.edu.pk`
   - **Password:** `password123`
2. Tap **"Start Assessment"** on the home dashboard.
3. On the Session screen, tap **"Connect EEG"**:
   - The status badge will change from *Not Connected* $\rightarrow$ *Live*.
   - Live Vitals will display real-time **Alpha ($\mu\text{V}^2$)**, **Beta ($\mu\text{V}^2$)**, **Theta ($\mu\text{V}^2$)**, and a dynamic **Stress Index** progress bar updating every 2 seconds.
4. Tap **"Fill Questionnaire"**:
   - Select answers for Stage 1. As you tap choices, `/eeg/marker` tags the brainwave snapshot with the question number behind the scenes.
   - Complete Stages 2, 3, 4, 5.
5. Tap **"End Session & Get Report"**:
   - Backend automatically stops the EEG stream, runs score fusion, and generates your mental health report.
   - If scores indicate High Risk, an appointment is auto-booked for the psychologist.

---

### Step 5: Test Psychologist Dashboard & Interactive EEG Timeline Graph
1. Log out of the student account.
2. Log in as the psychologist:
   - **Email:** `usman@biit.edu.pk`
   - **Password:** `doctor123`
3. You will see the appointment for student **2023-ARID-0167**.
4. Tap the **"EEG Graph"** button:
   - An interactive **EEG Timeline** modal will open.
   - Use the **Slider** or the **Forward/Backward Arrows** to scrub through session time.
   - Observe how the **Stress Index**, **Alpha**, **Beta**, and **Theta** values change at each point.
   - Look at the top right of the modal to see the **Question #** tag (e.g. `Question #3`) active at that exact timestamp.
5. Tap **"Q-Answers"** to view the student's exact questionnaire choices and submit 1–5 star usefulness ratings for adaptive weighting.

---

*End of Documentation*  
*Project: Virtual Clinic — AI-Powered Mental Health Monitoring System*  
*BIIT University*
