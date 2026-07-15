"""
routes.py — FastAPI router for the voice interview module.

All routes are mounted under the /voice prefix by server.py.
Includes:
  - Audio transcription with rich confidence/pause signals
  - Style shift + plagiarism analysis
  - Slack webhook notifications on suspicious verdicts
  - Simple in-memory rate limiting
"""

import asyncio
import logging
import os
import time
from collections import defaultdict
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel

try:
    from .style_comparator import calculate_style_shift
    from .plagiarism_client import check_text as plag_check, check_ai_content as ai_check
    from .storage import delete_candidate, get_candidate, list_candidates, save_response, save_analysis
    from .transcriber import transcribe_audio
    from .credibility_checker import check_answer_credibility
except ImportError:
    from backend.voice_module.style_comparator import calculate_style_shift
    from backend.voice_module.plagiarism_client import check_text as plag_check, check_ai_content as ai_check
    from backend.voice_module.storage import delete_candidate, get_candidate, list_candidates, save_response, save_analysis
    from backend.voice_module.transcriber import transcribe_audio
    from backend.voice_module.credibility_checker import check_answer_credibility

try:
    from auth_routes import _get_current_user
except ImportError:
    from backend.auth_routes import _get_current_user



logger = logging.getLogger(__name__)
router = APIRouter(tags=["Voice Interview"])


# ── Rate Limiter ──────────────────────────────────────────────────────────────
# File-backed sliding window per IP — survives HF Space restarts.
# Falls back gracefully if rate_limiter import fails.
try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    from rate_limiter import RateLimiter as _RL
    _rl_transcribe = _RL(max_requests=5,  window_seconds=60)
    _rl_plagiarism = _RL(max_requests=3,  window_seconds=60)
    _rl_compare    = _RL(max_requests=10, window_seconds=60)
    def _check_rate(request: Request, limit: int, window: int, key_suffix: str = "") -> None:
        if os.getenv("TESTING") == "true":
            return
        ip  = request.client.host if request.client else "unknown"
        rl  = _rl_transcribe if "transcribe" in key_suffix else (
              _rl_plagiarism if "plag" in key_suffix else _rl_compare)
        if not rl.allow(ip):
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit reached: max {limit} requests per {window}s. Please wait.",
            )
except Exception as _rl_err:
    # Fallback: in-memory (original behaviour)
    logger.warning("File-backed rate limiter unavailable (%s) — using in-memory", _rl_err)
    _rate_store: dict[str, list[float]] = defaultdict(list)
    def _check_rate(request: Request, limit: int, window: int, key_suffix: str = "") -> None:
        if os.getenv("TESTING") == "true":
            return
        ip  = request.client.host if request.client else "unknown"
        key = f"{ip}:{key_suffix}"
        now = time.monotonic()
        _rate_store[key] = [t for t in _rate_store[key] if now - t < window]
        if len(_rate_store[key]) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit reached: max {limit} requests per {window}s. Please wait.",
            )
        _rate_store[key].append(now)

_RATE_LIMIT_TRANSCRIBE  = (5,  60)
_RATE_LIMIT_PLAGIARISM  = (3,  60)
_RATE_LIMIT_COMPARE     = (10, 60)



# ── Slack Webhook ─────────────────────────────────────────────────────────────

async def _notify_slack(candidate_id: str, verdict: str, shift: str,
                        plag_score: Optional[float], submitted_by: str) -> None:
    """
    POST a Slack notification when verdict is SUSPICIOUS or HIGHLY SUSPICIOUS.
    Requires SLACK_WEBHOOK_URL in .env — silently skips if not configured.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return

    color_map = {
        "HIGHLY SUSPICIOUS": "#ef4444",
        "SUSPICIOUS":        "#f59e0b",
    }
    color = color_map.get(verdict.upper(), "#94a3b8")
    plag_str = f"{plag_score:.1f}%" if plag_score is not None else "N/A"

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"⚠️ SachhAI Alert — {verdict}",
                "fields": [
                    {"title": "Candidate",   "value": candidate_id,  "short": True},
                    {"title": "Reviewed By", "value": submitted_by or "Unknown", "short": True},
                    {"title": "Style Shift", "value": shift,          "short": True},
                    {"title": "Plagiarism",  "value": plag_str,       "short": True},
                ],
                "footer": "SachhAI Interview Integrity System",
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(webhook_url, json=payload)
        logger.info("[slack] Alert sent for candidate=%s verdict=%s", candidate_id, verdict)
    except Exception as exc:
        logger.warning("[slack] Failed to send notification: %s", exc)


# ── Verdict logic ─────────────────────────────────────────────────────────────

def compute_final_verdict(style: dict, plag: dict) -> str:
    """
    Combine style-shift signal and plagiarism score into one final verdict.

    Genuine           → style_shift LOW  AND plagiarism < 20 %
    Needs Review      → style_shift MODERATE OR  plagiarism 20-40 %
    Suspicious        → style_shift HIGH OR  plagiarism >= 40 %
    Highly Suspicious → style_shift VERY HIGH OR  (HIGH + plagiarism >= 40 %)
    """
    shift      = style.get("style_shift", "LOW").upper()
    plag_score = plag.get("score")
    p = float(plag_score) if plag_score is not None else 0.0

    very_high_shift = shift == "VERY HIGH"
    high_shift      = shift == "HIGH"
    moderate_shift  = shift == "MODERATE"
    high_plag       = p >= 40.0

    if very_high_shift or (high_shift and high_plag):
        return "HIGHLY SUSPICIOUS"
    if high_shift or high_plag:
        return "SUSPICIOUS"
    if moderate_shift or p >= 20.0:
        return "NEEDS REVIEW"
    return "GENUINE"


# ── POST /voice/record/personal ───────────────────────────────────────────────

@router.post("/record/personal", summary="Record & store personal introduction")
async def record_personal(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (webm, mp3, wav, m4a…)"),
    candidate_id: str = Form(..., description="Unique candidate identifier"),
    user: dict = Depends(_get_current_user),
):
    _check_rate(request, *_RATE_LIMIT_TRANSCRIBE, "transcribe")
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")

    # If candidate already exists, check ownership
    existing = get_candidate(candidate_id)
    username = user.get("sub")
    role = user.get("role")
    if existing:
        cand_by = existing.get("submitted_by")
        if role != "admin" and cand_by != username:
            raise HTTPException(
                status_code=403,
                detail="Access denied: you do not have permission to modify this candidate's data",
            )

    try:
        result = await transcribe_audio(audio_bytes, audio.filename or "personal.webm")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    text    = result["text"]
    signals = result.get("signals") or {}

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Deepgram returned an empty transcription. Speak more clearly or try again.",
        )

    save_response(candidate_id, "personal", text, submitted_by=username)
    logger.info("[voice/record/personal] candidate=%s | %d chars stored", candidate_id, len(text))

    return {
        "candidate_id": candidate_id,
        "type":         "personal",
        "transcription": text,
        "char_count":   len(text),
        "word_count":   len(text.split()),
        "audio_signals": signals,
    }


# ── POST /voice/record/technical ─────────────────────────────────────────────

@router.post("/record/technical", summary="Record & store technical explanation")
async def record_technical(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (webm, mp3, wav, m4a…)"),
    candidate_id: str = Form(..., description="Unique candidate identifier"),
    user: dict = Depends(_get_current_user),
):
    _check_rate(request, *_RATE_LIMIT_TRANSCRIBE, "transcribe")
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")

    existing = get_candidate(candidate_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Candidate '{candidate_id}' not found. "
                "Please record and save a personal response first."
            ),
        )

    username = user.get("sub")
    role = user.get("role")
    cand_by = existing.get("submitted_by")
    if role != "admin" and cand_by != username:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to modify this candidate's data",
        )

    try:
        result = await transcribe_audio(audio_bytes, audio.filename or "technical.webm")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    text    = result["text"]
    signals = result.get("signals") or {}

    if not text:
        raise HTTPException(
            status_code=422,
            detail="Deepgram returned an empty transcription. Speak more clearly or try again.",
        )

    save_response(candidate_id, "technical", text, submitted_by=username)
    logger.info("[voice/record/technical] candidate=%s | %d chars stored", candidate_id, len(text))

    return {
        "candidate_id": candidate_id,
        "type":         "technical",
        "transcription": text,
        "char_count":   len(text),
        "word_count":   len(text.split()),
        "audio_signals": signals,
    }


# ── POST /voice/transcribe-chunk ──────────────────────────────────────────────

@router.post("/transcribe-chunk", summary="Transcribe a short audio clip via Deepgram")
async def transcribe_chunk(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (webm, mp3, wav, m4a…)"),
    type: str = Form(default="personal", description="'personal' or 'technical'"),
    user: dict = Depends(_get_current_user),
):
    """
    Accept a short audio clip and return its Deepgram transcription
    plus rich audio-level signals (confidence, pace, pauses).
    """
    _check_rate(request, *_RATE_LIMIT_TRANSCRIBE, "transcribe")
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file received")

    try:
        result = await transcribe_audio(audio_bytes, audio.filename or f"{type}.webm")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    text    = result["text"]
    signals = result.get("signals") or {}

    logger.info(
        "[voice/transcribe-chunk] type=%s | %d chars transcribed", type, len(text)
    )

    return {
        "type":          type,
        "text":          text,
        "word_count":    len(text.split()) if text else 0,
        "char_count":    len(text),
        "audio_signals": signals,
        "diarized_data": result.get("diarized_data"),
    }


# ── Shared analysis runner ────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    candidate_id: str


class TextCompareRequest(BaseModel):
    """Direct text comparison — no audio / transcription required."""
    candidate_id: str
    personal: str
    technical: str
    personal_signals:  Optional[dict] = None
    technical_signals: Optional[dict] = None


def _merge_audio_signals(style_result: dict, p_signals: Optional[dict],
                         t_signals: Optional[dict]) -> dict:
    """
    Augment style result with audio-level signals and produce an
    audio_authenticity sub-score that blends into the final analysis.
    """
    if not p_signals or not t_signals:
        return style_result

    flags         = style_result.get("flags", [])
    audio_summary = []

    # ── Speech rate jump ─────────────────────────────────────────────────────
    p_wpm = p_signals.get("speech_rate_wpm")
    t_wpm = t_signals.get("speech_rate_wpm")
    if p_wpm and t_wpm:
        wpm_delta = t_wpm - p_wpm
        if wpm_delta > 40:
            flags.append(
                f"Speech rate increased by {wpm_delta:.0f} WPM in technical round "
                "— may indicate reading from a script or screen"
            )
            audio_summary.append("faster_speech")
        elif wpm_delta < -40:
            flags.append(
                f"Speech rate dropped by {abs(wpm_delta):.0f} WPM in technical round "
                "— unusual deceleration detected"
            )
            audio_summary.append("slower_speech")

    # ── Confidence variance (low variance = robotic) ──────────────────────────
    p_cv = p_signals.get("confidence_variance")
    t_cv = t_signals.get("confidence_variance")
    if p_cv is not None and t_cv is not None:
        if t_cv < 0.04 and p_cv > 0.08:
            flags.append(
                "Very low confidence variance in technical round "
                "— unusually consistent delivery, typical of AI-read or memorised content"
            )
            audio_summary.append("robotic_confidence")

    # ── Pause pattern ────────────────────────────────────────────────────────
    p_pauses = p_signals.get("pause_count", 0)
    t_long_pauses = t_signals.get("long_pause_count", 0)
    if t_long_pauses >= 3 and p_pauses < t_long_pauses:
        flags.append(
            f"{t_long_pauses} long pauses detected in technical round "
            "— candidate may be consulting an external source between answers"
        )
        audio_summary.append("long_pauses")

    # ── Audio sub-score (penalty to authenticity) ─────────────────────────────
    penalty = 0
    for factor in audio_summary:
        if factor == "faster_speech":
            penalty += 15
        elif factor == "slower_speech":
            penalty += 12
        elif factor == "robotic_confidence":
            penalty += 15
        elif factor == "long_pauses":
            penalty += 12

    updated_auth = max(0.0, style_result.get("authenticity_score", 80.0) - penalty)

    shift_score = style_result.get("shift_score", 0.0)
    if penalty > 0:
        shift_score = min(100.0, shift_score + penalty * 0.8)

    style_shift = style_result.get("style_shift", "LOW")
    if shift_score >= 60.0:
        style_shift = "VERY HIGH"
    elif shift_score >= 40.0:
        style_shift = "HIGH"
    elif shift_score >= 20.0:
        style_shift = "MODERATE"
    else:
        style_shift = "LOW"

    return {
        **style_result,
        "flags":             flags,
        "shift_score":        round(shift_score, 1),
        "style_shift":        style_shift,
        "authenticity_score": round(updated_auth, 1),
        "audio_signals": {
            "personal":  p_signals,
            "technical": t_signals,
            "audio_flags": audio_summary,
        },
    }


async def _run_full_analysis(
    personal: str,
    technical: str,
    p_signals: Optional[dict] = None,
    t_signals: Optional[dict] = None,
) -> dict:
    """Run style-shift + plagiarism in parallel. Merge audio signals if available."""
    style_result, plag_result = await asyncio.gather(
        asyncio.to_thread(calculate_style_shift, personal, technical),
        plag_check(technical),
    )

    if p_signals or t_signals:
        style_result = _merge_audio_signals(style_result, p_signals, t_signals)

    verdict = compute_final_verdict(style_result, plag_result)

    return {
        **style_result,
        "plagiarism": plag_result,
        "verdict":    verdict,
    }


# ── POST /voice/text-compare ──────────────────────────────────────────────────

@router.post(
    "/text-compare",
    summary="Compare personal vs technical responses (manual text input)",
)
async def text_compare(
    request: Request,
    req: TextCompareRequest,
    user: dict = Depends(_get_current_user),
):
    _check_rate(request, *_RATE_LIMIT_COMPARE, "compare")

    personal  = req.personal.strip()
    technical = req.technical.strip()
    if not personal:
        raise HTTPException(status_code=400, detail="personal text is empty")
    if not technical:
        raise HTTPException(status_code=400, detail="technical text is empty")

    username = user.get("sub")
    role = user.get("role")

    # If candidate already exists, check ownership
    existing = get_candidate(req.candidate_id)
    if existing:
        cand_by = existing.get("submitted_by")
        if role != "admin" and cand_by != username:
            raise HTTPException(
                status_code=403,
                detail="Access denied: you do not have permission to modify this candidate's data",
            )

    submitted_by = username
    save_response(req.candidate_id, "personal",  personal,  submitted_by=submitted_by)
    save_response(req.candidate_id, "technical", technical, submitted_by=submitted_by)

    logger.info(
        "[voice/text-compare] candidate=%s | p=%d | t=%d",
        req.candidate_id, len(personal), len(technical),
    )

    import time as _time
    _t0 = _time.monotonic()

    analysis = await asyncio.to_thread(calculate_style_shift, personal, technical)

    # ── Inline plagiarism (same algorithm as streaming backend) ──────────────
    tp = analysis.get("technical_profile", {})
    pp = analysis.get("personal_profile", {})
    raw_cosine  = analysis.get("cosine_similarity", 0.0)
    voc_jump    = tp.get("vocabulary_level", 0) - pp.get("vocabulary_level", 0)
    fill_drop   = pp.get("filler_ratio", 0) - tp.get("filler_ratio", 0)
    form_jump   = tp.get("formality_score", 0) - pp.get("formality_score", 0)
    plag_risk   = 0.0
    plag_signals: list = []
    if raw_cosine > 0.65:
        plag_risk += 35
        plag_signals.append(f"High textual overlap (cosine={raw_cosine:.2f}) — may be reading notes")
    elif raw_cosine > 0.45:
        plag_risk += 15
        plag_signals.append(f"Moderate textual overlap (cosine={raw_cosine:.2f})")
    if voc_jump > 18:
        plag_risk += 25
        plag_signals.append(f"Vocabulary jumped +{voc_jump:.0f}pts above personal baseline")
    elif voc_jump > 10:
        plag_risk += 12
        plag_signals.append(f"Vocabulary moderately elevated (+{voc_jump:.0f}pts)")
    if fill_drop > 0.03 and pp.get("filler_ratio", 0) > 0.01:
        plag_risk += 20
        plag_signals.append("Filler words disappeared — AI-generated text has no natural disfluencies")
    analysis["inline_plagiarism_risk"]    = round(min(100.0, plag_risk), 1)
    analysis["inline_plagiarism_signals"] = plag_signals
    analysis["cosine_similarity"]         = raw_cosine
    if req.personal_signals or req.technical_signals:
        analysis = _merge_audio_signals(analysis, req.personal_signals, req.technical_signals)

    # Compute verdict without plagiarism to ensure it's present
    analysis["verdict"] = compute_final_verdict(analysis, {})

    # Cache the analysis
    save_analysis(req.candidate_id, analysis)

    # Enforce 2–5 s response time so analysis feels substantial
    _elapsed = _time.monotonic() - _t0
    if _elapsed < 2.0:
        await asyncio.sleep(2.0 - _elapsed)

    # Notify Slack if suspicious
    verdict = analysis.get("verdict", "")
    if verdict in ("SUSPICIOUS", "HIGHLY SUSPICIOUS"):
        asyncio.create_task(
            _notify_slack(
                req.candidate_id, verdict,
                analysis.get("style_shift", ""),
                None,
                submitted_by or "Unknown",
            )
        )

    return {
        "candidate_id":      req.candidate_id,
        "personal_preview":  personal[:300],
        "technical_preview": technical[:300],
        "analysis":          analysis,
    }


# ── POST /voice/compare ───────────────────────────────────────────────────────

@router.post("/compare", summary="Compare personal vs technical responses (from audio)")
async def compare(
    request: Request,
    req: CompareRequest,
    user: dict = Depends(_get_current_user),
):
    _check_rate(request, *_RATE_LIMIT_COMPARE, "compare")

    candidate = get_candidate(req.candidate_id)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Candidate '{req.candidate_id}' not found",
        )

    # Tenant ownership check
    username = user.get("sub")
    role = user.get("role")
    cand_by = candidate.get("submitted_by")
    if role != "admin" and cand_by != username:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to view or analyze this candidate's data",
        )

    personal  = candidate.get("personal", "")
    technical = candidate.get("technical", "")

    if not personal:
        raise HTTPException(status_code=400, detail="Personal response not recorded yet")
    if not technical:
        raise HTTPException(status_code=400, detail="Technical response not recorded yet")

    logger.info("[voice/compare] Running analysis for candidate=%s", req.candidate_id)
    analysis = await _run_full_analysis(personal, technical)

    save_analysis(req.candidate_id, analysis)

    verdict = analysis.get("verdict", "")
    if verdict in ("SUSPICIOUS", "HIGHLY SUSPICIOUS"):
        asyncio.create_task(
            _notify_slack(req.candidate_id, verdict, analysis.get("style_shift", ""), None, username)
        )

    return {
        "candidate_id":      req.candidate_id,
        "personal_preview":  personal[:300]  + ("…" if len(personal)  > 300 else ""),
        "technical_preview": technical[:300] + ("…" if len(technical) > 300 else ""),
        "analysis":          analysis,
    }


# ── POST /voice/plagiarism ────────────────────────────────────────────────────

class PlagCheckRequest(BaseModel):
    personal:     str = ""
    technical:    str
    candidate_id: str = ""


@router.post("/plagiarism", summary="Run plagiarism & AI detection on interview responses")
async def run_plagiarism(
    request: Request,
    req: PlagCheckRequest,
    user: dict = Depends(_get_current_user),
):
    _check_rate(request, *_RATE_LIMIT_PLAGIARISM, "plagiarism")

    username = user.get("sub")
    role = user.get("role")

    if req.candidate_id:
        existing = get_candidate(req.candidate_id)
        if existing:
            cand_by = existing.get("submitted_by")
            if role != "admin" and cand_by != username:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: you do not have permission to access or modify this candidate's data",
                )

    p_text = req.personal.strip()
    t_text = req.technical.strip()

    if not t_text:
        raise HTTPException(status_code=400, detail="technical text is empty")

    logger.info(
        "[voice/plagiarism] personal=%d chars | technical=%d chars",
        len(p_text), len(t_text),
    )

    tasks = {
        "t_plag": plag_check(t_text),
        "t_ai":   ai_check(t_text),
    }

    if p_text:
        tasks["p_plag"] = plag_check(p_text)
        tasks["p_ai"]   = ai_check(p_text)

    keys    = list(tasks.keys())
    results = await asyncio.gather(*(tasks[k] for k in keys))
    res_dict = dict(zip(keys, results))

    t_result = {
        "plagiarism":   res_dict["t_plag"],
        "ai_detection": res_dict["t_ai"],
    }

    p_result = None
    if p_text:
        p_result = {
            "plagiarism":   res_dict["p_plag"],
            "ai_detection": res_dict["p_ai"],
        }

    # Update cached analysis with plagiarism data if we have a candidate_id
    if req.candidate_id:
        try:
            candidate = get_candidate(req.candidate_id) or {}
            existing_analysis = candidate.get("analysis") or {}
            existing_analysis["plagiarism_data"] = {
                "personal":  p_result,
                "technical": t_result,
            }
            save_analysis(req.candidate_id, existing_analysis)
        except Exception:
            pass

    return {"personal": p_result, "technical": t_result}


# ── GET /voice/candidates ─────────────────────────────────────────────────────

@router.get("/candidates", summary="List all stored candidate IDs")
def get_candidates(
    user: dict = Depends(_get_current_user),
):
    username = user.get("sub")
    role = user.get("role")
    submitted_by = None if role == "admin" else username
    candidates = list_candidates(
        submitted_by=submitted_by,
        role=role,
    )
    return {"candidates": candidates}


# ── GET /voice/candidate/{candidate_id} ───────────────────────────────────────

@router.get("/candidate/{candidate_id}", summary="Get stored data for a candidate")
def get_candidate_data(
    candidate_id: str,
    user: dict = Depends(_get_current_user),
):
    data = get_candidate(candidate_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found")
    username = user.get("sub")
    role = user.get("role")
    cand_by = data.get("submitted_by")
    if role != "admin" and cand_by != username:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to view this candidate's data",
        )
    return {"candidate_id": candidate_id, "data": data}


# ── DELETE /voice/candidate/{candidate_id} ────────────────────────────────────

@router.delete("/candidate/{candidate_id}", summary="Delete a candidate's data")
def remove_candidate(
    candidate_id: str,
    user: dict = Depends(_get_current_user),
):
    username = user.get("sub")
    role = user.get("role")
    if username == "hr1":
        raise HTTPException(
            status_code=403,
            detail="Access denied: Demo account is read-only and cannot delete records",
        )
    data = get_candidate(candidate_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found")
    cand_by = data.get("submitted_by")
    if role != "admin" and cand_by != username:
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to delete this candidate",
        )
    removed = delete_candidate(candidate_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found")
    return {"deleted": True, "candidate_id": candidate_id}


# ── POST /voice/check-credibility ────────────────────────────────────────────

class CredibilityCheckItem(BaseModel):
    """A single question + candidate response pair to evaluate."""
    question:          str
    candidate_response: str
    expected_answer:   Optional[str] = None


class CredibilityBatchRequest(BaseModel):
    """Batch credibility check for multiple Q&A pairs in one request."""
    candidate_id: str = ""
    items:        list[CredibilityCheckItem]


@router.post(
    "/check-credibility",
    summary="Evaluate whether candidate responses correctly answer interview questions",
)
async def check_credibility(
    request: Request,
    req: CredibilityBatchRequest,
    user: dict = Depends(_get_current_user),
):
    """
    For each Q&A pair in *items*, run LLM-based answer credibility scoring.
    Returns a per-item verdict plus an overall credibility summary.

    Verdict levels
    --------------
    CORRECT       — Answer clearly and accurately addresses the question.
    PARTIALLY     — Answer partially correct; key gaps present.
    INCORRECT     — Answer is wrong, off-topic, or non-committal.
    INSUFFICIENT  — Response too short / vague to evaluate.
    """
    _check_rate(request, *_RATE_LIMIT_COMPARE, "compare")

    username = user.get("sub")
    role = user.get("role")
    if req.candidate_id:
        existing = get_candidate(req.candidate_id)
        if existing:
            cand_by = existing.get("submitted_by")
            if role != "admin" and cand_by != username:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: you do not have permission to access this candidate's data",
                )

    if not req.items:
        raise HTTPException(status_code=400, detail="No items provided")
    if len(req.items) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 items per request")

    results = []
    for item in req.items:
        if not item.question.strip() or not item.candidate_response.strip():
            results.append({
                "question":  item.question,
                "verdict":   "INSUFFICIENT",
                "score":     0,
                "confidence": 0.0,
                "explanation": "Question or response was empty.",
                "key_points_hit":    [],
                "key_points_missed": [],
                "suggestions":       "",
            })
            continue

        result = await asyncio.to_thread(
            check_answer_credibility,
            item.question,
            item.candidate_response,
            item.expected_answer,
        )
        results.append({
            "question": item.question,
            **result,
        })

    # ── Aggregate summary ─────────────────────────────────────────────────────
    scored = [r for r in results if r["verdict"] != "INSUFFICIENT"]
    if scored:
        avg_score   = round(sum(r["score"] for r in scored) / len(scored))
        correct_n   = sum(1 for r in scored if r["verdict"] == "CORRECT")
        partial_n   = sum(1 for r in scored if r["verdict"] == "PARTIALLY")
        incorrect_n = sum(1 for r in scored if r["verdict"] == "INCORRECT")
        if avg_score >= 70:
            overall = "STRONG"
        elif avg_score >= 45:
            overall = "MODERATE"
        else:
            overall = "WEAK"
    else:
        avg_score, correct_n, partial_n, incorrect_n = 0, 0, 0, 0
        overall = "INSUFFICIENT"

    logger.info(
        "[voice/check-credibility] candidate=%s | items=%d | avg_score=%d | overall=%s",
        req.candidate_id or "N/A", len(req.items), avg_score, overall,
    )

    credibility_data = {
        "results":      results,
        "summary": {
            "overall":    overall,
            "avg_score":  avg_score,
            "correct":    correct_n,
            "partial":    partial_n,
            "incorrect":  incorrect_n,
            "total":      len(req.items),
        },
    }

    # Auto-save credibility results if candidate_id is provided
    if req.candidate_id:
        try:
            cand = get_candidate(req.candidate_id) or {}
            existing_analysis = cand.get("analysis") or {}
            existing_analysis["credibility_results"] = credibility_data
            save_analysis(req.candidate_id, existing_analysis)
            logger.info("[voice/check-credibility] Auto-saved credibility results for candidate=%s", req.candidate_id)
        except Exception as exc:
            logger.error("[voice/check-credibility] Failed to auto-save credibility results: %s", exc)

    return {
        "candidate_id": req.candidate_id,
        "results":      results,
        "summary":      credibility_data["summary"],
    }


class SaveCredibilityRequest(BaseModel):
    """Payload to save or override candidate credibility assessment."""
    candidate_id: str
    results:      list[dict]


@router.post(
    "/save-credibility",
    summary="Save or override candidate credibility assessment",
)
async def save_credibility(
    req: SaveCredibilityRequest,
    user: dict = Depends(_get_current_user),
):
    if not req.candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id required")

    username = user.get("sub")
    role = user.get("role")

    cand = get_candidate(req.candidate_id)
    if cand:
        cand_by = cand.get("submitted_by")
        if role != "admin" and cand_by != username:
            raise HTTPException(
                status_code=403,
                detail="Access denied: you do not have permission to modify this candidate's data",
            )

    # Recalculate summary based on overridden results
    scored = [r for r in req.results if r.get("verdict") != "INSUFFICIENT"]
    if scored:
        avg_score   = round(sum(int(r.get("score", 0)) for r in scored) / len(scored))
        correct_n   = sum(1 for r in scored if r.get("verdict") == "CORRECT")
        partial_n   = sum(1 for r in scored if r.get("verdict") == "PARTIALLY")
        incorrect_n = sum(1 for r in scored if r.get("verdict") == "INCORRECT")
        if avg_score >= 70:
            overall = "STRONG"
        elif avg_score >= 45:
            overall = "MODERATE"
        else:
            overall = "WEAK"
    else:
        avg_score, correct_n, partial_n, incorrect_n = 0, 0, 0, 0
        overall = "INSUFFICIENT"

    credibility_data = {
        "results":      req.results,
        "summary": {
            "overall":    overall,
            "avg_score":  avg_score,
            "correct":    correct_n,
            "partial":    partial_n,
            "incorrect":  incorrect_n,
            "total":      len(req.results),
        },
    }

    try:
        cand = get_candidate(req.candidate_id) or {}
        existing_analysis = cand.get("analysis") or {}
        existing_analysis["credibility_results"] = credibility_data
        save_analysis(req.candidate_id, existing_analysis)
        logger.info("[voice/save-credibility] Saved overridden credibility results for candidate=%s", req.candidate_id)
    except Exception as exc:
        logger.error("[voice/save-credibility] Failed to save credibility results: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save credibility results: {exc}")

    return {
        "success":      True,
        "candidate_id": req.candidate_id,
        "summary":      credibility_data["summary"],
    }

