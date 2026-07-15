"""
test_style_comparator.py — Unit tests for the style shift detection engine.

Run with:
    cd backend
    python -m pytest voice_module/test_style_comparator.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

try:
    from voice_module.style_comparator import (
        calculate_style_shift,
        _avg_sentence_len,
        _lexical_diversity,
        _vocabulary_level,
        _grammar_score,
        _filler_ratio,
        _transition_density,
        _formality_score,
        _build_profile,
    )
except ImportError:
    from backend.voice_module.style_comparator import (
        calculate_style_shift,
        _avg_sentence_len,
        _lexical_diversity,
        _vocabulary_level,
        _grammar_score,
        _filler_ratio,
        _transition_density,
        _formality_score,
        _build_profile,
    )


# ── Profile builder helpers ───────────────────────────────────────────────────

class TestAvgSentenceLen:
    def test_single_sentence(self):
        result = _avg_sentence_len("Hello world this is a test.")
        assert result > 0

    def test_multiple_sentences(self):
        result = _avg_sentence_len("Hello world. This is a test. Great day.")
        assert result == pytest.approx(3.0, abs=1.0)

    def test_empty(self):
        assert _avg_sentence_len("") == 0.0


class TestLexicalDiversity:
    def test_full_diversity(self):
        # All unique words → diversity = 1.0
        result = _lexical_diversity("cat dog bird fish")
        assert result == pytest.approx(1.0)

    def test_zero_diversity(self):
        # All same word → diversity low
        result = _lexical_diversity("the the the the")
        assert result < 0.5

    def test_empty(self):
        assert _lexical_diversity("") == 0.0


class TestVocabularyLevel:
    def test_simple_vocabulary(self):
        simple = _vocabulary_level("I like to play and run and jump around here")
        assert simple < 50

    def test_complex_vocabulary(self):
        complex_text = _vocabulary_level(
            "Sophisticated algorithmic implementations demonstrate computational efficiency"
        )
        assert complex_text > simple_text if (simple_text := _vocabulary_level("I like to run")) else True

    def test_empty(self):
        assert _vocabulary_level("") == 0.0


class TestGrammarScore:
    def test_good_grammar(self):
        score = _grammar_score("This is a well-formed sentence. Here is another one.")
        assert score >= 70

    def test_fragment_penalised(self):
        good  = _grammar_score("This is a proper sentence.")
        bad   = _grammar_score("yes. no. ok. sure. fine.")
        assert good > bad

    def test_empty(self):
        result = _grammar_score("")
        assert result >= 0


class TestFillerRatio:
    def test_no_fillers(self):
        result = _filler_ratio("The system processes data efficiently.")
        assert result == 0.0

    def test_with_fillers(self):
        result = _filler_ratio("um I was like basically going you know to the store")
        assert result > 0

    def test_empty(self):
        assert _filler_ratio("") == 0.0


class TestTransitionDensity:
    def test_no_transitions(self):
        result = _transition_density("I went to the store and bought milk.")
        assert result == 0.0

    def test_high_transitions(self):
        result = _transition_density(
            "Furthermore, consequently this demonstrates that however "
            "additionally it should be noted that specifically in conclusion."
        )
        assert result > 0.04


# ── Main style shift function ──────────────────────────────────────────────────

CASUAL_PERSONAL = (
    "Hi I'm John, um I studied computer science and I like to code. "
    "I've been working on some web projects you know. "
    "I'm pretty good with JavaScript and like React and stuff. "
    "I basically enjoy building things."
)

AI_TECHNICAL = (
    "The application leverages a sophisticated microservices architecture "
    "implementing RESTful API endpoints with JWT-based authentication mechanisms. "
    "Furthermore, the system utilizes asynchronous processing paradigms to ensure "
    "optimal throughput and scalability. Consequently, the architectural decisions "
    "demonstrate a comprehensive understanding of distributed systems design principles. "
    "Additionally, the implementation incorporates advanced caching strategies to "
    "minimize database query latency and improve response times significantly."
)

CONSISTENT_PERSONAL = (
    "Hi, I'm Jane. I have a background in software engineering with three years "
    "of professional experience. I have worked on backend systems and API design. "
    "I am comfortable with Python, FastAPI, and database optimization."
)

CONSISTENT_TECHNICAL = (
    "In my recent project I built a REST API using FastAPI and PostgreSQL. "
    "I designed the schema to optimize for read performance. "
    "I also added caching using Redis to reduce database load. "
    "The project improved response time by around forty percent."
)


class TestCalculateStyleShift:
    def test_returns_required_keys(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        required = [
            "authenticity_score", "style_shift", "shift_score",
            "flags", "summary", "personal_profile", "technical_profile",
            "shift_breakdown", "strong_signal_count",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_ai_response_flagged_high(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        assert result["style_shift"] in ("HIGH", "VERY HIGH")
        assert result["shift_score"] >= 40

    def test_consistent_responses_flagged_low(self):
        result = calculate_style_shift(CONSISTENT_PERSONAL, CONSISTENT_TECHNICAL)
        assert result["style_shift"] in ("LOW", "MODERATE")
        assert result["authenticity_score"] >= 60

    def test_authenticity_score_range(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        assert 0.0 <= result["authenticity_score"] <= 100.0

    def test_shift_score_range(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        assert 0.0 <= result["shift_score"] <= 100.0

    def test_profiles_populated(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        p_profile = result["personal_profile"]
        t_profile = result["technical_profile"]
        assert p_profile["word_count"] > 0
        assert t_profile["word_count"] > 0

    def test_flags_are_strings(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        for flag in result["flags"]:
            assert isinstance(flag, str)

    def test_empty_inputs_handled_gracefully(self):
        result = calculate_style_shift("Hello.", "Hello.")
        assert "style_shift" in result
        assert result["shift_score"] >= 0

    def test_identical_texts_low_shift(self):
        text = "I built a REST API using Python and FastAPI for my internship project."
        result = calculate_style_shift(text, text)
        assert result["style_shift"] == "LOW"

    def test_word_ratio_penalty_applied(self):
        """If technical is 3× longer, penalty should push score higher."""
        short_personal = "I built a website."
        long_technical = (AI_TECHNICAL + " " + AI_TECHNICAL + " " + AI_TECHNICAL)
        result = calculate_style_shift(short_personal, long_technical)
        assert result["shift_score"] > 40

    def test_strong_signal_count_accuracy(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        assert isinstance(result["strong_signal_count"], int)
        assert result["strong_signal_count"] >= 0


class TestStyleShiftTiers:
    def test_low_tier_produces_high_authenticity(self):
        result = calculate_style_shift(CONSISTENT_PERSONAL, CONSISTENT_TECHNICAL)
        if result["style_shift"] == "LOW":
            assert result["authenticity_score"] >= 80

    def test_very_high_tier_produces_low_authenticity(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        if result["style_shift"] == "VERY HIGH":
            assert result["authenticity_score"] <= 40

    def test_summary_is_non_empty_string(self):
        result = calculate_style_shift(CASUAL_PERSONAL, AI_TECHNICAL)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 20
