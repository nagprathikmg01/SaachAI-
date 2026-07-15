"""
personal_routes.py — Endpoints for Meet extension personal-phase analysis.

Routes:
  POST /voice/analyze-personal   → build linguistic baseline from personal text
  POST /voice/suggest-questions  → generate follow-up questions from live context
  POST /voice/plagiarism-check   → intra-session plagiarism / script-reading detector
  POST /voice/save-session       → persist completed interview session
  GET  /voice/sessions           → list all stored sessions (for dashboard)
  GET  /voice/sessions/{id}      → get one session
"""

import re
import math
import logging
from pydantic import BaseModel
from typing import Optional

from fastapi import APIRouter, Request, Header, Depends, HTTPException

try:
    from auth_routes import _get_current_user
except ImportError:
    from backend.auth_routes import _get_current_user

import asyncio

try:
    from .style_comparator import _build_profile, calculate_style_shift, _cosine_similarity
    from .session_store import save_session, list_sessions, get_session
    from .baseline_quality import assess_baseline_quality
    from .storage import save_response, save_analysis
    from .plagiarism_client import check_text as plag_check
    from .followup_generator import _TECH_TOPICS
except ImportError:
    from backend.voice_module.style_comparator import _build_profile, calculate_style_shift, _cosine_similarity
    from backend.voice_module.session_store import save_session, list_sessions, get_session
    from backend.voice_module.baseline_quality import assess_baseline_quality
    from backend.voice_module.storage import save_response, save_analysis
    from backend.voice_module.plagiarism_client import check_text as plag_check
    from backend.voice_module.followup_generator import _TECH_TOPICS

logger = logging.getLogger(__name__)
personal_router = APIRouter(tags=["PersonalAnalysis"])


# ── Request / Response Models ─────────────────────────────────────────────────

class PersonalTextReq(BaseModel):
    text: str
    role: str = ""

class SuggestQuestionsReq(BaseModel):
    transcript: str          # latest ~200 words from candidate
    flags: list[str] = []
    hedging: float = 0.0
    passive_voice: float = 0.0
    formality_drop: float = 0.0
    vocabulary_drop: float = 0.0
    role: str = ""

class PlagiarismReq(BaseModel):
    personal_text: str
    live_window: str         # current analysis window text


# ── /voice/analyze-personal ───────────────────────────────────────────────────

@personal_router.post("/analyze-personal")
async def analyze_personal(
    req: PersonalTextReq,
    user: dict = Depends(_get_current_user),
):
    """
    Build a linguistic baseline profile from the candidate's personal text
    (cover letter, self-introduction, resume summary, etc.).

    Returns the full profile dict so the Meet overlay can:
      1. Display baseline metrics
      2. Pass it as the comparison anchor during the live technical phase
    """
    if not req.text or len(req.text.split()) < 15:
        return {"status": "error", "message": "Please provide at least 15 words of personal text."}

    try:
        profile = _build_profile(req.text)

        # Readability label — now based on grammar score (0-100)
        gs = profile["grammar_score"]
        if gs >= 80:
            readability = "Fluent / Well-formed"
        elif gs >= 60:
            readability = "Moderate fluency"
        elif gs >= 40:
            readability = "Informal / Fragmented"
        else:
            readability = "Very informal / Highly fragmented"

        # Vocabulary tier
        vl = profile["vocabulary_level"]
        if vl < 35:
            vocab_tier = "Casual"
        elif vl < 55:
            vocab_tier = "Moderate"
        elif vl < 70:
            vocab_tier = "Advanced"
        else:
            vocab_tier = "Expert"

        # Natural vs formal baseline
        formality = profile["formality_score"]
        formality_label = (
            "Very formal" if formality > 70 else
            "Formal" if formality > 55 else
            "Moderate" if formality > 40 else
            "Casual / Informal"
        )

        filler = profile["filler_ratio"]
        filler_label = (
            "High (natural speech)" if filler > 0.04 else
            "Some fillers" if filler > 0.01 else
            "Very few / none"
        )

        summary_parts = [
            f"Formality: {formality_label} ({formality:.0f}/100)",
            f"Vocabulary: {vocab_tier} ({vl:.0f}/100)",
            f"Grammar fluency: {readability} ({profile['grammar_score']:.0f}/100)",
            f"Filler words: {filler_label}",
            f"Lexical diversity: {profile['lexical_diversity']:.2f}",
        ]

        # ── Baseline quality assessment ────────────────────────────────────────
        bq = assess_baseline_quality(profile, req.text)

        return {
            "status":            "ok",
            # Legacy fields (backward compat)
            "profile":           profile,
            "readability":       readability,
            "vocab_tier":        vocab_tier,
            "formality_label":   formality_label,
            "filler_label":      filler_label,
            "summary_bullets":   summary_parts,
            "word_count":        profile["word_count"],
            # ── Baseline Quality (v2) ──────────────────────────────────────────
            "baseline_quality":     bq["quality"],          # STRONG / ADEQUATE / WEAK
            "baseline_quality_info": bq["quality_info"],    # {label, color, icon}
            "baseline_quality_score": bq["quality_score"],  # 0-100
            "baseline_confidence":  bq["confidence_level"], # high / medium / low
            "baseline_confidence_info": bq["confidence_info"],
            # Readiness
            "readiness":         bq["readiness"],           # "Ready" / "Ready with caution" / "Baseline weak"
            "readiness_note":    bq["readiness_note"],
            # Sample adequacy
            "adequacy_label":    bq["adequacy_label"],      # Excellent / Adequate / Short / Insufficient
            "adequacy_note":     bq["adequacy_note"],
            # Signals
            "filler_note":       bq["filler_note"],
            "formality_context": bq["formality_context"],
            "variety_note":      bq["variety_note"],
            # Explainability
            "strengths":         bq["strengths"],
            "issues":            bq["issues"],
            "recommendations":   bq["recommendations"],
            "comparison_context": bq["comparison_context"],
            "recruiter_summary": bq["recruiter_summary"],
            # Compliance
            "disclaimer":        bq["disclaimer"],
            # Multi-baseline (future-ready)
            "baseline_type":     bq["baseline_type"],       # "casual_intro"
            "baseline_index":    bq["baseline_index"],      # 1 (first baseline)
            "baseline_label":    bq["baseline_label"],      # "Personal Introduction"
            "supports_structured": bq["supports_structured"],
        }

    except Exception as exc:
        logger.error("[analyze-personal] Error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ── /voice/suggest-questions ──────────────────────────────────────────────────

# Tech domain keyword → follow-up question templates (imported from followup_generator)

def _suggest_questions(
    transcript: str,
    flags: list,
    hedging: float,
    passive_voice: float,
    formality_drop: float,
    vocabulary_drop: float,
    role: str,
) -> list[str]:
    questions = []
    lower = transcript.lower()

    # 1. Vagueness/hedging signals → ask for specifics
    if hedging > 0.12:
        questions.append("Can you give a concrete, specific example of that — with the actual outcome and metrics?")
    if passive_voice > 0.30:
        questions.append("What was your personal, direct contribution to that? Can you describe exactly what you built or decided?")

    # 2. Style shift → probe authenticity
    if formality_drop > 15 or any("sophistication" in f or "formality" in f for f in flags):
        questions.append("Can you explain that concept in your own words, without using technical jargon?")
    if vocabulary_drop > 12 or any("vocabulary" in f for f in flags):
        questions.append("That was a detailed answer — can you walk me through how you would implement that from scratch, step by step?")

    # 3. Burstiness / uniform pacing → they're reading
    if any("rhythm" in f or "uniform" in f for f in flags):
        questions.append("Let's take a different angle — what would you do differently if you were starting this project today?")

    # 4. Domain keyword match → specific follow-ups
    matched = set()
    for pattern, question in _TECH_TOPICS.items():
        if re.search(pattern, lower, re.I) and question not in matched:
            matched.add(question)
            if len(questions) + len(matched) >= 6:
                break

    questions.extend(list(matched)[:3])

    # 5. Generic probes if we don't have enough
    generic = [
        "What was the hardest problem you encountered in that work, and how did you debug it?",
        "If a junior engineer asked you to explain that concept, how would you describe it?",
        "What metrics did you use to measure success, and what was the final result?",
        "Can you compare two different approaches you considered and explain your choice?",
    ]
    for g in generic:
        if len(questions) >= 5:
            break
        if g not in questions:
            questions.append(g)

    return questions[:5]


@personal_router.post("/suggest-questions")
async def suggest_questions(
    req: SuggestQuestionsReq,
    user: dict = Depends(_get_current_user),
):
    qs = _suggest_questions(
        transcript=req.transcript,
        flags=req.flags,
        hedging=req.hedging,
        passive_voice=req.passive_voice,
        formality_drop=req.formality_drop,
        vocabulary_drop=req.vocabulary_drop,
        role=req.role,
    )
    return {"status": "ok", "questions": qs}


# ── /voice/plagiarism-check ───────────────────────────────────────────────────

def _script_reading_score(personal: str, live: str) -> dict:
    """
    Intra-session plagiarism / script-reading detector.

    Signals:
      1. Cosine similarity between personal text and live window
         (high = candidate is re-using their own text = reading notes)
      2. Sudden vocabulary spike compared to personal baseline
      3. Low burstiness in live window (machine-uniform pacing)
      4. Very long sentences in live vs personal (pre-written)

    Returns a 0-100 plagiarism_risk score + verdict + signals.
    """
    if not personal or not live:
        return {"plagiarism_risk": 0, "verdict": "Insufficient data", "signals": []}

    p = _build_profile(personal)
    l = _build_profile(live)
    cosine = _cosine_similarity(personal, live)

    risk = 0.0
    signals = []

    # High cosine → reading from their own written material
    if cosine > 0.65:
        risk += 35
        signals.append(f"High textual overlap with personal text (cosine={cosine:.2f}) — candidate may be reading from notes")
    elif cosine > 0.45:
        risk += 15
        signals.append(f"Moderate overlap with personal text (cosine={cosine:.2f})")

    # Vocabulary spike
    voc_jump = l["vocabulary_level"] - p["vocabulary_level"]
    if voc_jump > 18:
        risk += 25
        signals.append(f"Vocabulary complexity jumped +{voc_jump:.0f} pts from personal baseline — suggests pre-written content")
    elif voc_jump > 10:
        risk += 12

    # Transition density spike (AI text loves formal connectors)
    td_jump = l["transition_density"] - p["transition_density"]
    if td_jump > 0.02:
        risk += 20
        signals.append(f"Formal connectors spiked (+{td_jump*1000:.1f}‰) — AI text is dense with furthermore/additionally/however")

    # Filler word drop (biggest AI signal)
    fill_drop = p["filler_ratio"] - l["filler_ratio"]
    if fill_drop > 0.03 and p["filler_ratio"] > 0.01:
        risk += 25
        signals.append(f"Filler words dropped {fill_drop*100:.1f}% — AI-generated text has no natural disfluencies")

    # Grammar jumped (AI text is grammatically perfect)
    gram_jump = l["grammar_score"] - p["grammar_score"]
    if gram_jump > 15:
        risk += 10
        signals.append(f"Grammar score jumped +{gram_jump:.0f}pts — sudden structural perfection is an AI indicator")

    risk = round(min(100.0, risk), 1)

    if risk >= 60:
        verdict = "HIGH RISK — Likely reading from script/notes"
    elif risk >= 35:
        verdict = "MODERATE RISK — Some scripted elements detected"
    elif risk >= 15:
        verdict = "LOW RISK — Minor indicators present"
    else:
        verdict = "CLEAN — No scripted content detected"

    return {
        "plagiarism_risk": risk,
        "verdict": verdict,
        "signals": signals,
        "cosine_overlap": round(cosine, 3),
    }


@personal_router.post("/plagiarism-check")
async def plagiarism_check(
    req: PlagiarismReq,
    user: dict = Depends(_get_current_user),
):
    try:
        result = _script_reading_score(req.personal_text, req.live_window)
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("[plagiarism-check] Error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ── /voice/save-session ───────────────────────────────────────────────────────────

class SaveSessionReq(BaseModel):
    candidate_name: str
    interviewer_name: str
    role: str = ""
    duration_s: int = 0
    final_score: float = 0.0
    verdict: str = "NEEDS REVIEW"
    strong_signals: int = 0
    flags: list = []
    questions: list = []
    plagiarism_risk: float = 0.0
    summary: str = ""
    personal_text: str = ""
    technical_text: str = ""    # full accumulated transcript from extension
    personal_profile: dict = {}
    technical_profile: dict = {}

@personal_router.post("/save-session")
async def api_save_session(
    req: SaveSessionReq,
    request: Request,
    user: dict = Depends(_get_current_user),
):
    username = user.get("sub")
    verified_by = (username or "Unknown")
    try:
        session_id = save_session(
            candidate_name=req.candidate_name,
            interviewer_name=req.interviewer_name,
            role=req.role,
            duration_s=req.duration_s,
            final_score=req.final_score,
            verdict=req.verdict,
            strong_signals=req.strong_signals,
            flags=req.flags,
            questions=req.questions,
            plagiarism_risk=req.plagiarism_risk,
            summary=req.summary,
            personal_text=req.personal_text,
        )

        # Also save to Supabase so it appears in the existing dashboard.html
        try:
            cand_id = f"{req.candidate_name.replace(' ', '_')}_{session_id}"
            save_response(cand_id, "personal", req.personal_text, submitted_by=verified_by)
            technical_stored = req.technical_text or "(Recorded via Live Chrome Extension)"
            save_response(cand_id, "technical", technical_stored, submitted_by=verified_by)

            # ── Full deep analysis if we have enough transcript ──────────────
            analysis_data: dict = {
                "authenticity_score": req.final_score,
                "verdict": req.verdict,
                "summary": req.summary,
                "flags": req.flags,
                "followup_questions": req.questions,
                "plagiarism_risk": req.plagiarism_risk,
                "style_shift": f"Score: {req.final_score}",
                "personal_profile": req.personal_profile,
                "technical_profile": req.technical_profile,
            }

            tech_words = len(req.technical_text.split()) if req.technical_text else 0
            pers_words = len(req.personal_text.split()) if req.personal_text else 0

            if tech_words >= 30 and pers_words >= 15:
                # Run full style-shift + plagiarism deep analysis post-session
                style_result, plag_result = await asyncio.gather(
                    asyncio.to_thread(calculate_style_shift, req.personal_text, req.technical_text),
                    plag_check(req.technical_text),
                )
                # ── Rewrite the summary to match the LIVE session average score ──
                # The deep-analysis summary bakes in its own recalculated score (e.g. 8.0).
                # We replace the score reference so it always shows what the interviewer saw live.
                raw_summary = style_result.get("summary", req.summary)
                import re as _re
                live_summary = _re.sub(
                    r"\((?:Consistency )?Score: [\d.]+/100(?:,.*?)?\)",
                    f"(Score: {req.final_score}/100)",
                    raw_summary,
                )
                analysis_data.update({
                    # Core scores — always pinned to live extension average
                    "authenticity_score":  req.final_score,
                    "lsdi":               style_result.get("lsdi_score", style_result.get("shift_score", 0)),
                    "shift_score":        style_result.get("shift_score", 0),
                    "style_shift":        style_result.get("style_shift", "UNKNOWN"),
                    "tier_label":         style_result.get("tier_label", ""),
                    # Verdict — always pinned to live average verdict
                    "verdict":            req.verdict,
                    "verdict_info":       style_result.get("verdict_info", {}),
                    "confidence":         style_result.get("confidence", {}),
                    "confidence_level":   style_result.get("confidence_level", "Low"),
                    "confidence_interval": style_result.get("confidence_interval", {}),
                    # Flags, summary (score text replaced), evidence
                    "flags":              style_result.get("flags", req.flags),
                    "summary":            live_summary,
                    "evidence":           style_result.get("evidence", []),
                    "active_signals":     style_result.get("active_signals", []),
                    "primary_signal":     style_result.get("primary_signal"),
                    "supporting_signals": style_result.get("supporting_signals", []),
                    # Follow-ups + interpretation
                    "followup_questions": style_result.get("followup_questions", req.questions),
                    "safe_interpretation": style_result.get("safe_interpretation", ""),
                    "short_guardrail":    style_result.get("short_guardrail", ""),
                    "disclaimer":         style_result.get("disclaimer", ""),
                    # Profiles + breakdown (for metric panels and charts)
                    "personal_profile":   style_result.get("personal_profile", req.personal_profile),
                    "technical_profile":  style_result.get("technical_profile", req.technical_profile),
                    "shift_breakdown":    style_result.get("shift_breakdown", {}),
                    # Temporal drift (for drift window chart)
                    "temporal_drift":     style_result.get("temporal_drift", {}),
                    # Plagiarism
                    "plagiarism":         plag_result,
                    "plagiarism_risk":    plag_result.get("score", req.plagiarism_risk),
                    "plagiarism_signals": plag_result.get("signals", []),
                    # Meta
                    "strong_signal_count": style_result.get("strong_signal_count", 0),
                    "cosine_similarity":  style_result.get("cosine_similarity", None),
                    "deep_analysis":      True,
                    "_analysis_mode":     "ai_detection_v3",
                })
                logger.info(
                    "[save-session] Deep analysis complete for %s: verdict=%s score=%.1f",
                    cand_id, analysis_data["verdict"], analysis_data["authenticity_score"]
                )

            save_analysis(cand_id, analysis_data)
        except Exception as db_exc:
            logger.warning("[save-session] Supabase sync failed: %s", db_exc)

        return {"status": "ok", "session_id": session_id}
    except Exception as exc:
        logger.error("[save-session] Error: %s", exc)
        return {"status": "error", "message": str(exc)}


# ── /voice/sessions ─────────────────────────────────────────────────────────────────

@personal_router.get("/sessions")
async def api_list_sessions(user: dict = Depends(_get_current_user)):
    try:
        sessions = list_sessions(limit=100)
        username = user.get("sub")
        role = user.get("role")
        if role != "admin":
            # HR users can see their own sessions plus default demo sessions
            sessions = [s for s in sessions if s.get("interviewer_name") == username or s.get("interviewer_name") == "HR Team"]
        return {"status": "ok", "sessions": sessions, "count": len(sessions)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

@personal_router.get("/sessions/{session_id}")
async def api_get_session(session_id: str, user: dict = Depends(_get_current_user)):
    session = get_session(session_id)
    if not session:
        return {"status": "error", "message": "Session not found"}
    username = user.get("sub")
    role = user.get("role")
    if role != "admin" and session.get("interviewer_name") != username and session.get("interviewer_name") != "HR Team":
        raise HTTPException(
            status_code=403,
            detail="Access denied: you do not have permission to view this session's data",
        )
    return {"status": "ok", "session": session}
