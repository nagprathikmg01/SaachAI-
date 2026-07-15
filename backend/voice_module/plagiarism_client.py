"""
plagiarism_client.py — Winston AI plagiarism detection client.

Uses the Winston AI REST API (POST https://api.gowinston.ai/v2/plagiarism).
Unlike PlagiarismCheck.org, Winston AI is synchronous — a single POST returns
the full result immediately (no polling required).

Returns {score, sources} on success.
Returns {score: None, sources: [], error: str} on any failure so the caller
never has to catch exceptions from this function.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import httpx

logger = logging.getLogger(__name__)

_BASE    = "https://api.gowinston.ai/v2"
_MIN_CHARS = 100   # Winston AI minimum: 100 characters
_TIMEOUT   = 60    # seconds — synchronous call, so needs generous timeout


def _api_key() -> str:
    k = os.getenv("WINSTON_AI_API_KEY", "").strip()
    if not k:
        raise RuntimeError("WINSTON_AI_API_KEY is not set in environment")
    return k


def _parse(body: dict) -> dict:
    """Normalise Winston AI response into {score, sources}."""
    result_obj = body.get("result", {})
    score = float(result_obj.get("score", 0) or 0)
    
    # Winston sometimes leaves score=0 but populates totalPlagiarismWords
    if score == 0 and result_obj.get("textWordCounts", 0) > 0:
        plag_words = result_obj.get("totalPlagiarismWords", 0)
        score = (plag_words / result_obj.get("textWordCounts", 1)) * 100

    raw_sources = body.get("sources", []) or []
    sources = [
        {
            "url":        s.get("url", ""),
            "title":      s.get("title", "") or s.get("url", "Unknown"),
            "similarity": float(s.get("score", 0)),
        }
        for s in raw_sources if s.get("url")
    ]
    sources.sort(key=lambda x: x["similarity"], reverse=True)

    return {"score": round(score, 2), "sources": sources[:10]}


async def check_text(text: str) -> dict:
    """
    Submit text to Winston AI plagiarism API and return result.

    Returns {score: float, sources: list} on success.
    Returns {score: None, sources: [], error: str} on any failure.
    """
    text = (text or "").strip()
    if len(text) < _MIN_CHARS:
        return {
            "score": None,
            "sources": [],
            "error": f"Text too short for plagiarism check (minimum {_MIN_CHARS} characters required).",
        }

    try:
        key = _api_key()
    except RuntimeError as e:
        return {"score": None, "sources": [], "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/plagiarism",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "language": "en"},
            )

        logger.info("[winston] status=%s", r.status_code)

        if not r.is_success:
            return {
                "score": None,
                "sources": [],
                "error": f"Winston AI error {r.status_code}: {r.text[:200]}",
            }

        body = r.json()
        result = _parse(body)
        logger.info("[winston] plag_score=%.1f%% citations=%d", result["score"], len(result["sources"]))
        return result

    except Exception as exc:
        logger.exception("[winston] check_text failed")
        return {"score": None, "sources": [], "error": str(exc)}


async def check_ai_content(text: str) -> dict:
    """
    Submit text to Winston AI predict endpoint to detect AI usage.
    Returns {score: float} where score is the probability of it being AI (0 to 100).
    Returns {score: None, error: str} on failure.
    Requires minimum 300 chars.
    """
    text = (text or "").strip()
    if len(text) < 300:
        return {"score": None, "error": "Text too short for AI Detection (minimum 300 characters required)."}

    try:
        key = _api_key()
    except RuntimeError as e:
        return {"score": None, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{_BASE}/ai-content-detection",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"text": text, "language": "en", "sentences": False},
            )

        logger.info("[winston] ai_detection status=%s", r.status_code)

        if not r.is_success:
            return {"score": None, "error": f"AI Detect error {r.status_code}: {r.text[:200]}"}

        body = r.json()
        # Winston AI returns `score` as human-probability.
        # The value may be 0-1 (fractional) or 0-100 (percentage) depending on version.
        # We normalise to 0-100 and invert to get the AI probability.
        raw = float(body.get("score", 1.0))
        # If score > 1, it is already on a 0-100 scale
        human_pct = raw if raw > 1.0 else raw * 100.0
        ai_score  = max(0.0, min(100.0, 100.0 - human_pct))

        logger.info("[winston] ai_score=%.1f%%", ai_score)
        return {"score": round(ai_score, 1), "error": None}

    except Exception as exc:
        logger.exception("[winston] check_ai_content failed")
        return {"score": None, "error": str(exc)}
