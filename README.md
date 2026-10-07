# Virtual Clinic Backend

This repository contains the backend API for the multimodal virtual clinic system. It is designed to work as a shared backend service for different frontend apps, including React Native, iOS, .NET, and React web clients.

The API handles:
- user authentication and role-based access
- student and teacher session management
- questionnaire submissions and scoring
- BP, sensor, and EEG data ingestion
- result processing and report generation
- clinician/advisor endpoints
- real-time EEG streaming over WebSockets

This repo is backend-only. The frontend apps connect to the API through HTTP endpoints and WebSocket streams.

## Tech stack
- Python 3.10+
- FastAPI
- SQL Server + pyodbc
- JWT-based authentication
- WebSockets for EEG streaming
- Pydantic settings using `.env`

## Current backend responsibilities
- `/auth` — login and registration
- `/sessions` — session creation and retrieval
- `/questionnaire` — questionnaire flows and scoring
- `/sensors` — sensor health data endpoints
- `/results` — assessments and result data
- `/psychologist` and `/advisor` — clinician/advisor access
- `/ws/eeg/{session_id}` — live EEG stream
- `/docs` — Swagger UI for API testing
- `/health` — backend health check

## Project structure

- `main.py` — FastAPI app entry point
- `config.py` — environment-based application settings
- `database.py` — SQL Server connection logic
- `routers/` — API endpoint modules
- `models/` — request/response schemas
- `utils/` — JWT and time helper functions
- `processing/` — scoring and emotion-processing logic
- `hardware/` — external health device integrations
- `websocket/` — WebSocket handlers
- `database/` — SQL schema and database setup files

## Setup

1. Open a terminal in the project folder.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file from the example values below.
5. Configure your SQL Server connection details.
6. Start the API:

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

7. Open the API docs here:

   ```text
   http://localhost:8000/docs
   ```

## Environment configuration

Create a `.env` file in the project root. Example:

```env
DB_SERVER=localhost
DB_NAME=VirtualClinicDB
DB_USER=
DB_PASSWORD=
DB_TRUSTED_CONNECTION=true

SECRET_KEY=replace_with_a_long_random_secret_key
ALGORITHM=HS256
TOKEN_EXPIRE_MINUTES=480

WITHINGS_CLIENT_ID=
WITHINGS_CLIENT_SECRET=
WITHINGS_REDIRECT_URI=http://localhost:8000/withings/callback

EEG_BATCH_SIZE=50
EMOTION_INTERVAL_SECONDS=5
```

Important:
- Do not commit your real `.env` file.
- Do not push personal images, facial media, or sensitive local data.
- Keep this repo backend-only and share only code and configuration templates.

## Running the backend

From the project root:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

To test the server health:

```bash
curl http://localhost:8000/health
```

## Authentication

Use the `/auth/register` and `/auth/login` endpoints to create or sign in to users.

Example login request body:

```json
{
  "email": "student@example.com",
  "password": "yourpassword"
}
```

Store the returned access token and send it in the `Authorization` header for protected requests.

## Notes for team use

- This repository is meant to be shared across multiple frontend teams.
- Keep the backend generic and reusable.
- Frontend teams should supply their own UI, UX, and local app configuration.
- Do not store user photos, emotion screenshots, or raw recorded personal data in the shared repo.

## Health and documentation

- Swagger UI: `http://localhost:8000/docs`
- Health endpoint: `http://localhost:8000/health`

## License

This project is intended for academic and internal team use.
