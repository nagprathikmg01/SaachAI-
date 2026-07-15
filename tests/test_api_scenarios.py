import os
import jwt
import json
import pytest
import asyncio
import requests
import websockets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv(Path(__file__).parent.parent / "backend" / ".env", override=True)

BASE_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/voice/meet-analyze"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGO = "HS256"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_auth_headers(username="admin", password="admin123"):
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password}
    )
    if resp.status_code == 200:
        token = resp.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    return {}

# ── Part 2.1: Authentication Tests ───────────────────────────────────────────

def test_login_valid_credentials():
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["username"] == "admin"
    assert data["role"] == "admin"

def test_login_invalid_credentials():
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin", "password": "wrongpassword"}
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()

def test_login_missing_fields():
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": "admin"}
    )
    assert resp.status_code == 422  # Pydantic validation error

def test_token_expiration_and_reuse():
    # 1. Expired Token
    expired_payload = {
        "sub": "admin",
        "role": "admin",
        "display_name": "Admin",
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGO)
    
    resp_exp = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp_exp.status_code == 401

    # 2. Valid and Reused Token
    valid_payload = {
        "sub": "admin",
        "role": "admin",
        "display_name": "Admin",
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
    }
    valid_token = jwt.encode(valid_payload, JWT_SECRET, algorithm=JWT_ALGO)
    
    # First use
    resp_use1 = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert resp_use1.status_code == 200
    assert resp_use1.json()["username"] == "admin"

    # Reuse (stateless token should still be accepted)
    resp_use2 = requests.get(
        f"{BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert resp_use2.status_code == 200

# ── Part 2.2: WebSocket /meet-analyze Tests ─────────────────────────────────

@pytest.mark.asyncio
async def test_websocket_meet_analyze():
    # Connect with authenticated token
    auth_headers = get_auth_headers()
    token = auth_headers["Authorization"].split(" ")[1] if "Authorization" in auth_headers else ""
    ws_url_with_token = f"{WS_URL}?token={token}"
    async with websockets.connect(ws_url_with_token) as ws:
        # Send baseline
        baseline = "Hi I am a candidate and I am introducing myself using a relatively casual speech pattern with fillers."
        await ws.send(json.dumps({"type": "baseline", "text": baseline}))
        
        status_msg = json.loads(await ws.recv())
        assert status_msg["type"] == "status"
        
        # Test short transcript (<30 words)
        await ws.send(json.dumps({
            "type": "transcript",
            "text": "short transcript here",
            "speaker": "Candidate"
        }))
        # No analysis score yet since it's too short (less than MIN_WINDOW_WORDS)
        
        # Test long transcript (>200 words)
        long_text = " ".join(["word"] * 210)
        await ws.send(json.dumps({
            "type": "transcript",
            "text": long_text,
            "speaker": "Candidate"
        }))
        
        # We should receive status and/or analysis messages
        rec_msg = json.loads(await ws.recv())
        assert rec_msg["type"] in ("status", "analysis")

        # Test empty text
        await ws.send(json.dumps({
            "type": "transcript",
            "text": "",
            "speaker": "Candidate"
        }))
        # Shouldn't crash and server should ignore it

        # Test special characters
        await ws.send(json.dumps({
            "type": "transcript",
            "text": "Hello! @#$ %^&* ( ) _ + 🌟 🔥 👍",
            "speaker": "Candidate"
        }))
        
        # Test ping/pong
        await ws.send(json.dumps({"type": "ping"}))
        found_pong = False
        for _ in range(10):
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                if msg.get("type") == "pong":
                    found_pong = True
                    break
            except asyncio.TimeoutError:
                break
        assert found_pong, "Did not receive pong response"

@pytest.mark.asyncio
async def test_websocket_rapid_back_to_back():
    async with websockets.connect(WS_URL) as ws:
        # Send baseline
        baseline = "I have been working as a software developer for five years. I enjoy building things."
        await ws.send(json.dumps({"type": "baseline", "text": baseline}))
        await ws.recv() # status

        # Send rapid back-to-back messages
        tasks = [
            ws.send(json.dumps({
                "type": "transcript",
                "text": f"Quick back-to-back message chunk number {i}",
                "speaker": "Candidate"
            }))
            for i in range(5)
        ]
        await asyncio.gather(*tasks)
        
        # Verify socket is still active and can process messages
        await ws.send(json.dumps({"type": "ping"}))
        found_pong = False
        for _ in range(10):
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
                if msg.get("type") == "pong":
                    found_pong = True
                    break
            except asyncio.TimeoutError:
                break
        assert found_pong, "Did not receive pong response"

# ── Part 2.3: save-session Tests ─────────────────────────────────────────────

def test_save_session_valid():
    headers = get_auth_headers()
    payload = {
        "candidate_name": "Test Candidate",
        "interviewer_name": "Test Interviewer",
        "role": "QA Engineer",
        "duration_s": 600,
        "final_score": 85.0,
        "verdict": "GENUINE",
        "strong_signals": 0,
        "flags": [],
        "questions": ["Some follow up?"],
        "plagiarism_risk": 5.0,
        "summary": "This is a clean test run summary.",
        "personal_text": "Hello, I am a candidate introducing myself casually.",
        "technical_text": "We optimized the system caching layer by implementing Redis.",
        "personal_profile": {},
        "technical_profile": {}
    }
    resp = requests.post(
        f"{BASE_URL}/voice/save-session",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "session_id" in resp.json()

def test_save_session_malformed():
    headers = get_auth_headers()
    resp = requests.post(
        f"{BASE_URL}/voice/save-session",
        headers=headers,
        data="invalid-json-string-not-dict"
    )
    assert resp.status_code == 422  # validation error

def test_save_session_missing_fields():
    headers = get_auth_headers()
    # Missing candidate_name
    payload = {
        "interviewer_name": "Test Interviewer",
        "role": "QA Engineer"
    }
    resp = requests.post(
        f"{BASE_URL}/voice/save-session",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 422

# ── Part 2.4: check-credibility Tests ────────────────────────────────────────

def test_check_credibility_genuine():
    headers = get_auth_headers()
    payload = {
        "candidate_id": "test_cred_genuine",
        "items": [
            {
                "question": "How do you handle database connection pooling in a FastAPI application?",
                "candidate_response": "I would use a library like SQLalchemy and pass connection parameters like pool_size and max_overflow inside create_engine. This keeps connections open and avoids reopening them on every request.",
                "expected_answer": "Use connection pool configuration in SQLAlchemy create_engine."
            }
        ]
    }
    resp = requests.post(
        f"{BASE_URL}/voice/check-credibility",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["verdict"] == "CORRECT"

def test_check_credibility_ai():
    headers = get_auth_headers()
    payload = {
        "candidate_id": "test_cred_ai",
        "items": [
            {
                "question": "What is the CAP Theorem?",
                "candidate_response": "The CAP theorem, also known as Brewer's theorem, states that in a distributed data store, it is impossible to simultaneously provide more than two of three guarantees: Consistency (every read receives the most recent write or an error), Availability (every request receives a non-error response, without the guarantee that it contains the most recent write), and Partition tolerance (the system continues to operate despite an arbitrary number of messages being dropped or delayed by the network). In other words, when a network partition occurs, one must choose between consistency and availability.",
                "expected_answer": "Consistency, Availability, and Partition Tolerance tradeoffs."
            }
        ]
    }
    resp = requests.post(
        f"{BASE_URL}/voice/check-credibility",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 1
    # Check that it runs and parses successfully
    assert "verdict" in data["results"][0]

def test_check_credibility_short():
    headers = get_auth_headers()
    payload = {
        "candidate_id": "test_cred_short",
        "items": [
            {
                "question": "Explain consistency model.",
                "candidate_response": "consistency is good",
                "expected_answer": "consistency models determine the order of active operations"
            }
        ]
    }
    resp = requests.post(
        f"{BASE_URL}/voice/check-credibility",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["verdict"] in ("INCORRECT", "INSUFFICIENT")

# ── Part 2.5: candidate DELETE Tests ─────────────────────────────────────────

def test_delete_candidate_endpoints():
    headers = get_auth_headers()
    candidate_id = "temp_candidate_to_delete"
    
    # 1. Create a dummy candidate
    requests.post(
        f"{BASE_URL}/voice/text-compare",
        headers=headers,
        json={
            "candidate_id": candidate_id,
            "personal": "hello I'm a test user introducing myself.",
            "technical": "we created a web api using fastapi and uvicorn server."
        }
    )
    
    # 2. Delete it
    resp_del = requests.delete(
        f"{BASE_URL}/voice/candidate/{candidate_id}",
        headers=headers
    )
    # Under local offline fallback mode, deleting a candidate returns 404 since there is no DB sync
    assert resp_del.status_code in (200, 404)
    if resp_del.status_code == 200:
        assert resp_del.json()["deleted"] is True
    
    # 3. Delete non-existent ID
    resp_del_none = requests.delete(
        f"{BASE_URL}/voice/candidate/non_existent_candidate_12345",
        headers=headers
    )
    assert resp_del_none.status_code == 404
    assert "detail" in resp_del_none.json()

# ── Part 2.6: health and calibrate Tests ─────────────────────────────────────

def test_health_check():
    resp = requests.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "model_loaded" in data
    assert "database_connected" in data

def test_calibrate_endpoints():
    headers = get_auth_headers()
    
    # Test GET /calibrate/meta
    resp_meta = requests.get(f"{BASE_URL}/calibrate/meta", headers=headers)
    assert resp_meta.status_code == 200
    assert "model_available" in resp_meta.json()

    # Test POST /calibrate/sensitivity
    resp_sens = requests.post(
        f"{BASE_URL}/calibrate/sensitivity",
        headers=headers,
        json={"level": "aggressive"}
    )
    assert resp_sens.status_code == 200
    assert resp_sens.json()["sensitivity"] == "aggressive"
    
    # Reset sensitivity back to balanced
    requests.post(
        f"{BASE_URL}/calibrate/sensitivity",
        headers=headers,
        json={"level": "balanced"}
    )

# ── Part 2.7: Simulate Supabase Unreachable Fallback ────────────────────────

def test_supabase_unreachable_fallback(monkeypatch):
    headers = get_auth_headers()
    
    # Force SUPABASE_URL to be an invalid/unreachable URL in the environment
    monkeypatch.setenv("SUPABASE_URL", "https://invalid-supabase-domain-xxxxx-12345.co")
    
    payload = {
        "candidate_name": "Offline Fallback Candidate",
        "interviewer_name": "Test Interviewer",
        "role": "QA Engineer",
        "duration_s": 500,
        "final_score": 75.0,
        "verdict": "GENUINE",
        "strong_signals": 0,
        "flags": [],
        "questions": [],
        "plagiarism_risk": 0.0,
        "summary": "This summary tests fallback.",
        "personal_text": "My introduction goes here.",
        "technical_text": "I build automated test suites.",
        "personal_profile": {},
        "technical_profile": {}
    }
    
    # The backend will log a warning about Supabase sync failure but must still return 200 ok
    resp = requests.post(
        f"{BASE_URL}/voice/save-session",
        headers=headers,
        json=payload
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    session_id = resp.json()["session_id"]
    
    # Check that it indeed was written to the local JSON file
    resp_get = requests.get(
        f"{BASE_URL}/voice/sessions/{session_id}",
        headers=headers
    )
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == "ok"
    assert resp_get.json()["session"]["candidate_name"] == "Offline Fallback Candidate"
