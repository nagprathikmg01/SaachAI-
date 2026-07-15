"""
verdict_aggregator.py - Multi-layer 5-tier verdict system.

Verdict is NOT just based on LSDI score alone.
It considers multiple evidence layers:

  1. LSDI score (baseline-vs-live divergence)
  2. Confidence level (answer length, baseline quality, signal count)
  3. Signal count and type
  4. Answer length adequacy
  5. AI combo flag (definitive fingerprint)
  6. Temporal drift presence

Short answers ALWAYS cap the verdict at NEEDS_REVIEW.
Low confidence ALWAYS prevents HIGH_RISK verdict.
"""

from typing import Optional


# ── Verdict tier definitions ─────────────────────────────────────────────────

VERDICTS = {
    "GENUINE": {
        "label":           "Genuine",
        "color":           "green",
        "safe_wording":    "No significant indicators detected. Candidate appears to be responding naturally.",
        "interviewer_note": "No action needed.",
    },
    "LOW_RISK": {
        "label":           "Low Risk",
        "color":           "teal",
        "safe_wording":    "Minor style differences observed. Likely reflects topic change or natural variation.",
        "interviewer_note": "No immediate concern. Monitor subsequent answers.",
    },
    "NEEDS_REVIEW": {
        "label":           "Needs Review",
        "color":           "yellow",
        "safe_wording":    "Noticeable style shift detected. Could reflect rehearsal, preparation, or external assistance.",
        "interviewer_note": "Ask one or two follow-up questions to verify understanding.",
    },
    "SUSPICIOUS": {
        "label":           "Suspicious",
        "color":           "orange",
        "safe_wording":    "Multiple style signals present. Pattern is consistent with possible prepared or AI-assisted answer.",
        "interviewer_note": "Ask follow-up questions requiring spontaneous reasoning and personal examples.",
    },
    "HIGH_RISK": {
        "label":           "High Risk",
        "color":           "red",
        "safe_wording":    "Strong style divergence across multiple dimensions. Pattern warrants close scrutiny.",
        "interviewer_note": "Ask candidate to re-explain in simpler terms and provide specific personal examples.",
    },
}

DISCLAIMER = (
    "This tool supports interviewer judgment and should not be used as the sole basis "
    "for any hiring decision. Style differences can reflect rehearsal, fluency, communication "
    "style, or language background - not only AI assistance. Low-confidence and short-answer "
    "results require particular caution."
)


def compute_verdict(
    lsdi_score: float,
    confidence_level: str,
    signal_count: int,
    ai_combo: bool,
    answer_word_count: int,
    temporal_has_spike: bool,
    style_shift: str,
) -> dict:
    """
    Computes the 5-tier verdict based on multiple evidence layers.

    Returns:
        verdict:         one of GENUINE / LOW_RISK / NEEDS_REVIEW / SUSPICIOUS / HIGH_RISK
        verdict_info:    label, color, safe_wording, interviewer_note
        disclaimer:      compliance text
        capped_reason:   if verdict was capped, explains why
    """

    # ── Raw verdict from LSDI alone ───────────────────────────────────────────
    if lsdi_score >= 75:
        raw_verdict = "HIGH_RISK"
    elif lsdi_score >= 55:
        raw_verdict = "SUSPICIOUS"
    elif lsdi_score >= 35:
        raw_verdict = "NEEDS_REVIEW"
    elif lsdi_score >= 20:
        raw_verdict = "LOW_RISK"
    else:
        raw_verdict = "GENUINE"

    # Promote based on additional evidence
    if ai_combo and raw_verdict not in ("HIGH_RISK", "SUSPICIOUS"):
        raw_verdict = "SUSPICIOUS"
    if signal_count >= 5 and raw_verdict == "NEEDS_REVIEW":
        raw_verdict = "SUSPICIOUS"
    if temporal_has_spike and raw_verdict == "LOW_RISK":
        raw_verdict = "NEEDS_REVIEW"

    # ── Guardrails — cap verdict downward ─────────────────────────────────────
    cap_reasons: list[str] = []

    # Short answer cap
    if answer_word_count < 40 and raw_verdict in ("SUSPICIOUS", "HIGH_RISK"):
        raw_verdict = "NEEDS_REVIEW"
        cap_reasons.append("answer too short (< 40 words) for strong conclusions")

    # Low confidence cap
    if confidence_level in ("very_low", "low") and raw_verdict == "HIGH_RISK":
        raw_verdict = "SUSPICIOUS"
        cap_reasons.append("low analysis confidence")

    # Very low confidence cap
    if confidence_level == "very_low" and raw_verdict in ("SUSPICIOUS", "HIGH_RISK"):
        raw_verdict = "NEEDS_REVIEW"
        cap_reasons.append("insufficient data (very low confidence)")

    final_verdict = raw_verdict
    capped_reason = "; ".join(cap_reasons) if cap_reasons else None

    return {
        "verdict":       final_verdict,
        "verdict_info":  VERDICTS[final_verdict],
        "disclaimer":    DISCLAIMER,
        "capped_reason": capped_reason,
    }


def build_evidence_objects(
    fill_drop: float,
    voc_jump: float,
    fk_jump: float,
    fog_jump: float,
    hedge_jump: float,
    passive_jump: float,
    burst_drop: float,
    t_density_diff: float,
    temporal: dict,
    ai_combo: bool,
    p: dict,
    t: dict,
    answer_word_count: int,
    confidence_level: str,
) -> list[dict]:
    """
    Builds a list of structured evidence objects.
    Each object has: type, label, description, severity, value, caveat, action.
    Only includes signals that clearly exceed threshold.
    """
    evidence: list[dict] = []
    is_short = answer_word_count < 40
    short_caveat = "Answer was short - this signal may simply reflect brevity." if is_short else None

    # ── AI Combo (definitive fingerprint) ─────────────────────────────────────
    if ai_combo:
        evidence.append({
            "type":        "ai_combo",
            "label":       "Possible AI-assisted answer",
            "description": (
                "Filler words disappeared, vocabulary spiked, and formal connectors appeared "
                "simultaneously. This combination is rare in natural speech."
            ),
            "severity":    "high",
            "value":       "3-signal combo",
            "caveat":      short_caveat or "Could also reflect a heavily rehearsed prepared answer.",
            "action":      "Ask candidate to re-explain informally and give a personal example.",
        })

    # ── Filler drop ───────────────────────────────────────────────────────────
    if fill_drop > 0.04 and p.get("filler_ratio", 0) > 0.01 and not ai_combo:
        evidence.append({
            "type":        "filler_drop",
            "label":       "Filler words dropped",
            "description": (
                f"Spoken fillers fell from {p['filler_ratio']:.1%} (personal) "
                f"to {t['filler_ratio']:.1%} (technical). "
                "Natural speech always contains some fillers."
            ),
            "severity":    "medium",
            "value":       f"-{fill_drop:.1%}",
            "caveat":      short_caveat or "Rehearsed answers also tend to have fewer fillers.",
            "action":      "Ask candidate to re-explain more casually.",
        })

    # ── Vocab jump ────────────────────────────────────────────────────────────
    if voc_jump > 18:
        evidence.append({
            "type":        "vocab_spike",
            "label":       "Vocabulary spike",
            "description": (
                f"Vocabulary sophistication jumped +{voc_jump:.0f} pts. "
                "Everyday vocabulary shifted to formal technical language."
            ),
            "severity":    "medium" if voc_jump < 25 else "high",
            "value":       f"+{voc_jump:.0f} pts",
            "caveat":      short_caveat or "Technical topics naturally require specialized vocabulary.",
            "action":      "Ask candidate to simplify the explanation.",
        })

    # ── Flesch-Kincaid jump ────────────────────────────────────────────────────
    if fk_jump > 3.0:
        evidence.append({
            "type":        "complexity_jump",
            "label":       "Reading complexity spike",
            "description": (
                f"Text complexity jumped +{fk_jump:.1f} grade levels. "
                "The technical answer is significantly harder to parse than the personal intro."
            ),
            "severity":    "medium",
            "value":       f"+{fk_jump:.1f} FK grade levels",
            "caveat":      "Technical topics are inherently more complex.",
            "action":      "Ask candidate to explain in simpler terms.",
        })

    # ── Passive voice ─────────────────────────────────────────────────────────
    if passive_jump > 0.25:
        evidence.append({
            "type":        "passive_voice",
            "label":       "Passive voice increase",
            "description": (
                f"Passive voice usage increased by {passive_jump:.0%}. "
                "AI-generated and pre-written text use passive voice far more than natural speech."
            ),
            "severity":    "low" if passive_jump < 0.4 else "medium",
            "value":       f"+{passive_jump:.0%}",
            "caveat":      short_caveat or "Some technical domains prefer passive voice by convention.",
            "action":      "Ask 'What did YOU specifically do in that situation?'",
        })

    # ── Sentence burstiness ───────────────────────────────────────────────────
    if burst_drop > 0.2 and t.get("sentence_burstiness", 1.0) < 0.25:
        evidence.append({
            "type":        "sentence_uniformity",
            "label":       "Unnaturally uniform sentences",
            "description": (
                f"Sentence length variation dropped to {t['sentence_burstiness']:.2f} "
                "(human speech typically scores 0.4+). "
                "AI text tends to be unnaturally even in structure."
            ),
            "severity":    "medium",
            "value":       f"burstiness: {t['sentence_burstiness']:.2f}",
            "caveat":      "Short answers will also score low on burstiness.",
            "action":      "Note this as a supporting signal rather than primary evidence.",
        })

    # ── Transition density ────────────────────────────────────────────────────
    if t_density_diff > 30 and t.get("transition_density", 0) > 0.05:
        evidence.append({
            "type":        "transition_density",
            "label":       "Formal connector overuse",
            "description": (
                "High density of formal connectors (furthermore, additionally, however). "
                "Natural spoken answers rarely use these; AI and pre-written text overuses them."
            ),
            "severity":    "medium",
            "value":       f"density: {t['transition_density']:.3f}",
            "caveat":      "Some candidates prepare structured answers - this alone is not conclusive.",
            "action":      "Ask candidate to re-state the key point informally.",
        })

    # ── Temporal drift ────────────────────────────────────────────────────────
    if temporal.get("has_spike") and not is_short:
        win_label = {2: "mid-answer", 3: "near the end"}.get(
            temporal.get("drift_window", 0), "mid-answer"
        )
        evidence.append({
            "type":        "temporal_drift",
            "label":       f"Style shift {win_label}",
            "description": (
                f"Complexity spiked {win_label} (+{temporal.get('drift_score', 0):.0f} pts). "
                "Candidate may have started naturally then referenced prepared material."
            ),
            "severity":    "medium",
            "value":       f"+{temporal.get('drift_score', 0):.0f} pts",
            "caveat":      "This can also happen when a candidate remembers an answer mid-sentence.",
            "action":      "Ask 'What was your initial instinct when I asked that question?'",
        })

    # ── Hedging ───────────────────────────────────────────────────────────────
    if hedge_jump > 0.005:
        evidence.append({
            "type":        "hedging_density",
            "label":       "Academic hedging phrases",
            "description": (
                "Phrases like 'it is worth noting', 'one must consider' appeared. "
                "These are rare in natural speech but common in AI and academic text."
            ),
            "severity":    "low",
            "value":       f"+{hedge_jump:.4f}",
            "caveat":      "Could reflect a well-studied candidate using formal language.",
            "action":      "Ask candidate to express their personal opinion directly.",
        })

    return evidence
