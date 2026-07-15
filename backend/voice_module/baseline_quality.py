"""
baseline_quality.py — Baseline quality assessment engine.

Evaluates how reliable a personal baseline is for comparison.
Used in the "Baseline Locked" screen to tell recruiters how much
to trust subsequent analysis results.

Decision logic:
  - Sample adequacy: based on word count
  - Filler presence: confirms natural speech was captured
  - Sentence variety: checks burstiness > 0 (not a single blob)
  - Formality level: natural casual speech is best baseline
  - Overall quality: composite score -> STRONG / ADEQUATE / WEAK

Returns recruiter-friendly copy and recommendations.
"""

from typing import Optional


# ── Readiness status thresholds ────────────────────────────────────────────────

QUALITY_LEVELS = {
    "STRONG":   {"label": "Baseline Strong",        "color": "#10b981", "icon": "check"},
    "ADEQUATE": {"label": "Ready with Caution",     "color": "#f59e0b", "icon": "caution"},
    "WEAK":     {"label": "Baseline Weak",          "color": "#ef4444", "icon": "warning"},
}

CONFIDENCE_LABELS = {
    "high":      {"label": "High",   "color": "#10b981"},
    "medium":    {"label": "Medium", "color": "#f59e0b"},
    "low":       {"label": "Low",    "color": "#f97316"},
    "very_low":  {"label": "Very Low","color": "#ef4444"},
}

DISCLAIMER = (
    "This tool supports interviewer judgment. "
    "Results should not be used as the sole basis for any hiring decision."
)


def assess_baseline_quality(profile: dict, text: str) -> dict:
    """
    Evaluates a personal intro profile for baseline reliability.

    Args:
        profile: output of _build_profile()
        text:    original personal intro text

    Returns a rich baseline quality assessment dict.
    """
    word_count     = profile.get("word_count", 0)
    filler_ratio   = profile.get("filler_ratio", 0.0)
    formality      = profile.get("formality_score", 50.0)
    grammar        = profile.get("grammar_score", 50.0)
    lexical_div    = profile.get("lexical_diversity", 0.5)
    sentence_count = profile.get("sentence_count", 1)
    burstiness     = profile.get("sentence_burstiness", 0.0)
    avg_sent_len   = profile.get("avg_sentence_len", 10.0)

    issues:          list[str] = []
    recommendations: list[str] = []
    strengths:       list[str] = []
    score = 0   # 0–100 composite quality score

    # ── 1. Sample adequacy (word count) ───────────────────────────────────────
    if word_count >= 80:
        adequacy_label = "Excellent"
        adequacy_note  = f"{word_count} words — sufficient for reliable analysis"
        score += 35
        strengths.append("Good sample length")
    elif word_count >= 50:
        adequacy_label = "Adequate"
        adequacy_note  = f"{word_count} words — usable but more would improve accuracy"
        score += 22
        recommendations.append(
            "Ask the candidate to introduce themselves more fully "
            "(50-80 words is the sweet spot for a reliable baseline)."
        )
    elif word_count >= 30:
        adequacy_label = "Short"
        adequacy_note  = f"{word_count} words — borderline; results may vary"
        score += 12
        issues.append("Sample is short — analysis confidence will be limited")
        recommendations.append(
            "Collect a longer personal intro. Ask: 'Tell me about yourself, "
            "your background, and what you enjoy doing outside work.'"
        )
    else:
        adequacy_label = "Insufficient"
        adequacy_note  = f"{word_count} words — too short for reliable comparison"
        score += 0
        issues.append("Sample too short — baseline may produce false positives")
        recommendations.append(
            "Sample is very short. Encourage the candidate to speak freely "
            "for 30-60 seconds before starting the technical round."
        )

    # ── 2. Natural speech markers (filler ratio) ───────────────────────────────
    if filler_ratio > 0.03:
        score += 25
        strengths.append("Natural speech rhythm captured (fillers present)")
        filler_note = "Natural speech captured"
    elif filler_ratio > 0.01:
        score += 15
        filler_note = "Some natural speech markers"
        strengths.append("Some spoken language signals present")
    else:
        score += 0
        filler_note = "Very few speech markers — may be scripted or typed"
        issues.append("No filler words detected — baseline may be overly formal or typed")
        recommendations.append(
            "If text was typed rather than spoken, consider re-recording "
            "a spoken personal intro for a more accurate baseline."
        )

    # ── 3. Formality context ───────────────────────────────────────────────────
    if formality < 55:
        score += 20
        formality_context = "Casual / Conversational — ideal as baseline"
        strengths.append("Conversational tone — good contrast for technical detection")
    elif formality < 70:
        score += 12
        formality_context = "Moderate formality — adequate baseline"
        recommendations.append(
            "Baseline is slightly formal. Ask a casual personal question to get "
            "more natural speech before starting the technical round."
        )
    else:
        score += 4
        formality_context = "High formality — may reduce detection sensitivity"
        issues.append(
            "Baseline is too formal — technical answers may not trigger expected shift"
        )
        recommendations.append(
            "Try collecting a more casual baseline. "
            "Ask about hobbies, a recent project they enjoyed, or their daily routine."
        )

    # ── 4. Sentence variety ────────────────────────────────────────────────────
    if sentence_count >= 4 and burstiness > 0.2:
        score += 20
        variety_note = "Good sentence variety"
        strengths.append("Natural variation in sentence length")
    elif sentence_count >= 2:
        score += 10
        variety_note = "Moderate variety"
    else:
        score += 0
        variety_note = "Low variety — single block of text"
        issues.append("Text appears as one block — harder to analyse rhythm patterns")

    # ── Composite quality level ────────────────────────────────────────────────
    if score >= 75:
        quality = "STRONG"
        readiness = "Ready"
        readiness_note = (
            "The baseline is strong. Analysis results during the technical round "
            "will be reliable and can be shared with confidence."
        )
        confidence_level = "high"
    elif score >= 45:
        quality = "ADEQUATE"
        readiness = "Ready with caution"
        readiness_note = (
            "The baseline is usable. Results should be treated as indicative "
            "and paired with interviewer judgment."
        )
        confidence_level = "medium"
    else:
        quality = "WEAK"
        readiness = "Baseline weak"
        readiness_note = (
            "The baseline is weak. Analysis may produce unreliable results. "
            "Consider collecting additional samples before proceeding."
        )
        confidence_level = "low"

    # ── Comparison context awareness ──────────────────────────────────────────
    comparison_context = _build_comparison_context(formality, filler_ratio, word_count)

    # ── Safe recruiter copy ────────────────────────────────────────────────────
    recruiter_summary = _build_recruiter_summary(
        quality, word_count, filler_ratio, formality, strengths, issues
    )

    return {
        # Quality tier
        "quality":            quality,
        "quality_info":       QUALITY_LEVELS[quality],
        "quality_score":      score,
        # Confidence
        "confidence_level":   confidence_level,
        "confidence_info":    CONFIDENCE_LABELS[confidence_level],
        # Readiness
        "readiness":          readiness,
        "readiness_note":     readiness_note,
        # Sample adequacy
        "adequacy_label":     adequacy_label,
        "adequacy_note":      adequacy_note,
        "word_count":         word_count,
        # Natural speech
        "filler_note":        filler_note,
        "filler_ratio":       filler_ratio,
        # Formality context
        "formality_context":  formality_context,
        "formality_score":    formality,
        # Sentence variety
        "variety_note":       variety_note,
        "sentence_count":     sentence_count,
        # Explainability
        "strengths":          strengths,
        "issues":             issues,
        "recommendations":    recommendations,
        "comparison_context": comparison_context,
        "recruiter_summary":  recruiter_summary,
        # Compliance
        "disclaimer":         DISCLAIMER,
        # Multi-baseline support (future)
        "baseline_type":      "casual_intro",
        "baseline_index":     1,
        "baseline_label":     "Personal Introduction",
        "supports_structured": False,  # future: True when project-baseline collected
    }


def _build_comparison_context(formality: float, filler_ratio: float, word_count: int) -> str:
    """
    Explains to the recruiter what the system will compare against.
    """
    parts = []
    if formality < 45:
        parts.append("casual conversational speech")
    elif formality < 65:
        parts.append("moderately formal speech")
    else:
        parts.append("formal structured speech")

    if filler_ratio > 0.02:
        parts.append("with natural spoken fillers")

    if word_count >= 60:
        parts.append("and a well-established vocabulary fingerprint")
    else:
        parts.append("with a limited vocabulary sample")

    return (
        f"Technical answers will be compared against the candidate's {', '.join(parts)}. "
        "A formality or vocabulary jump beyond the normal range for this baseline "
        "will trigger a style-shift alert."
    )


def _build_recruiter_summary(
    quality: str,
    word_count: int,
    filler_ratio: float,
    formality: float,
    strengths: list,
    issues: list,
) -> str:
    """
    Safe, non-accusatory recruiter-facing summary.
    """
    if quality == "STRONG":
        return (
            f"Good baseline captured ({word_count} words). "
            "The system has a clear picture of this candidate's natural communication style. "
            "Any significant shift during the technical round will be flagged for your review."
        )
    elif quality == "ADEQUATE":
        return (
            f"Usable baseline captured ({word_count} words). "
            "The system can detect significant style shifts, but results should be "
            "treated as supporting evidence rather than conclusive findings. "
            "Follow-up questions are recommended if any flags appear."
        )
    else:
        return (
            f"Thin baseline ({word_count} words). "
            "The system may produce less reliable comparisons in this session. "
            "We recommend collecting more personal context before starting the technical round."
        )
