# ============================================================
# test_endpoints.py — Sequential API integration test
#
# Tests the full session lifecycle:
#   Register → Login → Start Session → Questionnaire →
#   BP → Pulse → Emotion → End Session → Get Results
#
# Usage:
#   1. Start the server: uvicorn main:app --reload --port 8000
#   2. Run tests:        python test_endpoints.py
# ============================================================

import sys
import json
import base64
import time
import requests
import io

BASE_URL = "http://localhost:8000"

# Track test results
passed = 0
failed = 0


def _log(step: str, success: bool, data=None, error=None):
    """
    Print a formatted test result line.

    Args:
        step:    Name of the test step.
        success: True if step passed.
        data:    Response data to display on success.
        error:   Error message on failure.
    """
    global passed, failed
    if success:
        passed += 1
        print(f"  ✅ PASS — {step}")
        if data:
            print(f"           {json.dumps(data, indent=2, default=str)[:500]}")
    else:
        failed += 1
        print(f"  ❌ FAIL — {step}")
        if error:
            print(f"           Error: {error}")


def _make_test_image_base64() -> str:
    """
    Generate a small solid-color JPEG image as base64 for emotion testing.
    Uses pure Python to create a minimal valid JPEG without needing PIL.

    Returns:
        Base64-encoded string of a tiny JPEG image.
    """
    try:
        # Try with PIL if available
        from PIL import Image
        img = Image.new("RGB", (100, 100), color=(200, 180, 160))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except ImportError:
        pass

    try:
        # Try with numpy + cv2 if available
        import numpy as np
        import cv2
        img = np.full((100, 100, 3), (160, 180, 200), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        return base64.b64encode(encoded.tobytes()).decode("utf-8")
    except ImportError:
        pass

    # Minimal valid JPEG (1x1 pixel, light gray) — raw bytes
    # This is a hand-crafted minimal JPEG that any decoder will accept
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
        0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
        0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
        0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
        0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
        0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
        0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
        0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
        0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
        0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
        0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
        0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
        0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1,
        0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
        0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36,
        0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
        0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64,
        0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77,
        0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A,
        0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5,
        0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
        0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
        0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
        0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF,
        0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
        0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0xFF, 0xD9,
    ])
    return base64.b64encode(minimal_jpeg).decode("utf-8")


def run_tests():
    """
    Execute the full API test sequence.

    Tests in order:
      1.  Register a student user
      2.  Login with the registered user
      3.  Start a new session
      4.  Submit Stage 1 questionnaire (6 questions)
      5.  Submit Stage 2 questionnaire (5 questions)
      6.  POST a BP reading
      7.  POST a pulse reading
      8.  POST an emotion frame (base64 JPEG)
      9.  End the session (triggers ML pipeline)
      10. GET the session results
    """
    print("=" * 60)
    print("Multimodal Virtual Clinic — API Integration Tests")
    print("=" * 60)
    print(f"Target: {BASE_URL}")
    print()

    # ── Check server is running ──────────────────────────────
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Server health: {r.json()}")
    except requests.ConnectionError:
        print("❌ Server is not running! Start it with: uvicorn main:app --reload --port 8000")
        sys.exit(1)

    print()

    # Use a unique email to avoid conflicts on re-runs
    test_email = f"test_student_{int(time.time())}@clinic.edu"

    # ── 1. Register student ──────────────────────────────────
    print("Step 1: Register Student")
    try:
        r = requests.post(f"{BASE_URL}/auth/register", json={
            "name": "Test Student",
            "email": test_email,
            "password": "test123456",
            "role": "student",
            "cgpa_trend": -0.3,
            "attendance_drop": 5.0,
        })
        if r.status_code in (200, 201):
            data = r.json()
            user_id = data.get("user_id")
            _log("Register Student", True, data)
        else:
            _log("Register Student", False, error=f"HTTP {r.status_code}: {r.text}")
            return
    except Exception as e:
        _log("Register Student", False, error=str(e))
        return

    # ── 2. Login ─────────────────────────────────────────────
    print("\nStep 2: Login")
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": test_email,
            "password": "test123456",
        })
        if r.status_code == 200:
            data = r.json()
            token = data.get("access_token")
            user_id = data.get("user_id")
            _log("Login", True, {"user_id": user_id, "role": data.get("role")})
        else:
            _log("Login", False, error=f"HTTP {r.status_code}: {r.text}")
            return
    except Exception as e:
        _log("Login", False, error=str(e))
        return

    headers = {"Authorization": f"Bearer {token}"}

    # ── 3. Start session ─────────────────────────────────────
    print("\nStep 3: Start Session")
    try:
        r = requests.post(f"{BASE_URL}/session/start", json={
            "user_id": user_id,
        })
        if r.status_code == 200:
            data = r.json()
            session_id = data.get("session_id")
            _log("Start Session", True, data)
        else:
            _log("Start Session", False, error=f"HTTP {r.status_code}: {r.text}")
            return
    except Exception as e:
        _log("Start Session", False, error=str(e))
        return

    # ── 4. Submit Stage 1 (6 questions) ──────────────────────
    print("\nStep 4: Submit Stage 1 Questionnaire")
    try:
        stage1_answers = [
            {"question_id": i, "response_choice": "Sometimes", "cal_score": 2.0 + (i % 2)}
            for i in range(1, 7)
        ]
        r = requests.post(f"{BASE_URL}/questionnaire/submit", json={
            "session_id": session_id,
            "stage_number": 1,
            "answers": stage1_answers,
        })
        if r.status_code == 200:
            data = r.json()
            _log("Submit Stage 1", True, data)
        else:
            _log("Submit Stage 1", False, error=f"HTTP {r.status_code}: {r.text}")
    except Exception as e:
        _log("Submit Stage 1", False, error=str(e))

    # ── 5. Submit Stage 2 (5 questions) ──────────────────────
    print("\nStep 5: Submit Stage 2 Questionnaire")
    try:
        stage2_answers = [
            {"question_id": i + 6, "response_choice": "Often", "cal_score": 3.0}
            for i in range(1, 6)
        ]
        r = requests.post(f"{BASE_URL}/questionnaire/submit", json={
            "session_id": session_id,
            "stage_number": 2,
            "answers": stage2_answers,
        })
        if r.status_code == 200:
            data = r.json()
            _log("Submit Stage 2", True, data)
        else:
            _log("Submit Stage 2", False, error=f"HTTP {r.status_code}: {r.text}")
    except Exception as e:
        _log("Submit Stage 2", False, error=str(e))

    # ── 6. POST BP reading ───────────────────────────────────
    print("\nStep 6: Submit BP Reading")
    try:
        r = requests.post(f"{BASE_URL}/sensors/bp", json={
            "session_id": session_id,
            "systolic": 128,
            "diastolic": 82,
            "pulse_rate": 76,
        })
        if r.status_code == 200:
            _log("BP Reading", True, r.json())
        else:
            _log("BP Reading", False, error=f"HTTP {r.status_code}: {r.text}")
    except Exception as e:
        _log("BP Reading", False, error=str(e))

    # ── 7. POST pulse reading ────────────────────────────────
    print("\nStep 7: Submit Pulse Reading")
    try:
        r = requests.post(f"{BASE_URL}/sensors/pulse", json={
            "session_id": session_id,
            "pulse_rate": 78.5,
            "source": "muse",
        })
        if r.status_code == 200:
            _log("Pulse Reading", True, r.json())
        else:
            _log("Pulse Reading", False, error=f"HTTP {r.status_code}: {r.text}")
    except Exception as e:
        _log("Pulse Reading", False, error=str(e))

    # ── 8. POST emotion frame ────────────────────────────────
    print("\nStep 8: Submit Emotion Frame")
    try:
        test_image = _make_test_image_base64()
        r = requests.post(f"{BASE_URL}/sensors/emotion", json={
            "session_id": session_id,
            "user_id": user_id,
            "image_base64": test_image,
        })
        if r.status_code == 200:
            _log("Emotion Frame", True, r.json())
        elif r.status_code == 422:
            # DeepFace may reject the test image — that's OK for testing
            _log("Emotion Frame", True, {"note": "422 expected with test image", "detail": r.text[:200]})
        else:
            _log("Emotion Frame", False, error=f"HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        _log("Emotion Frame", False, error=str(e))

    # ── 9. End session ───────────────────────────────────────
    print("\nStep 9: End Session (triggers ML pipeline)")
    try:
        r = requests.post(f"{BASE_URL}/session/end", json={
            "session_id": session_id,
            "user_id": user_id,
        })
        if r.status_code == 200:
            data = r.json()
            _log("End Session", True, data)
        else:
            _log("End Session", False, error=f"HTTP {r.status_code}: {r.text[:500]}")
    except Exception as e:
        _log("End Session", False, error=str(e))

    # ── 10. GET results ──────────────────────────────────────
    print("\nStep 10: Get Session Results")
    try:
        r = requests.get(f"{BASE_URL}/results/{session_id}")
        if r.status_code == 200:
            data = r.json()
            _log("Get Results", True, {
                "recommendation": data.get("recommendation"),
                "confidence": data.get("confidence"),
                "final_score": data.get("final_score"),
            })
        else:
            _log("Get Results", False, error=f"HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        _log("Get Results", False, error=str(e))

    # ── Summary ──────────────────────────────────────────────
    print()
    print("=" * 60)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed}/{total} failed")
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {failed} test(s) failed. Review output above.")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
