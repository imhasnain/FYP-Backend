"""Full end-to-end test of the backend API."""
import requests, json, sys

BASE = "http://localhost:8000"

def ok(label, resp):
    if resp.status_code >= 400:
        print(f"  FAIL [{resp.status_code}]: {label}")
        print(f"     {resp.text[:300]}")
        sys.exit(1)
    print(f"  OK  {label}: {json.dumps(resp.json(), default=str)[:120]}")
    return resp.json()

print("\n=== 1. Health Check ===")
ok("GET /", requests.get(f"{BASE}/"))
ok("GET /health", requests.get(f"{BASE}/health"))

print("\n=== 2. Auth ===")
login = ok("POST /auth/login (demo student)", requests.post(f"{BASE}/auth/login",
    json={"email": "student@clinic.edu", "password": "password123"}))
user_id = login["user_id"]
token = login["access_token"]

print("\n=== 3. Start Session ===")
sess = ok("POST /session/start", requests.post(f"{BASE}/session/start",
    json={"user_id": user_id}))
session_id = sess["session_id"]
print(f"  >> session_id = {session_id}")

print("\n=== 4. Questionnaire ===")
stages = ok("GET /questionnaire/stages", requests.get(f"{BASE}/questionnaire/stages"))
print(f"  >> {len(stages)} stages loaded")

for stage_num in range(1, 6):
    qs = ok(f"GET /questionnaire/questions/{stage_num}",
        requests.get(f"{BASE}/questionnaire/questions/{stage_num}?role=student"))
    answers = [{"question_id": q["question_id"], "response_choice": 1, "cal_score": 1.0 * q["weight"]} for q in qs]
    submit = ok(f"POST /questionnaire/submit (stage {stage_num})",
        requests.post(f"{BASE}/questionnaire/submit",
            json={"session_id": session_id, "stage_number": stage_num, "answers": answers}))
    print(f"  >> stage {stage_num}: passed={submit['passed']}, next_stage={submit['next_stage']}")

print("\n=== 5. End Session ===")
end = ok("POST /session/end", requests.post(f"{BASE}/session/end",
    json={"session_id": session_id, "user_id": user_id}))
print(f"  >> recommendation: {end['recommendation']}")
print(f"  >> final_score:    {end['final_score']}")

print("\n=== 6. Get Result ===")
result = ok(f"GET /results/{session_id}", requests.get(f"{BASE}/results/{session_id}"))
print(f"  >> risk_class: {result['recommendation']}")

print("\n=== 7. User History ===")
hist = ok(f"GET /results/user/{user_id}", requests.get(f"{BASE}/results/user/{user_id}"))
print(f"  >> {len(hist['sessions'])} total sessions in history")

print("\n\n*** ALL TESTS PASSED — Backend is fully working! ***")
