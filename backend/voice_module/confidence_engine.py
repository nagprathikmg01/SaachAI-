"""
confidence_engine.py - Calculates analysis confidence level.

Confidence answers: "How much should the interviewer trust this result?"

Factors:
  - Answer length (longer = more reliable)
  - Baseline quality (more words in personal intro = better baseline)
  - Signal consistency (more signals agreeing = higher confidence)
  - Streaming partial flag (reduce confidence for mid-stream chunks)

Output levels: very_low / low / medium / high
"""

from typing import Optional


def calculate_confidence(
    answer_word_count: int,
    personal_word_count: int,
    signal_count: int,
    is_streaming_partial: bool = False,
) -> dict:
    """
    Returns a confidence dict with level, label, score, factors, and caveat.
    Used to gate how aggressively verdicts are stated.
    """

    # ── Answer length factor (weight 0.50) ────────────────────────────────────
    if answer_word_count < 15:
        length_conf  = "very_low"
        length_score = 0.10
    elif answer_word_count < 30:
        length_conf  = "low"
        length_score = 0.30
    elif answer_word_count < 60:
        length_conf  = "medium"
        length_score = 0.65
    else:
        length_conf  = "high"
        length_score = 1.00

    # ── Baseline quality factor (weight 0.30) ─────────────────────────────────
    if personal_word_count < 30:
        baseline_conf  = "low"
        baseline_score = 0.30
    elif personal_word_count < 60:
        baseline_conf  = "medium"
        baseline_score = 0.65
    else:
        baseline_conf  = "high"
        baseline_score = 1.00

    # ── Signal consistency factor (weight 0.20) ───────────────────────────────
    if signal_count == 0:
        signal_label = "none"
        signal_score = 0.50   # absence of signals = neutral, not certain
    elif signal_count <= 2:
        signal_label = "weak"
        signal_score = 0.50
    elif signal_count <= 4:
        signal_label = "moderate"
        signal_score = 0.75
    else:
        signal_label = "strong"
        signal_score = 1.00

    # ── Streaming partial penalty ─────────────────────────────────────────────
    stream_penalty = 0.75 if is_streaming_partial else 1.00

    # ── Composite score ───────────────────────────────────────────────────────
    raw_score = (
        length_score  * 0.50 +
        baseline_score * 0.30 +
        signal_score  * 0.20
    ) * stream_penalty

    overall_score = round(raw_score, 2)

    if overall_score < 0.25:
        level = "very_low";  label = "Very Low"
    elif overall_score < 0.45:
        level = "low";       label = "Low"
    elif overall_score < 0.70:
        level = "medium";    label = "Medium"
    else:
        level = "high";      label = "High"

    # ── Caveats ───────────────────────────────────────────────────────────────
    caveats: list[str] = []
    if length_conf in ("very_low", "low"):
        caveats.append("answer too short for reliable analysis")
    if baseline_conf == "low":
        caveats.append("personal intro was brief - baseline may be unrepresentative")
    if is_streaming_partial:
        caveats.append("based on partial transcription - score may change")
    caveat: Optional[str] = "; ".join(caveats) if caveats else None

    return {
        "level":   level,
        "label":   label,
        "score":   overall_score,
        "factors": {
            "answer_length":      length_conf,
            "baseline_quality":   baseline_conf,
            "signal_consistency": signal_label,
        },
        "caveat": caveat,
    }


def get_short_answer_guardrail(answer_word_count: int) -> Optional[str]:
    """
    Returns a guardrail message if the answer is too short to make strong claims.
    Returns None if the answer is long enough.
    """
    if answer_word_count < 15:
        return (
            "Insufficient data (< 15 words). "
            "Results are not reliable. Do not use for decision-making."
        )
    if answer_word_count < 30:
        return (
            "Low-confidence analysis (< 30 words). "
            "Treat results as indicative only. Ask a follow-up for more data."
        )
    if answer_word_count < 50:
        return (
            "Short answer (< 50 words). "
            "Minor style differences observed - may simply reflect brevity."
        )
    return None
