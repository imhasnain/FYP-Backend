# AI Prompts Documentation
## Project: Multimodal Virtual Clinic for Psychologists
### Backend Development — Prompt History

## Phase 1 — Initial Backend Architecture & Scaffolding

### Prompt 1 — Full Backend Blueprint (Core Prompt)

```
You are a senior backend engineer. Build a complete, production-ready backend system for a Final Year Project (FYP) titled:

"Multimodal Virtual Clinic for Psychologists using EEG, BP, Pulse Rate, and Facial Emotion"

PROJECT OVERVIEW:
An AI-powered system for psychologists to assess and monitor mental health in university students and teachers. The system collects:
- Questionnaire responses (5 stages, each with a threshold score)
- EEG signals from Muse headset (continuous stream via muselsl + pylsl)
- Pulse/Heart Rate (from Muse PPG channel OR BLE BP machine)
- Blood Pressure (smart BLE BP machine via bleak library)
- Facial emotion (webcam frames analyzed by DeepFace)
```

---

### Prompt 2 — Redesigned Architecture with Login-Only Auth
> *Replaced registration flow with a pre-seeded login-only system.*

```
I am building a Final Year Project titled:
"Multimodal Virtual Clinic for Psychologists using AI"

Authentication System:
- Only Login page (no registration)
- Validate credentials from database
- Role-based access: Student, Teacher

Session Management:
- A session starts when the user begins the questionnaire
- Each session must have: session_id, user_id, start_time and end_time
- Each session stores: Questionnaire responses, EEG features, BP & Pulse readings, Facial emotion data
- A session represents one complete mental health evaluation

Questionnaire Flow: [5-stage questionnaire with threshold scoring]
```

---

## Phase 2 — Authentication & User Management

### Prompt 3 — Fix Student/Teacher Column Population
> *Registration was only saving user_id but not filling student/teacher-specific fields.*

```
Now, you have to test all the apis with sample data and test with database too.
Lastly when I register and I check student and teacher data the other columns of 
student and teachers are empty like they only have userid and student/teacher id.
No other data like student column should have cgpa and stuff.
```

### Prompt 4 — Role-Specific Data Validation Bug
> *Teacher was accepting student fields (cgpa, attendance) that it shouldn't.*

```
When I register a user it takes this API body:
{
  "name": "mirza",
  "email": "mirza123@gmail.com",
  "password": "112233445",
  "role": "teacher",
  "cgpa_trend": 10,
  "attendance_drop": 10,
  "workload_hrs": 20,
  "class_count": 21
}

I selected teacher and I gave cgpa and attendance still but teacher doesn't have that.
```

### Prompt 5 — Remove Registration, Use Pre-Seeded Data
> *Simplified the auth system to login-only with pre-existing DB records.*

```
We should remove register user and only have login.
The data will be already in database like student and teacher data.
cgpa or course load or attendance also update database schema.sql
```

### Prompt 6 — Remove Password Encryption
> *Simplified auth by removing bcrypt and using plain email/password matching.*

```
Ok one last thing is now lets remove encryption for now from everywhere in project 
frontend backend sql etc just remove it and use classic manual email and password.
```

---

## Phase 3 — Database & Schema Fixes

### Prompt 7 — Database Column Mismatch Errors
> *Backend logs showed SQL errors for missing columns like 'recommendation' and 'confidence'.*

```
2026-04-29 23:54:56 | ERROR | routers.results | get_user_history error: 
('42S22', "Invalid column name 'recommendation'. Invalid column name 'confidence'.")

[paste of full traceback]
```

### Prompt 8 — Fix INSERT Query Errors in Sessions & Results
> *Broken INSERT queries were preventing session history retrieval.*

```
[Paste of full backend error logs showing SQL constraint and column name mismatches 
in sessions and results routers — caused by schema mismatch with actual SQL Server DB]
```

---

## Phase 4 — ML Pipeline

### Prompt 9 — Train Custom Facial Emotion Model
> *Replaced DeepFace library with a custom CNN trained on FER-2013 dataset.*

```
Where is the AI model that is detecting emotions? In which folder is it 
because even though I was happy it predicted sad.
```

Followed by:
```
I don't like that. I think we should train our own model for that and use it in this project.
```

### Prompt 10 — Fix Training Script Path Error
> *Training script was failing because the FER-2013 dataset folder structure wasn't being found.*

```
Step 1: Get the Dataset. You will need an emotion dataset. The most common one is 
FER-2013 (available for free on Kaggle). Download it and organize the images into 
this exact folder structure inside your Backend/ml folder:

Backend/ml/dataset/
  ├── train/
  │   ├── angry/
  │   ├── happy/
  │   └── ... (fear, disgust, neutral, sad, surprise)
  └── validation/
      ├── angry/
      ├── happy/
      └── ...

I have done this but I still get this error:
[TensorFlow import error traceback]
```

### Prompt 11 — EEG Window Analysis Configuration
> *Changed EEG analysis strategy to a 10-minute rolling window.*

```
What if we do 10 min window Analysis time, would it be better?
And images should be taken after every 5 seconds and map it with questionnaire model prediction.
```

---

## Phase 5 — API Testing & Validation

### Prompt 12 — Build Full Automated API Test Suite
> *Created a complete test script covering all endpoints with real sample data.*

```
Now, you have to test all the APIs with sample data and test with database too.
```

---



### Prompt 13 — Port Access Error
> *Server failed to start due to Windows port permission issue.*

```
>> uvicorn main:app --reload --host 0.0.0.0 --port 8000
ERROR: [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions
```

## Phase 6 — Code Cleanup & Documentation

### Prompt 14 — Clean Up AI-Generated Code
> *Reviewed and cleaned redundant/bloated code produced during vibe-coding sessions.*

```
Now leave BP and EEG modal for later.
Go through whole project, clean the code. I have already ran it, its working.
Just remove extra stuff, clean the code because its made by AI agent vibe code.
Don't change too much, it is already according to my requirement.
```


## Summary Table

| # | Phase | What Was Built / Fixed |
|---|-------|------------------------|
| 1 | Architecture | Full backend skeleton (FastAPI, SQL Server, all routers) |
| 2 | Architecture | Redesigned to login-only with pre-seeded user data |
| 3 | Auth | Fixed student/teacher column population on registration |
| 4 | Auth | Fixed role-specific field validation (teacher vs student) |
| 5 | Auth | Removed registration, login-only with pre-seeded DB |
| 6 | Auth | Removed password encryption, plain credentials |
| 7 | Database | Fixed SQL column name mismatches in results router |
| 8 | Database | Fixed broken INSERT queries in sessions/results |
| 9 | ML | Replaced DeepFace with custom CNN emotion model |
| 10 | ML | Fixed FER-2013 dataset path error in training script |
| 11 | ML | Configured 10-minute EEG window + 5-second emotion sampling |
| 12 | Testing | Created full automated API test suite |
| 13 | Deployment | Resolved Windows port access permission error |
| 14 | Cleanup | Cleaned AI-generated boilerplate from all modules |

