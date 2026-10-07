@echo off
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Installing requirements...
pip install -r requirements.txt

echo Starting backend server...
uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
