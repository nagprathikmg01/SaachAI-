"""
session_store.py — Local JSON store for Meet-plugin interview sessions.

Stores sessions in backend/meet_sessions.json.
Each session has: id, candidate_name, interviewer_name, role, timestamp,
                   duration_s, final_score, verdict, flags, questions,
                   plagiarism_risk, summary, personal_text.
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SESSIONS_FILE = Path(__file__).parent.parent / "meet_sessions.json"

# ── Seed demo data if file is empty ──────────────────────────────────────────
DEMO_SESSIONS = [
    {
        "id": "demo-001",
        "candidate_name": "Arjun Mehta",
        "interviewer_name": "HR Team",
        "role": "Senior Backend Engineer",
        "timestamp": "2026-05-10T09:15:00Z",
        "duration_s": 2340,
        "final_score": 82.4,
        "verdict": "GENUINE",
        "strong_signals": 1,
        "flags": ["Minor vocabulary increase in technical round"],
        "questions": [
            "Can you give a concrete example of your Kubernetes scaling work?",
            "Walk me through the CI/CD pipeline you implemented."
        ],
        "plagiarism_risk": 12.0,
        "summary": "Low style shift (18.2/100). Communication style is consistent across both rounds. Responses appear naturally authored.",
        "personal_text": "Hi, I'm Arjun. I've been working in backend development for about 6 years..."
    },
    {
        "id": "demo-002",
        "candidate_name": "Priya Sharma",
        "interviewer_name": "Tech Lead",
        "role": "ML Engineer",
        "timestamp": "2026-05-11T11:30:00Z",
        "duration_s": 1820,
        "final_score": 51.3,
        "verdict": "SUSPICIOUS",
        "strong_signals": 5,
        "flags": [
            "Sudden vocabulary sophistication increase in technical round",
            "High density of epistemic hedging phrases detected",
            "Sentence rhythm became unnaturally uniform",
            "Passive voice usage increased by 38%"
        ],
        "questions": [
            "Can you explain that concept in your own words, without using jargon?",
            "What was your specific role in that ML project?",
            "Walk me through implementing that from scratch, step by step."
        ],
        "plagiarism_risk": 62.0,
        "summary": "High style shift (54.7/100). The technical response shows a markedly different communication fingerprint — may indicate pre-written or AI-assisted content.",
        "personal_text": "Hey, so I've been into machine learning for like three years now, mostly doing some projects on the side..."
    },
    {
        "id": "demo-003",
        "candidate_name": "Rohan Das",
        "interviewer_name": "HR Team",
        "role": "Frontend Developer",
        "timestamp": "2026-05-12T14:00:00Z",
        "duration_s": 1560,
        "final_score": 91.0,
        "verdict": "GENUINE",
        "strong_signals": 0,
        "flags": [],
        "questions": ["Can you elaborate on your React performance optimization approach?"],
        "plagiarism_risk": 5.0,
        "summary": "Low style shift (8.1/100). Communication style is highly consistent. Responses appear naturally authored with strong authenticity signals.",
        "personal_text": "I'm Rohan, frontend dev for 4 years, mainly React and TypeScript..."
    },
]


def _load() -> list:
    if not SESSIONS_FILE.exists():
        _save(DEMO_SESSIONS)
        return DEMO_SESSIONS
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("[session_store] Load error: %s", e)
        return []


def _save(sessions: list) -> None:
    try:
        SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("[session_store] Save error: %s", e)


def save_session(
    candidate_name: str,
    interviewer_name: str,
    role: str,
    duration_s: int,
    final_score: float,
    verdict: str,
    strong_signals: int,
    flags: list,
    questions: list,
    plagiarism_risk: float,
    summary: str,
    personal_text: str = "",
) -> str:
    sessions = _load()
    session_id = str(uuid.uuid4())[:8]
    session = {
        "id": session_id,
        "candidate_name": candidate_name.strip(),
        "interviewer_name": interviewer_name.strip(),
        "role": role.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_s": duration_s,
        "final_score": round(final_score, 1),
        "verdict": verdict,
        "strong_signals": strong_signals,
        "flags": flags,
        "questions": questions,
        "plagiarism_risk": round(plagiarism_risk, 1),
        "summary": summary,
        "personal_text": personal_text[:500],  # store first 500 chars
    }
    sessions.insert(0, session)  # newest first
    _save(sessions)
    logger.info("[session_store] Saved session %s for %s", session_id, candidate_name)
    return session_id


def list_sessions(limit: int = 50) -> list:
    sessions = _load()
    return sessions[:limit]


def get_session(session_id: str) -> dict | None:
    for s in _load():
        if s.get("id") == session_id:
            return s
    return None
