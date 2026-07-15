"""
style_comparator.py - Proven 11-parameter linguistic shift detector.

Restored to the original working approach (commit bceb9fc) that gave
accurate results in field testing.

Core parameters (all domain-appropriate for SPOKEN interview transcripts):
  vocabulary_level   - avg word length + long-word ratio (proxy for sophistication)
  flesch_kincaid     - FK grade level
  formality_score    - composite: vocab + sentence length - filler density
  gunning_fog        - polysyllabic density
  hedging_density    - epistemic hedging phrases
  passive_voice_ratio- be-form + past-participle pattern
  grammar_score      - penalises fragments and disfluencies
  avg_sentence_len   - words per sentence
  lexical_diversity  - type-token ratio
  filler_ratio       - um/uh/like etc.
  transition_density - formal connectors: however/furthermore/therefore
  sentence_burstiness- CV of sentence lengths

v2 additions (additive - old fields kept for backward compat):
  confidence         - answer length + baseline quality + signal count
  verdict            - 5-tier weighted verdict (GENUINE/LOW_RISK/NEEDS_REVIEW/SUSPICIOUS/HIGH_RISK)
  evidence           - structured evidence objects with caveats and actions
  followup_questions - interviewer follow-up questions per detected signal
  safe_interpretation- non-accusatory plain-English summary
  disclaimer         - compliance / fairness statement
"""

import re
import math
import logging
import os
import pickle
import numpy as np
from typing import Any

from .confidence_engine import calculate_confidence, get_short_answer_guardrail
from .verdict_aggregator import compute_verdict, build_evidence_objects, DISCLAIMER
from .followup_generator import generate_followups, get_active_signals

logger = logging.getLogger(__name__)


# ── Load ML Model ─────────────────────────────────────────────────────────────
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")
MODEL_PATH = os.path.join(MODEL_DIR, "sachhAI_classifier.pkl")

clf_model = None
if os.path.exists(MODEL_PATH):
    try:
        import joblib
        clf_model = joblib.load(MODEL_PATH)
        logger.info("[style_comparator] Loaded ML classifier model successfully via joblib.")
    except Exception as e:
        logger.warning("[style_comparator] Failed to load ML classifier with joblib: %s", e)
        try:
            with open(MODEL_PATH, "rb") as f:
                clf_model = pickle.load(f)
            logger.info("[style_comparator] Loaded ML classifier model successfully via pickle.")
        except Exception as e2:
            logger.warning("[style_comparator] Failed to load ML classifier with pickle: %s", e2)
else:
    logger.warning("[style_comparator] ML classifier not found at %s", MODEL_PATH)


def extract_features(personal: str, technical: str) -> np.ndarray:
    """
    Extract ML features from a personal/technical text pair.
    Returns a 1D numpy array of 18 features.
    """
    p = _build_profile(personal)
    t = _build_profile(technical)

    # Absolute metric deltas
    vocab_jump  = t["vocabulary_level"]  - p["vocabulary_level"]
    formal_jump = t["formality_score"]   - p["formality_score"]
    gram_jump   = t["grammar_score"]     - p["grammar_score"]
    sent_jump   = t["avg_sentence_len"]  - p["avg_sentence_len"]
    fill_drop   = p["filler_ratio"]      - t["filler_ratio"]
    div_diff    = abs(t["lexical_diversity"] - p["lexical_diversity"])
    trans_diff  = _transition_diff(p["transition_density"], t["transition_density"])

    # Ratios
    word_ratio  = t["word_count"] / max(1, p["word_count"])
    sent_ratio  = t["avg_sentence_len"] / max(p["avg_sentence_len"], 1.0)

    # Raw technical profile signals (absolute, not delta)
    t_vocab     = t["vocabulary_level"]
    t_formal    = t["formality_score"]
    t_gram      = t["grammar_score"]
    t_sent      = t["avg_sentence_len"]
    t_trans     = t["transition_density"]
    t_fill      = t["filler_ratio"]

    # Personal profile baseline
    p_fill      = p["filler_ratio"]
    p_vocab     = p["vocabulary_level"]

    # Combined signals
    strong_count = sum([
        vocab_jump  > 12,
        formal_jump > 15,
        gram_jump   > 12,
        sent_jump   > 5,
        fill_drop   > 0.02 and p["filler_ratio"] > 0.01,
        trans_diff  > 30,
    ])

    return np.array([
        vocab_jump, formal_jump, gram_jump, sent_jump,
        fill_drop, div_diff, trans_diff, word_ratio, sent_ratio,
        t_vocab, t_formal, t_gram, t_sent, t_trans, t_fill,
        p_fill, p_vocab, float(strong_count),
    ], dtype=np.float32)


# ── Text helpers ───────────────────────────────────────────────────────────────

def _sentences(text: str) -> list:
    """Split on punctuation first. If the whole text is one long un-punctuated
    block (common with ASR transcripts from spoken speech), fall back to
    splitting on spoken clause-boundary words so avg_sentence_len is realistic.
    """
    sents = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    # If ASR gave us 1 huge run-on, split on spoken clause boundaries
    if len(sents) == 1 and len(sents[0].split()) > 25:
        spoken_split = re.split(
            r'\b(and|but|so|because|then|after|when|while|although|i am|i was|i have|i think|i feel)\b',
            sents[0], flags=re.IGNORECASE
        )
        # Recombine conjunctions with their clause
        rebuilt, buf = [], ""
        for part in spoken_split:
            buf += " " + part
            if len(buf.split()) >= 8:
                rebuilt.append(buf.strip())
                buf = ""
        if buf.strip():
            rebuilt.append(buf.strip())
        if len(rebuilt) > 1:
            sents = rebuilt
    return sents

def _words(text: str) -> list:
    return re.findall(r'\b[a-z]+\b', text.lower())

def _avg_sentence_len(text: str) -> float:
    sents = _sentences(text)
    if not sents:
        return 0.0
    return round(sum(len(s.split()) for s in sents) / len(sents), 1)

def _lexical_diversity(text: str) -> float:
    """Type-token ratio — how varied is the vocabulary?"""
    w = _words(text)
    if not w:
        return 0.0
    return round(len(set(w)) / len(w), 3)

def _vocabulary_level(text: str) -> float:
    """Vocabulary sophistication proxy (0-100).
    Uses average word length + ratio of long words (>7 chars).
    Works reliably on ASR-transcribed spoken text.
    """
    w = _words(text)
    if not w:
        return 0.0
    long_ratio = sum(1 for x in w if len(x) > 7) / len(w)
    avg_len    = sum(len(x) for x in w) / len(w)
    return round(min(100.0, avg_len * 8 + long_ratio * 40), 1)

def _grammar_score(text: str) -> float:
    """Grammar stability proxy (0-100).
    Penalises fragments (<3 words) and consecutive word repeats (disfluencies).
    """
    score = 80.0
    for s in _sentences(text):
        parts = s.split()
        if not parts:
            continue
        if len(parts) < 3:
            score -= 1.5
        # NOTE: do NOT penalise lowercase sentence starts — Meet CC is always
        # lowercase regardless of content quality, so this would unfairly flag
        # genuine technical speakers whose text comes from Meet captions.
    words_all = text.lower().split()
    repeats = sum(1 for a, b in zip(words_all, words_all[1:]) if a == b and len(a) > 2)
    score -= repeats * 3
    return round(max(0.0, min(100.0, score)), 1)


_FILLERS = {
    # Universal spoken disfluencies
    'um', 'uh', 'hmm', 'ah',
    # Very common in informal speech
    'okay', 'ok', 'yeah', 'yep', 'nope', 'right', 'so',
    # Hedge/filler phrases
    'like', 'basically', 'actually', 'literally', 'obviously', 'totally',
    'kind of', 'sort of', 'i think', 'i feel', 'i guess', 'you know',
    'i mean', 'you see', 'well', 'anyway', 'just', 'pretty much',
    # Indian English spoken fillers
    'na', 'no', 'see', 'simply', 'only',
}

def _filler_ratio(text: str) -> float:
    """Density of spoken disfluency markers.
    Counts TOTAL occurrences (not just distinct types) so 'okay okay okay'
    correctly scores higher than a single 'okay'.
    A sudden DROP in fillers in the technical round is suspicious —
    natural speech always has some; AI text has none.
    """
    words = text.lower().split()
    total = max(1, len(words))
    # Count individual word fillers by occurrence
    count = sum(1 for w in words if w in _FILLERS)
    # Also count multi-word fillers by phrase occurrence
    lower = text.lower()
    multi = {'kind of', 'sort of', 'i think', 'i feel', 'i guess',
             'you know', 'i mean', 'you see', 'pretty much'}
    for phrase in multi:
        count += lower.count(phrase)
    return round(count / total, 3)

_TRANSITIONS = {
    'however', 'furthermore', 'additionally', 'therefore', 'consequently',
    'subsequently', 'nevertheless', 'nonetheless', 'specifically',
    'particularly', 'notably', 'in addition', 'as a result', 'in order to',
    'such as', 'for example', 'in particular', 'as well as', 'in terms of',
    'with respect to', 'on the other hand', 'in contrast', 'that is',
    'for instance', 'to summarize', 'in conclusion', 'to illustrate',
    'as mentioned', 'it is important', 'it is worth', 'it should be noted',
}

def _transition_density(text: str) -> float:
    """Ratio of formal connector phrases to total words.
    High density = structured written text; low = natural speech.
    Very diagnostic for AI-vs-human spoken comparison.
    """
    lower = text.lower()
    total = max(1, len(text.split()))
    count = sum(1 for t in _TRANSITIONS if t in lower)
    return round(count / total, 4)

def _formality_score(text: str) -> float:
    """Composite formality (0-100): vocab + sentence length - filler noise."""
    score = (
        _vocabulary_level(text) * 0.5
        + min(_avg_sentence_len(text) * 2, 40)
        - _filler_ratio(text) * 200
    )
    return round(max(0.0, min(100.0, score)), 1)

def _count_syllables(word: str) -> int:
    """Simple vowel-group syllable counter. Good enough for FK/Fog on ASR text."""
    word = word.lower().strip(".,!?;:")
    if not word:
        return 0
    vowels = "aeiou"
    count = 0
    prev_vowel = False
    for ch in word:
        is_v = ch in vowels
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    # Silent 'e' at end
    if word.endswith('e') and count > 1:
        count -= 1
    return max(1, count)

def _flesch_kincaid(text: str) -> float:
    """FK Grade Level — higher = more complex written text.
    AI responses typically score 12-16; casual speech scores 6-9.
    Computed without any external library (syllable proxy).
    """
    sents = _sentences(text)
    words = _words(text)
    if not sents or not words:
        return 0.0
    avg_sent = len(words) / len(sents)
    avg_syl  = sum(_count_syllables(w) for w in words) / len(words)
    fk = 0.39 * avg_sent + 11.8 * avg_syl - 15.59
    return round(max(0.0, min(20.0, fk)), 2)

def _gunning_fog(text: str) -> float:
    """Gunning Fog index — penalises 3+ syllable words (polysyllabic).
    AI text is dense with polysyllabic technical terms.
    """
    sents = _sentences(text)
    words = _words(text)
    if not sents or not words:
        return 0.0
    avg_sent  = len(words) / len(sents)
    complex_r = sum(1 for w in words if _count_syllables(w) >= 3) / len(words)
    fog = 0.4 * (avg_sent + 100 * complex_r)
    return round(max(0.0, min(20.0, fog)), 2)

# Epistemic hedging phrases — AI overuses these to sound authoritative
_HEDGES = {
    'it is worth noting', 'it should be noted', 'it is important to note',
    'it is worth mentioning', 'one must consider', 'it is essential',
    'it is crucial', 'it is necessary', 'it is significant',
    'it can be argued', 'it is generally', 'it is widely',
    'studies suggest', 'research indicates', 'evidence shows',
    'in general', 'typically', 'commonly', 'usually', 'often',
    'it is often', 'it is commonly', 'it is typically',
}

def _hedging_density(text: str) -> float:
    """Density of epistemic hedging phrases.
    AI text overuses these to sound authoritative and thorough.
    Natural spoken answers almost never use them.
    """
    lower = text.lower()
    total = max(1, len(text.split()))
    count = sum(1 for h in _HEDGES if h in lower)
    return round(count / total, 4)

# Passive voice: "is/are/was/were/been/being + past participle"
# We detect 'be' forms followed by words ending in -ed/-en/-d
_BE_FORMS = re.compile(r'\b(is|are|was|were|been|being|be)\b', re.IGNORECASE)
_PAST_PART = re.compile(r'\b\w+(ed|en)\b', re.IGNORECASE)

def _passive_voice_ratio(text: str) -> float:
    """Ratio of passive constructions to total sentences.
    AI uses ~3x more passive voice than natural spoken answers.
    Pattern: 'be-form' within 3 words of a past-participle.
    """
    sents = _sentences(text)
    if not sents:
        return 0.0
    passive_count = 0
    for s in sents:
        words = s.split()
        be_positions   = [i for i, w in enumerate(words) if _BE_FORMS.match(w)]
        part_positions = [i for i, w in enumerate(words) if _PAST_PART.search(w)]
        for bp in be_positions:
            if any(abs(bp - pp) <= 3 for pp in part_positions):
                passive_count += 1
                break
    return round(passive_count / len(sents), 3)

def _sentence_burstiness(text: str) -> float:
    """Coefficient of variation (std/mean) of sentence lengths.
    Natural speech is bursty (CV ~ 0.4-0.7).
    AI text is unnaturally uniform (CV < 0.25).
    Higher = more natural variation; lower = suspicious uniformity.

    Note: utterances under 4 words (greetings, affirmations like 'Good morning.',
    'Sure.', 'Okay.') are excluded — they inflate variance artificially and are
    not real sentence-level style signals.
    """
    sents = _sentences(text)
    # Filter out very short utterances — they are greetings/affirmations, not sentences
    sents = [s for s in sents if len(s.split()) >= 4]
    if len(sents) < 2:
        return 0.5   # not enough real sentences — neutral
    lengths = [len(s.split()) for s in sents]
    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    std = variance ** 0.5
    return round(min(1.5, std / mean), 3)


# ── New signals (v3): catch lightly-edited AI answers ─────────────────────────

_AI_BOILERPLATE = [
    # AI canonical openers and phrases that persist even after light editing
    'it is worth noting', 'it should be noted', 'it is important to note',
    'one must consider', 'it is essential to', 'it is crucial to',
    'in order to ensure', 'this enables', 'this ensures', 'this allows',
    'can be leveraged', 'can be utilized', 'can be employed',
    'provides a robust', 'offers a comprehensive', 'facilitates the',
    'it is generally accepted', 'it is commonly', 'it is widely',
    'each of these', 'all of these', 'these factors',
    'as mentioned above', 'as discussed', 'in summary', 'to summarize',
    'in conclusion', 'to conclude', 'overall', 'ultimately',
    'at its core', 'at a high level', 'under the hood',
    'decomposes into', 'encapsulates', 'abstracts away',
]

def _ai_boilerplate_density(text: str) -> float:
    """Count of canonical AI phrases per 100 words.
    Even after manual editing, AI-generated text retains signature phrases.
    Genuine spoken answers almost never contain more than 1-2 of these.
    """
    lower = text.lower()
    words = max(1, len(text.split()))
    count = sum(1 for phrase in _AI_BOILERPLATE if phrase in lower)
    return round(count / words * 100, 3)   # per 100 words


def _personal_pronoun_ratio(text: str) -> float:
    """Ratio of first-person pronouns (I, my, me, I've, I'm) to total words.
    Genuine spoken answers are rich in personal reference.
    AI text avoids personal pronouns, making this a strong authenticity signal.
    """
    words = re.findall(r"\b\w+'?\w*\b", text.lower())
    total = max(1, len(words))
    personal = sum(1 for w in words if w in {
        'i', 'my', 'me', 'mine', "i've", "i'm", "i'd", "i'll",
        "ive", "im",  # ASR often strips apostrophes
        'myself', 'we', 'our', 'us',
    })
    return round(personal / total, 4)


def _sentence_start_variety(text: str) -> float:
    """Ratio of sentences starting with AI-typical openers.
    AI heavily favors: 'This', 'These', 'Each', 'Furthermore', 'Moreover'
    Genuine technical speech often starts with 'In', 'The', 'By' naturally —
    so we only flag the high-confidence AI-exclusive starters.
    Returns fraction of sentences with impersonal/structural starters.
    Higher = more AI-like sentence structure.
    """
    sents = _sentences(text)
    if not sents:
        return 0.0
    # Narrowed to phrases that are genuinely AI-exclusive in spoken answers.
    # Removed: 'in', 'the', 'a', 'an', 'by', 'with', 'through', 'using', 'since'
    # — these are extremely common in genuine technical speech.
    ai_starters = {'this', 'these', 'each', 'furthermore', 'moreover',
                   'additionally', 'consequently', 'nevertheless', 'thus',
                   'hence', 'subsequently', 'notably', 'importantly'}
    ai_count = sum(
        1 for s in sents
        if s.split() and s.split()[0].lower() in ai_starters
    )
    return round(ai_count / len(sents), 3)

def _normalize_transcript(text: str) -> str:
    """Strip transcription-source artifacts so Deepgram and Google Meet CC
    produce comparable input for the style comparator.

    Deepgram (personal round) adds:
      - Smart punctuation: periods, commas, apostrophes
      - Sentence capitalisation
      - Paragraph / line breaks

    Google Meet CC (technical round) gives:
      - Raw lowercase stream, no punctuation, no sentence breaks

    Without normalisation the comparator sees formatting differences as STYLE
    differences and flags genuine speakers as suspicious (score ~36).

    Strategy: strip all punctuation except hyphens, lowercase everything,
    collapse whitespace. Both texts are then in the same 'raw spoken words'
    format before feature extraction.
    """
    # Remove punctuation (keep hyphens for compound words like 'well-known')
    text = re.sub(r"[.,!?;:\"'()\[\]{}]", " ", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace / line breaks
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_profile(text: str) -> dict:

    """Build the full 14-parameter linguistic profile for a text sample."""
    return {
        # Core counts
        "word_count":             len(text.split()),
        "sentence_count":         max(1, len(_sentences(text))),
        # ── The 11 original parameters ────────────────────────────
        "vocabulary_level":       _vocabulary_level(text),       # 1
        "flesch_kincaid":         _flesch_kincaid(text),         # 2
        "formality_score":        _formality_score(text),        # 3
        "gunning_fog":            _gunning_fog(text),            # 4
        "hedging_density":        _hedging_density(text),        # 5
        "passive_voice_ratio":    _passive_voice_ratio(text),    # 6
        "grammar_score":          _grammar_score(text),          # 7
        "avg_sentence_len":       _avg_sentence_len(text),       # 8
        "filler_ratio":           _filler_ratio(text),           # 9
        "transition_density":     _transition_density(text),     # 10
        "sentence_burstiness":    _sentence_burstiness(text),    # 11
        # ── v3: subtle AI signals ─────────────────────────────────
        "ai_boilerplate":         _ai_boilerplate_density(text), # 12
        "personal_pronoun_ratio": _personal_pronoun_ratio(text), # 13
        "ai_sentence_starters":   _sentence_start_variety(text), # 14
        # ── Supporting ────────────────────────────────────────────
        "lexical_diversity":      _lexical_diversity(text),
    }


# ── Temporal drift (validated addition) ───────────────────────────────────────

def _temporal_drift(text: str) -> dict:
    """Split technical answer into 3 equal windows. Detect complexity spikes.

    A mid-answer or late-answer spike (>15 pts formality jump from window 1)
    is consistent with the candidate starting their own answer, then switching
    to reading an AI-generated response partway through.

    Returns:
        drift_score   : 0-100 (how much complexity accelerates)
        drift_window  : 1/2/3 — which window shows the highest jump
        window_scores : [early, mid, late] formality scores
        has_spike     : True when mid or late window is >15 pts above early
    """
    words = text.split()
    n = len(words)
    if n < 30:
        return {"drift_score": 0.0, "drift_window": 0,
                "window_scores": [], "has_spike": False}

    third = n // 3
    w1 = " ".join(words[:third])
    w2 = " ".join(words[third:2 * third])
    w3 = " ".join(words[2 * third:])

    scores = [_formality_score(w1), _formality_score(w2), _formality_score(w3)]

    jump_mid  = scores[1] - scores[0]
    jump_late = scores[2] - scores[0]
    max_jump  = max(jump_mid, jump_late)
    drift_window = 2 if jump_mid >= jump_late else 3

    drift_score = round(min(100.0, max(0.0, max_jump * 1.8)), 1)
    has_spike   = max_jump > 15

    return {
        "drift_score":   drift_score,
        "drift_window":  drift_window if has_spike else 0,
        "window_scores": [round(s, 1) for s in scores],
        "has_spike":     has_spike,
    }


# ── Shift helpers ──────────────────────────────────────────────────────────────

def _pct_diff(p_val: float, t_val: float) -> float:
    """Percentage difference normalised so small-valued metrics aren't washed out."""
    denom = max(abs(p_val), abs(t_val), 1.0)
    return abs(t_val - p_val) / denom * 100

def _transition_diff(p_val: float, t_val: float) -> float:
    """Transition density lives in [0, 0.1] — pct_diff denominator kills it.
    Use scaled absolute diff (×2000 maps a 0.05 diff → 100).
    """
    return min(100.0, abs(t_val - p_val) * 2000)

def _cosine_similarity(text_a: str, text_b: str) -> float:
    """Bag-of-words cosine similarity between personal and technical text."""
    try:
        wa = re.findall(r'\b[a-z]+\b', text_a.lower())
        wb = re.findall(r'\b[a-z]+\b', text_b.lower())
        if not wa or not wb:
            return 0.0
        vocab = set(wa) | set(wb)
        def tf(w):
            return {x: w.count(x) / len(w) for x in vocab}
        ta, tb = tf(wa), tf(wb)
        dot = sum(ta[x] * tb[x] for x in vocab)
        na  = math.sqrt(sum(v ** 2 for v in ta.values()))
        nb  = math.sqrt(sum(v ** 2 for v in tb.values()))
        return round(dot / (na * nb), 4) if na and nb else 0.0
    except Exception:
        return 0.0


# ── Main entry point ───────────────────────────────────────────────────────────

def calculate_style_shift(personal: str, technical: str) -> dict[str, Any]:
    """
    Compare communication style between personal and technical responses.
    Runs all 11 parameters defined in SACHHAIPROJECT.md.

    Weights (from spec):
      1. vocabulary_level    2.5  — word sophistication
      2. flesch_kincaid      2.2  — reading complexity (higher = AI-like)
      3. formality_score     2.0  — composite formality
      4. gunning_fog         1.8  — polysyllabic density
      5. hedging_density     1.8  — epistemic phrases (AI overuses)
      6. passive_voice_ratio 1.5  — AI uses 3x more passive voice
      7. grammar_score       1.2  — disfluency / fragment detector
      8. avg_sentence_len    1.2  — structural complexity
      9. filler_ratio        3.0  — spoken naturalness (inverted; drop = AI)
     10. transition_density  2.0  — formal connectors (special scale)
     11. sentence_burstiness 2.0  — CV of lengths (inverted; uniform = AI)
    """
    p = _build_profile(personal)
    t = _build_profile(technical)

    # ── 11-Parameter Weight Map ───────────────────────────────────────────────
    # (key, weight, inverted)
    # inverted=True means a DROP in the technical answer is suspicious
    WEIGHT_MAP = [
        ("vocabulary_level",    2.5, False),
        ("flesch_kincaid",      2.2, False),
        ("formality_score",     2.5, False),
        ("gunning_fog",         1.8, False),
        ("hedging_density",     1.8, False),
        ("passive_voice_ratio", 1.8, False),
        ("grammar_score",       1.2, False),
        ("avg_sentence_len",    1.5, False),
        ("filler_ratio",        3.5, True),
        ("sentence_burstiness", 2.0, True),
    ]

    total_weight  = sum(w for _, w, _ in WEIGHT_MAP)
    breakdown: dict[str, float] = {}
    weighted_shift = 0.0

    for key, weight, inverted in WEIGHT_MAP:
        # Density metrics (hedging, burstiness) need scaled diff
        if key == "hedging_density":
            diff = min(100.0, abs(t[key] - p[key]) * 5000)
        elif key == "sentence_burstiness":
            # Low burstiness in technical = AI uniformity; scale 0-0.5 range
            diff = min(100.0, max(0.0, (p[key] - t[key])) * 200)
        elif inverted:
            # Inverted: a DROP in technical is suspicious — amplify it
            raw = _pct_diff(p[key], t[key])
            if t[key] < p[key]:
                diff = min(100, raw * 1.5)   # suspicious drop
            else:
                diff = raw * 0.2             # increase is fine, barely score it
        else:
            # Non-inverted COMPLEXITY metrics: ONLY penalise when technical goes UP
            # A drop (technical being more casual) is normal — do not count it.
            if t[key] > p[key]:
                diff = _pct_diff(p[key], t[key])
            else:
                diff = 0.0   # technical is lower complexity — not suspicious
        breakdown[key] = round(diff, 1)
        weighted_shift += diff * weight

    # Transition density: special absolute-diff scale
    t_density_diff = _transition_diff(p["transition_density"], t["transition_density"])
    breakdown["transition_density"] = round(t_density_diff, 1)
    weighted_shift += t_density_diff * 2.0
    total_weight   += 2.0

    shift_score = round(min(100.0, weighted_shift / total_weight), 1)

    # ── Directional deltas ─────────────────────────────────────────────────────
    voc_jump    = t["vocabulary_level"]    - p["vocabulary_level"]
    fk_jump     = t["flesch_kincaid"]      - p["flesch_kincaid"]
    form_jump   = t["formality_score"]     - p["formality_score"]
    fog_jump    = t["gunning_fog"]         - p["gunning_fog"]
    hedge_jump  = t["hedging_density"]     - p["hedging_density"]
    passive_jump= t["passive_voice_ratio"] - p["passive_voice_ratio"]
    gram_jump   = t["grammar_score"]       - p["grammar_score"]
    sent_jump   = t["avg_sentence_len"]    - p["avg_sentence_len"]
    fill_drop   = p["filler_ratio"]        - t["filler_ratio"]
    burst_drop  = p["sentence_burstiness"] - t["sentence_burstiness"]  # drop = AI uniform

    # Word count ratio: no longer penalised — a long technical answer vs a short
    # personal intro is the expected format, not a suspicious signal.
    word_ratio = t["word_count"] / max(1, p["word_count"])

    # ── Single rushed sentence → multiple structured sentences ─────────────────
    if p["sentence_count"] == 1 and t["sentence_count"] >= 3:
        shift_score = min(100.0, shift_score + 12.0)

    # ── Sentence length ratio penalty ──────────────────────────────────────────
    sent_ratio = t["avg_sentence_len"] / max(p["avg_sentence_len"], 1.0)
    if sent_ratio > 2.5:  # was 1.8 — genuine techincal answers naturally use longer sentences
        shift_score = min(100.0, shift_score + 8.0)

    # ── Strong signal rules (11 parameters) ───────────────────────────────────
    strong_signals = [
        voc_jump    > 12,                                      # 1. vocab spike
        fk_jump     > 5.0,                                     # 2. FK grade jump
        form_jump   > 20,                                      # 3. formality jump (raised 15→20)
        fog_jump    > 5.0,                                     # 4. Fog jump
        hedge_jump  > 0.002,                                   # 5. hedging
        passive_jump > 0.20,                                   # 6. passive voice
        gram_jump   > 10,                                      # 7. grammar
        sent_jump   > 8,                                       # 8. sentences longer (raised 5→8)
        fill_drop   > 0.03 and p["filler_ratio"] > 0.01,       # 9. fillers vanished
        t_density_diff > 18,                                   # 10. transitions spiked
        burst_drop  > 0.18,                                    # 11. sentence uniformity (raised 0.10→0.18)
    ]
    strong_signal_count = sum(strong_signals)

    # ── AI-Combo Rule: definitive AI-assistance fingerprint ───────────────────
    # Path A: classic filler-drop + vocab spike
    ai_combo_a = (
        fill_drop  > 0.03 and p["filler_ratio"] > 0.01
        and voc_jump > 12
        and (t_density_diff > 18 or fk_jump > 5.0 or hedge_jump > 0.002)
    )
    # Path B: zero pronouns in technical + sentence uniformity (catches AI regardless of
    # whether baseline has fillers — robust to garbled/unpunctuated speech transcripts)
    ai_combo_b = (
        t["personal_pronoun_ratio"] == 0.0 and t["word_count"] > 40
        and burst_drop > 0.30
        and (t_density_diff > 10 or voc_jump > 8)
    )
    ai_combo = ai_combo_a or ai_combo_b
    if ai_combo:
        shift_score = max(shift_score, 75.0)   # raised 65→75: guaranteed VERY HIGH

    # ── Simple→complex penalty ─────────────────────────────────────────────────
    # Handles garbled run-on personal text: avg_sentence_len is artificially inflated
    # by the lack of punctuation, so we check vocabulary gap as the primary signal.
    # Only fire when technical text is GENUINELY more complex (not just personal was garbled).
    personal_simple   = p["vocabulary_level"] < 48  # relaxed: run-on text inflates sentence length
    technical_complex = t["vocabulary_level"] > 60 and t["sentence_burstiness"] < 0.20 and t["personal_pronoun_ratio"] < 0.02
    if personal_simple and technical_complex:
        shift_score = min(100.0, shift_score + 12.0)

    # ── Direct formality gap penalty: ONLY when technical is MORE formal than personal ──
    if form_jump > 0:   # only positive jumps (technical > personal) are suspicious
        if form_jump > 28:
            shift_score = min(100.0, shift_score + 15.0)
        elif form_jump > 15:
            shift_score = min(100.0, shift_score + 8.0)

    # ── Temporal drift (validated bonus layer) ─────────────────────────────────
    temporal = _temporal_drift(technical)
    drift_auth_penalty = 0.0
    if temporal["has_spike"]:
        # Amplified: was *0.25, now *0.40 for faster real-time response
        drift_shift_penalty = min(20.0, temporal["drift_score"] * 0.40)
        shift_score = min(100.0, shift_score + drift_shift_penalty)
        # Direct auth penalty — amplified so 1/3 AI window craters the score
        if temporal["drift_score"] >= 50:
            drift_auth_penalty = min(22.0, (temporal["drift_score"] - 50) * 0.40)
        elif temporal["drift_score"] >= 35:
            drift_auth_penalty = min(12.0, (temporal["drift_score"] - 35) * 0.35)
        elif temporal["drift_score"] >= 20:
            drift_auth_penalty = min(6.0,  (temporal["drift_score"] - 20) * 0.25)

    # ── Cosine similarity (very low overlap = completely different vocabulary) ──
    cosine_sim = _cosine_similarity(personal, technical)
    if cosine_sim < 0.05 and len(personal.split()) > 30 and len(technical.split()) > 30:
        shift_score = min(100.0, shift_score + 8.0)

    # ── v3: Subtle AI signals ──────────────────────────────────────────────────
    pronoun_drop = p["personal_pronoun_ratio"] - t["personal_pronoun_ratio"]

    # Personal pronoun DROP: genuine answers say "I" frequently; AI avoids it.
    # Guard: require personal baseline >= 50 words — short intros are naturally
    # I-heavy ('I am X, I do Y') so a drop in technical is expected format, not AI.
    if pronoun_drop > 0.03 and p["personal_pronoun_ratio"] > 0.02 and p["word_count"] >= 50:
        shift_score = min(100.0, shift_score + 8.0)

    # ABSOLUTE: zero pronouns in a 50+ word technical response.
    # Guard: require personal baseline >= 50 words for the same reason.
    if (t["personal_pronoun_ratio"] == 0.0 and t["word_count"] > 50
            and p["personal_pronoun_ratio"] > 0.02 and p["word_count"] >= 50):
        shift_score = min(100.0, shift_score + 15.0)

    # ABSOLUTE: extreme burstiness uniformity — only suspicious if personal was naturally bursty
    if (t["sentence_burstiness"] < 0.15 and t["sentence_count"] >= 3
            and p["sentence_burstiness"] > 0.35):
        shift_score = min(100.0, shift_score + 12.0)

    # AI boilerplate SPIKE: signature phrases survive manual editing
    boilerplate_spike = t["ai_boilerplate"] - p["ai_boilerplate"]
    if boilerplate_spike > 0.5:
        shift_score = min(100.0, shift_score + 8.0)
    if t["ai_boilerplate"] > 1.5:
        shift_score = min(100.0, shift_score + 6.0)

    # ── Absolute AI Signatures ─────────────────────────────────────────────────
    # Each check is RELATIVE to personal baseline to avoid penalising STT artifacts
    # that appear in BOTH texts (e.g., no fillers captured, long unpunctuated sentences).
    abs_penalty = 0.0
    # Fillers vanished: only suspicious if personal was CLEARLY conversational.
    # Raised threshold 0.02 -> 0.08: a 2-6% filler rate on a 30-word intro is
    # statistically noisy. Require 8%+ to call it a genuine conversational baseline.
    if t["filler_ratio"] < 0.005 and t["word_count"] > 30 and p["filler_ratio"] > 0.08:
        abs_penalty += 12.0
    # High formality: only suspicious if personal was noticeably less formal
    if t["formality_score"] > 75 and p["formality_score"] < 55:
        abs_penalty += 10.0
    # AI boilerplate: absolute — always suspicious regardless of baseline
    if t["ai_boilerplate"] >= 1.0:
        abs_penalty += 10.0
    # Long structured sentences: only suspicious if personal used shorter sentences
    if t["avg_sentence_len"] > 25 and p["avg_sentence_len"] < 18:
        abs_penalty += 10.0

    if abs_penalty > 0:
        shift_score = min(100.0, shift_score + abs_penalty)
        strong_signal_count += int(abs_penalty / 10)

    # AI sentence starter SPIKE
    starter_spike = t["ai_sentence_starters"] - p["ai_sentence_starters"]
    if starter_spike > 0.3 and t["ai_sentence_starters"] > 0.6:
        shift_score = min(100.0, shift_score + 7.0)

    # Extend strong_signal_count with v3 signals
    v3_signals = [
        pronoun_drop > 0.03 and p["personal_pronoun_ratio"] > 0.02,
        t["personal_pronoun_ratio"] == 0.0 and t["word_count"] > 50,  # absolute zero pronouns (50+ words)
        t["sentence_burstiness"] < 0.15 and t["sentence_count"] >= 3, # extreme uniformity
        boilerplate_spike > 0.5,
        starter_spike > 0.3 and t["ai_sentence_starters"] > 0.6,
    ]
    strong_signal_count += sum(v3_signals)

    # ── Short personal baseline damping ────────────────────────────────────────
    # Readability metrics (FK grade, Fog index, formality, sentence length) are
    # statistically unreliable on texts shorter than 50 words. A casual 35-word
    # intro will ALWAYS look simpler than an 80-word technical answer — that is
    # the interview FORMAT, not AI assistance.
    # Guard: only apply when no definitive AI fingerprint is detected.
    if (p["word_count"] < 25
            and not ai_combo
            and t["ai_boilerplate"] < 0.5
            and t["personal_pronoun_ratio"] > 0.01):   # tech has at least some pronouns
        _scale = max(0.35, p["word_count"] / 40.0)
        shift_score = shift_score * _scale

    # ── Short Answer / Pause Forgiveness (Smooth Scaling) ─────────────────────
    # Apply scaling FIRST so floor checks below cannot fight against the damper.
    # This prevents the 23-point cliff at 35 words that plagued live scoring.
    word_len = t["word_count"]
    if word_len < 30:
        if word_len < 15:
            scale = 0.20  # heavily damped — too few words to trust any metric
        else:
            # Scale smoothly from 0.20 at 15 words to 1.0 at 30 words
            scale = 0.20 + 0.80 * ((word_len - 15) / 15.0)

        shift_score = shift_score * scale

        # Demote strong signals proportionally when text is short
        if word_len < 30:
            strong_signal_count = 0
        elif word_len < 45:
            strong_signal_count = max(0, strong_signal_count - 2)

    # ── Floor checks — applied AFTER smooth scaling ────────────────────────────
    # Only activate when we have 60+ words so they never fight the damper.
    if strong_signal_count >= 3 and word_len >= 60:
        shift_score = max(shift_score, 52.0)   # was 45
    if strong_signal_count >= 4 and word_len >= 60:
        shift_score = max(shift_score, 65.0)   # NEW: 4 signals = SUSPICIOUS
    if strong_signal_count >= 5 and word_len >= 60:
        shift_score = max(shift_score, 75.0)   # was 65
    if strong_signal_count >= 6 and word_len >= 60:
        shift_score = max(shift_score, 82.0)   # was 72

    # ── Formal speaker fairness correction ───────────────────────────────────
    # When the candidate's personal baseline is already formal (formality > 40),
    # a formal technical answer is EXPECTED — not suspicious.
    # Only apply when no hard AI signals fired (strong_signal_count == 0),
    # preventing genuine formal speakers from being falsely flagged.
    if (p["formality_score"] > 40
            and strong_signal_count == 0
            and p["filler_ratio"] < 0.01     # no fillers in personal (consistently formal)
            and p["personal_pronoun_ratio"] > 0.04  # uses first person (genuinely them)
            and t["ai_boilerplate"] < 0.5):
        formal_correction = min(22.0, (p["formality_score"] - 40) * 0.55)
        shift_score = max(0.0, shift_score - formal_correction)

    shift_score = round(shift_score, 1)

    # ── 4-tier verdict ─────────────────────────────────────────────────────────
    if   shift_score > 60:  style_shift = "VERY HIGH"
    elif shift_score >= 40: style_shift = "HIGH"
    elif shift_score >= 20: style_shift = "MODERATE"
    else:                   style_shift = "LOW"

    # ── Authenticity score (proportional per tier) ─────────────────────────────
    # Floor of 15 for VERY HIGH prevents extreme scores (8.0) that feel arbitrary.
    # Real AI pastes still score 15-35; the relative ranking is preserved.
    # Steeper: VERY HIGH *0.8→*1.2 | HIGH *1.0→*1.5 | MODERATE *1.0→*1.3 | LOW *1.0→*1.2
    if   style_shift == "VERY HIGH": auth = round(max(15.0, 40.0 - (shift_score - 60) * 1.2), 1)
    elif style_shift == "HIGH":      auth = round(max(35.0, 60.0 - (shift_score - 40) * 1.5), 1)
    elif style_shift == "MODERATE":  auth = round(max(58.0, 80.0 - (shift_score - 20) * 1.3), 1)
    else:                            auth = round(max(78.0, 100.0 - shift_score * 1.2), 1)

    # LSDI drag: sustained high shift craters auth faster
    if shift_score >= 65:
        auth = round(max(10.0, auth - (shift_score - 65) * 0.35), 1)
    elif shift_score >= 50:
        auth = round(max(25.0, auth - (shift_score - 50) * 0.20), 1)

    # Apply drift auth penalty (mid-answer AI switch detection)
    if drift_auth_penalty > 0:
        auth = round(max(0.0, auth - drift_auth_penalty), 1)

    # ── Blending ML Classifier Score ───────────────────────────────────────────
    ml_probability = None
    if clf_model is not None:
        try:
            feats = extract_features(personal, technical)
            probs = clf_model.predict_proba(feats.reshape(1, -1))[0]
            ml_probability = float(probs[1]) # probability of AI-assisted (class 1)
            
            heuristic_score = auth
            blended = 0.5 * heuristic_score + 0.5 * (1.0 - ml_probability) * 100
            auth = round(blended, 1)
        except Exception as e:
            logger.warning("[style_comparator] ML prediction failed, falling back to heuristics: %s", e)


    # ── Confidence interval ─────────────────────────────────────────────────────
    short_text  = min(p["word_count"], t["word_count"]) < 80
    borderline  = 35 <= shift_score <= 50
    conf_margin = 8 if (short_text or borderline) else 4
    conf_level  = "Low" if short_text else ("Medium" if borderline else "High")
    conf_interval = {
        "low":      max(0.0,   round(shift_score - conf_margin, 1)),
        "high":     min(100.0, round(shift_score + conf_margin, 1)),
        "margin":   conf_margin,
        "reliable": not short_text,
        "level":    conf_level,
    }

    # ── Behavioral Observation Flags (enterprise-grade, non-accusatory) ────────
    flags: list[str] = []
    _seen_flags: set[str] = set()

    def _add_flag(msg: str) -> None:
        """Add deduplicated flag."""
        key = msg[:60]
        if key not in _seen_flags:
            _seen_flags.add(key)
            flags.append(msg)

    if t["word_count"] < 15:
        _add_flag("Response length insufficient for reliable behavioral analysis (< 15 words).")
    else:
        # High-confidence composite signal
        if ai_combo:
            _add_flag(
                "Multiple concurrent communication pattern shifts observed: natural speech markers "
                "decreased while structural sophistication and formal connector density increased simultaneously."
            )

        if fill_drop > 0.04 and p["filler_ratio"] > 0.01 and not ai_combo:
            _add_flag(
                f"Natural speech markers decreased notably "
                f"(baseline: {p['filler_ratio']:.1%} \u2192 technical: {t['filler_ratio']:.1%}). "
                "Communication cadence shifted significantly between rounds."
            )

        if voc_jump > 18:
            _add_flag(
                f"Vocabulary sophistication increased abruptly (+{voc_jump:.0f} pts above personal baseline). "
                "Lexical complexity deviated from the established communication profile."
            )

        if t["transition_density"] > 0.05 and p["transition_density"] < 0.02:
            _add_flag(
                "Formal transition density increased beyond established baseline. "
                "Response structure became more optimized and document-like."
            )

        if fk_jump > 7.0:
            _add_flag(
                f"Technical abstraction level rose significantly (+{fk_jump:.1f} grade levels). "
                "Response sophistication increased considerably above personal communication baseline."
            )

        if fog_jump > 7.0:
            _add_flag(
                f"Polysyllabic term density elevated (+{fog_jump:.1f} pts). "
                "Sentence complexity became unusually optimized relative to baseline."
            )

        if hedge_jump > 0.005:
            _add_flag(
                "Epistemic qualifier frequency increased noticeably. "
                "Response formulation became unusually structured and hedged."
            )

        if passive_jump > 0.35:
            _add_flag(
                f"Passive voice ratio increased by {passive_jump:.0%}. "
                "Sentence pacing became unusually formal and impersonal."
            )

        if burst_drop > 0.2 and t["sentence_burstiness"] < 0.25:
            _add_flag(
                f"Sentence length variance decreased (burstiness: {t['sentence_burstiness']:.2f}). "
                "Communication cadence became unusually uniform relative to natural baseline."
            )

        if temporal["has_spike"]:
            win_label = {2: "mid-response", 3: "toward the latter portion"}.get(
                temporal.get("drift_window", 2), "mid-response"
            )
            _add_flag(
                f"Linguistic complexity spike observed {win_label} "
                f"(+{temporal['drift_score']:.0f} pts). "
                "Mid-session style elevation may indicate a shift in response formulation approach."
            )

        if strong_signal_count >= 4 and not ai_combo:
            _add_flag(
                f"Behavioral consistency variance detected across {strong_signal_count} linguistic dimensions. "
                "Simultaneous multi-parameter shift warrants interviewer attention."
            )

        if shift_score > 60 and not flags:
            _add_flag(
                "Overall communication profile shifted substantially between personal and technical rounds. "
                "Behavioral consistency variance exceeds typical topic-adjustment norms."
            )

    # ── Authenticity tier (6-level professional scale) ─────────────────────────
    def _auth_tier(score: float) -> str:
        if score >= 90: return "Highly Authentic"
        if score >= 75: return "Mostly Natural"
        if score >= 60: return "Mild Assistance Indicators"
        if score >= 40: return "Moderate Authenticity Concerns"
        if score >= 20: return "Strong Assistance Indicators"
        return "Heavy External Assistance Likely"

    # ── Summary narrative (enterprise-grade, analytical) ──────────────────────
    tier_label = _auth_tier(auth)
    if ai_combo:
        summary = (
            f"Behavioral Analysis: {tier_label} (Consistency Score: {auth}/100, LSDI: {shift_score}/100). "
            "Multiple concurrent communication pattern shifts were observed between rounds. "
            "Natural speech markers decreased while structural sophistication and formal connector density "
            "increased simultaneously — a multi-signal behavioral variance pattern that warrants "
            "further interviewer assessment."
        )
    elif style_shift == "VERY HIGH":
        summary = (
            f"Behavioral Analysis: {tier_label} (Score: {auth}/100). "
            "Significant communication style differences were detected between the personal and technical rounds. "
            "Vocabulary sophistication, formality, and structural complexity elevated substantially. "
            "This warrants direct follow-up questioning to assess knowledge ownership."
        )
    elif style_shift == "HIGH":
        summary = (
            f"Behavioral Analysis: {tier_label} (Score: {auth}/100). "
            "Noticeable variations in linguistic sophistication were observed between rounds. "
            "While these patterns warrant attention, they do not conclusively indicate external assistance. "
            "A clarifying follow-up question is recommended."
        )
    elif style_shift == "MODERATE":
        summary = (
            f"Behavioral Analysis: {tier_label} (Score: {auth}/100). "
            "Some temporary increases in linguistic sophistication were observed between rounds. "
            "Overall behavioral consistency remained largely stable. "
            "Evidence is insufficient to conclude significant external assistance."
        )
    else:
        summary = (
            f"Behavioral Analysis: {tier_label} (Score: {auth}/100). "
            "Communication remained largely stable throughout the session. "
            "Behavioral consistency and semantic continuity were strong across both rounds. "
            "No significant authenticity concerns were detected."
        )

    logger.info(
        "[style_comparator] shift=%.1f (%s) | auth=%.1f | signals=%d | flags=%d",
        shift_score, style_shift, auth, strong_signal_count, len(flags),
    )

    # ── v2: Confidence, Verdict, Evidence, Follow-ups ─────────────────────────
    confidence = calculate_confidence(
        answer_word_count   = t["word_count"],
        personal_word_count = p["word_count"],
        signal_count        = strong_signal_count,
    )

    verdict_result = compute_verdict(
        lsdi_score        = shift_score,
        confidence_level  = confidence["level"],
        signal_count      = strong_signal_count,
        ai_combo          = ai_combo,
        answer_word_count = t["word_count"],
        temporal_has_spike= temporal["has_spike"],
        style_shift       = style_shift,
    )

    evidence = build_evidence_objects(
        fill_drop         = fill_drop,
        voc_jump          = voc_jump,
        fk_jump           = fk_jump,
        fog_jump          = fog_jump,
        hedge_jump        = hedge_jump,
        passive_jump      = passive_jump,
        burst_drop        = burst_drop,
        t_density_diff    = t_density_diff,
        temporal          = temporal,
        ai_combo          = ai_combo,
        p                 = p,
        t                 = t,
        answer_word_count = t["word_count"],
        confidence_level  = confidence["level"],
    )

    active_signals = get_active_signals(
        fill_drop         = fill_drop,
        voc_jump          = voc_jump,
        fk_jump           = fk_jump,
        fog_jump          = fog_jump,
        hedge_jump        = hedge_jump,
        passive_jump      = passive_jump,
        burst_drop        = burst_drop,
        t_density_diff    = t_density_diff,
        temporal_has_spike= temporal["has_spike"],
        ai_combo          = ai_combo,
        answer_word_count = t["word_count"],
    )

    followup_questions = generate_followups(
        active_signals = active_signals,
        max_questions  = 3,
        style_shift    = style_shift,
        transcript     = technical,
    )

    short_guardrail = get_short_answer_guardrail(t["word_count"])
    safe_interpretation = verdict_result["verdict_info"]["safe_wording"]
    primary_signal = active_signals[0] if active_signals else None
    supporting_signals = active_signals[1:4] if len(active_signals) > 1 else []

    return {
        # ── Core scores ───────────────────────────────────────────────────────
        "authenticity_score":  auth,
        "lsdi_score":          shift_score,
        "style_shift":         style_shift,
        "shift_score":         shift_score,
        # ── Tier label (6-level professional scale) ────────────────────────────
        "tier_label":          tier_label,
        # ── Confidence ────────────────────────────────────────────────────────
        "confidence_interval": conf_interval,
        "confidence_level":    conf_level,
        "confidence":          confidence,
        # ── Flags & summary ───────────────────────────────────────────────────
        "flags":               flags,
        "summary":             summary,
        # ── Verdict layer ─────────────────────────────────────────────────────
        "verdict":             verdict_result["verdict"],
        "verdict_info":        verdict_result["verdict_info"],
        "capped_reason":       verdict_result["capped_reason"],
        # ── v2: Evidence objects ──────────────────────────────────────────────
        "evidence":            evidence,
        "primary_signal":      primary_signal,
        "supporting_signals":  supporting_signals,
        "active_signals":      active_signals,
        # ── v2: Explainability ────────────────────────────────────────────────
        "safe_interpretation": safe_interpretation,
        "followup_questions":  followup_questions,
        "short_guardrail":     short_guardrail,
        "disclaimer":          DISCLAIMER,
        # ── Profiles & breakdown ─────────────────────────────────────────────
        "personal_profile":    p,
        "technical_profile":   t,
        "shift_breakdown":     breakdown,
        # ── Diagnostics ───────────────────────────────────────────────────────
        "strong_signal_count": strong_signal_count,
        "ai_combo":            ai_combo,
        "cosine_similarity":   cosine_sim,
        "ml_probability":      ml_probability,
        "temporal_drift":      temporal,
        "fairness_adjusted":   False,
        "_analysis_mode":      "ai_detection_v3",
    }
