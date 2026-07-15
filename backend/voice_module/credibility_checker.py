"""
credibility_checker.py — LLM-based answer correctness / credibility scoring.

Uses OpenAI GPT to evaluate whether a candidate's spoken response adequately
answers a given interview question, optionally compared against a model answer.

Verdict levels
--------------
CORRECT        — Response clearly and accurately addresses the question.
PARTIALLY      — Response partially addresses the question; key gaps present.
INCORRECT      — Response is factually wrong, off-topic, or non-committal.
INSUFFICIENT   — Response is too short / vague to evaluate.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy OpenAI import ────────────────────────────────────────────────────────

_openai_client = None
_OPENAI_FAILED  = False  # set True after first auth failure — skips retry


def _get_openai():
    global _openai_client, _OPENAI_FAILED
    if _OPENAI_FAILED:
        return None
    if _openai_client is None:
        try:
            import openai
            _openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        except Exception as exc:
            logger.warning("[credibility] OpenAI not available: %s", exc)
            _openai_client = None
            _OPENAI_FAILED = True
    return _openai_client



# ── Public API ────────────────────────────────────────────────────────────────

def check_answer_credibility(
    question: str,
    candidate_response: str,
    expected_answer: Optional[str] = None,
) -> dict:
    """
    Evaluate whether *candidate_response* correctly addresses *question*.

    Parameters
    ----------
    question          : The interview question that was asked.
    candidate_response: Transcript of what the candidate said.
    expected_answer   : Optional model / reference answer for comparison.

    Returns
    -------
    dict with keys:
        verdict         : "CORRECT" | "PARTIALLY" | "INCORRECT" | "INSUFFICIENT"
        confidence      : float 0–1
        score           : int 0–100
        explanation     : str  — human-readable rationale for the verdict
        key_points_hit  : list[str]  — what the candidate got right
        key_points_missed: list[str] — what was missing or wrong
        suggestions     : str  — coaching note for the interviewer
    """
    client = _get_openai()
    if client is None:
        return _fallback_verdict(question, candidate_response, expected_answer)

    # Reject trivially short responses immediately
    if len(candidate_response.split()) < 8:
        return {
            "verdict": "INSUFFICIENT",
            "confidence": 1.0,
            "score": 0,
            "explanation": "Response too short to evaluate.",
            "key_points_hit": [],
            "key_points_missed": ["Substantive answer"],
            "suggestions": "Prompt the candidate to elaborate.",
        }

    # ── Build prompt ─────────────────────────────────────────────────────────
    ref_block = (
        f"\n\nREFERENCE / EXPECTED ANSWER:\n{expected_answer.strip()}"
        if expected_answer and expected_answer.strip()
        else ""
    )

    system_msg = (
        "You are an expert technical interview evaluator. "
        "Your task is to assess whether a candidate's spoken response correctly "
        "addresses an interview question. Be objective, concise, and constructive. "
        "Do NOT penalise for filler words, informal language, or minor phrasing issues — "
        "focus only on technical/factual correctness and completeness."
    )

    user_msg = (
        f"INTERVIEW QUESTION:\n{question.strip()}"
        f"{ref_block}"
        f"\n\nCANDIDATE'S RESPONSE:\n{candidate_response.strip()}"
        "\n\n---"
        "\nEvaluate the candidate's response and respond ONLY with a JSON object "
        "(no markdown fences) with exactly these keys:\n"
        '{"verdict": "CORRECT|PARTIALLY|INCORRECT|INSUFFICIENT", '
        '"confidence": <0.0-1.0>, '
        '"score": <0-100>, '
        '"explanation": "<1-2 sentence rationale>", '
        '"key_points_hit": ["<point>", ...], '
        '"key_points_missed": ["<point>", ...], '
        '"suggestions": "<coaching note for the interviewer>"}'
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
        import json
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)

        # Normalise / sanitise
        verdict = str(data.get("verdict", "INSUFFICIENT")).upper()
        if verdict not in ("CORRECT", "PARTIALLY", "INCORRECT", "INSUFFICIENT"):
            verdict = "INSUFFICIENT"

        return {
            "verdict":            verdict,
            "confidence":         float(data.get("confidence", 0.5)),
            "score":              int(data.get("score", 0)),
            "explanation":        str(data.get("explanation", "")),
            "key_points_hit":     list(data.get("key_points_hit", [])),
            "key_points_missed":  list(data.get("key_points_missed", [])),
            "suggestions":        str(data.get("suggestions", "")),
        }

    except Exception as exc:
        logger.warning("[credibility] LLM call failed: %s", exc)
        # Mark failed permanently on auth errors to avoid repeated 401s
        if "401" in str(exc) or "AuthenticationError" in type(exc).__name__:
            global _OPENAI_FAILED
            _OPENAI_FAILED = True
        return _fallback_verdict(question, candidate_response, expected_answer)


# ── Enhanced heuristic fallback (no LLM) ─────────────────────────────────────

_STOP = frozenset([
    "what", "when", "where", "which", "explain", "describe", "tell", "about",
    "have", "does", "would", "could", "should", "that", "this", "with", "from",
    "your", "they", "their", "will", "been", "were", "have", "here", "there",
    "also", "more", "very", "just", "some", "into", "over", "after", "such",
    "than", "then", "them", "these", "those", "each", "both", "make", "made",
    "like", "time", "only", "well", "even", "back", "come", "good", "know",
    "take", "most", "people", "other", "many", "used", "said", "need", "work",
    "long", "high", "every", "through", "while", "same", "help", "between",
])


def _tfidf_cosine(text_a: str, text_b: str) -> float:
    """Compute TF-IDF cosine similarity between two texts without sklearn."""
    import re, math

    def tokenize(t: str):
        return [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", t.lower()) if w not in _STOP]

    ta, tb = tokenize(text_a), tokenize(text_b)
    if not ta or not tb:
        return 0.0

    vocab = set(ta) | set(tb)

    def tf(tokens):
        cnt = {}
        for t in tokens:
            cnt[t] = cnt.get(t, 0) + 1
        return {t: c / len(tokens) for t, c in cnt.items()}

    ta_tf, tb_tf = tf(ta), tf(tb)

    # IDF over only 2 docs
    idf = {
        w: math.log(2 / (1 + (1 if w in ta_tf else 0) + (1 if w in tb_tf else 0))) + 1
        for w in vocab
    }

    def vec(tf_map):
        return {w: tf_map.get(w, 0) * idf[w] for w in vocab}

    va, vb = vec(ta_tf), vec(tb_tf)
    dot   = sum(va[w] * vb[w] for w in vocab)
    mag_a = math.sqrt(sum(v ** 2 for v in va.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vb.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _keywords_in_common(text_a: str, text_b: str) -> tuple:
    """Return (words in both, words only in text_a)."""
    import re
    def kw(t):
        return {w for w in re.findall(r"\b[a-zA-Z]{4,}\b", t.lower()) if w not in _STOP}
    a, b = kw(text_a), kw(text_b)
    return sorted(a & b), sorted(a - b)


def _fallback_verdict(
    question: str,
    candidate_response: str,
    expected_answer: Optional[str] = None,
) -> dict:
    """
    Multi-signal heuristic when OpenAI is unavailable.

    Signals:
      1. TF-IDF cosine similarity between candidate response and question
      2. TF-IDF cosine similarity between candidate response and expected_answer (if provided)
      3. Response length adequacy
      4. Key-concept overlap analysis
    """
    wc = len(candidate_response.split())
    if wc < 8:
        return {
            "verdict": "INSUFFICIENT",
            "confidence": 1.0,
            "score": 0,
            "explanation": "Response too short to evaluate (fewer than 8 words).",
            "key_points_hit": [],
            "key_points_missed": [],
            "suggestions": "Ask the candidate to elaborate with more detail.",
        }

    # Signal 1: question similarity
    q_sim = _tfidf_cosine(question, candidate_response)

    # Signal 2: expected-answer similarity + key concept overlap
    if expected_answer and expected_answer.strip():
        exp_sim = _tfidf_cosine(expected_answer, candidate_response)
        ref_text = expected_answer
        using_expected = True

        # Key concept coverage: how many ref keywords does the candidate cover?
        exp_hit, exp_miss = _keywords_in_common(expected_answer, candidate_response)
        total_ref_kw = len(exp_hit) + len(exp_miss)
        concept_coverage = len(exp_hit) / max(total_ref_kw, 1)

        # Blend: TF-IDF (30%) + concept coverage (70%)
        combined_sim = exp_sim * 0.30 + concept_coverage * 0.70
    else:
        exp_sim = 0.0
        ref_text = question
        using_expected = False

        # Key concept coverage vs. the question itself
        q_hit, q_miss = _keywords_in_common(question, candidate_response)
        total_q_kw = len(q_hit) + len(q_miss)
        concept_coverage = len(q_hit) / max(total_q_kw, 1)

        combined_sim = q_sim * 0.40 + concept_coverage * 0.60

    # Signal 3: length bonus (longer spoken answers are usually more complete)
    length_bonus = min(0.08, (wc - 8) / 300)
    final_sim = min(1.0, combined_sim + length_bonus)

    # Scale score 0-100 and apply verdict thresholds
    # Spoken answers naturally have lower cosine similarity — calibrate generously
    score = int(final_sim * 100)

    if final_sim >= 0.45:
        verdict, conf = "CORRECT", round(final_sim, 2)
    elif final_sim >= 0.22:
        verdict, conf = "PARTIALLY", round(final_sim, 2)
    else:
        verdict, conf = "INCORRECT", round(final_sim, 2)



    hit, miss = _keywords_in_common(ref_text, candidate_response)

    source = "expected answer" if using_expected else "question"
    if verdict == "CORRECT":
        explanation = (
            f"The candidate's response covers the main concepts from the {source} well "
            f"(similarity: {final_sim:.0%}). Response length: {wc} words."
        )
    elif verdict == "PARTIALLY":
        explanation = (
            f"The candidate addressed some aspects of the {source} but key concepts are missing "
            f"(similarity: {final_sim:.0%}). Response length: {wc} words."
        )
    else:
        explanation = (
            f"The candidate's response shows low alignment with the {source} "
            f"(similarity: {final_sim:.0%}). Either off-topic or insufficient depth."
        )

    suggestions = (
        f"Probe further on: {', '.join(miss[:4])}." if miss
        else ("Strong answer. Consider a follow-up to test edge cases." if verdict == "CORRECT"
              else "Ask the candidate to elaborate or rephrase their answer.")
    )

    return {
        "verdict":           verdict,
        "confidence":        conf,
        "score":             score,
        "explanation":       explanation,
        "key_points_hit":    hit[:6],
        "key_points_missed": miss[:6],
        "suggestions":       suggestions,
    }

