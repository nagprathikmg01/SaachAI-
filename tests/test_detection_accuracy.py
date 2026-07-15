import os
import sys
import joblib
import numpy as np
import pytest
from pathlib import Path

# Add backend to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from voice_module.style_comparator import calculate_style_shift, _build_profile, _transition_diff
from voice_module.confidence_engine import calculate_confidence, get_short_answer_guardrail
from voice_module.verdict_aggregator import compute_verdict

MODEL_PATH = Path(__file__).parent.parent / "backend" / "voice_module" / "model" / "sachhAI_classifier.pkl"

# ── Feature extraction helper (identical to train_model.py) ───────────────────
def extract_features(personal_text: str, technical_text: str) -> np.ndarray:
    p = _build_profile(personal_text)
    t = _build_profile(technical_text)

    # Deltas
    vocab_jump  = t["vocabulary_level"]    - p["vocabulary_level"]
    formal_jump = t["formality_score"]     - p["formality_score"]
    gram_jump   = t["grammar_score"]       - p["grammar_score"]
    sent_jump   = t["avg_sentence_len"]    - p["avg_sentence_len"]
    fill_drop   = p["filler_ratio"]        - t["filler_ratio"]
    div_diff    = abs(t["lexical_diversity"] - p["lexical_diversity"])
    trans_diff  = _transition_diff(p["transition_density"], t["transition_density"])

    # Ratios
    word_ratio  = t["word_count"] / max(1, p["word_count"])
    sent_ratio  = t["avg_sentence_len"] / max(p["avg_sentence_len"], 1.0)

    # Raw technical profile signals
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

# ── Ground-Truth Test Cases ───────────────────────────────────────────────────

CASES = {
    "A_HUMAN": {
        "name": "Genuine Human Answer (imperfect grammar)",
        "personal": (
            "Hi I'm Rahul, third year computer science from Pune. I like building apps and "
            "tinkering with stuff. I made a weather app, a notes app, and recently started "
            "working on a small e-commerce site with my college friends. I'm really into "
            "backend stuff, I like how data flows through a system. Outside coding I play badminton."
        ),
        "technical": (
            "So a linked list is basically a chain of nodes where each node holds some data "
            "and a pointer to the next node. The thing I find useful about it is you don't "
            "need to define the size upfront like you do with arrays. You can just keep "
            "adding nodes dynamically. The downside though is you lose random access so if I want "
            "the fifth element I have to start at the head and traverse one by one which "
            "is O of n. I actually implemented a simple one in my notes app."
        ),
        "expected_verdict": ["GENUINE", "LOW_RISK", "NEEDS_REVIEW"],
    },
    "B_AI_RAW": {
        "name": "Raw AI-Generated Answer (verbatim)",
        "personal": (
            "Hi I'm Rahul, third year computer science from Pune. I like building apps and "
            "tinkering with stuff. I made a weather app, a notes app, and recently started "
            "working on a small e-commerce site with my college friends. I'm really into "
            "backend stuff, I like how data flows through a system. Outside coding I play badminton."
        ),
        "technical": (
            "A Binary Search Tree is a hierarchical data structure wherein each node contains "
            "a key, with the invariant that all keys in the left subtree are strictly less than "
            "the root key, and all keys in the right subtree are strictly greater. This property "
            "enables O(log n) average-case time complexity for search, insertion, and deletion "
            "operations on balanced trees. However, degenerate cases such as sorted input cause "
            "the tree to reduce to a linear chain, degrading operations to O(n)."
        ),
        "expected_verdict": ["SUSPICIOUS", "HIGH_RISK"],
    },
    "C_AI_PARAPHRASED": {
        "name": "AI-Generated but Lightly Paraphrased Answer",
        "personal": (
            "Hi I'm Rahul, third year computer science from Pune. I like building apps and "
            "tinkering with stuff. I made a weather app, a notes app, and recently started "
            "working on a small e-commerce site with my college friends. I'm really into "
            "backend stuff, I like how data flows through a system. Outside coding I play badminton."
        ),
        "technical": (
            "Um, so a Binary Search Tree is basically a hierarchical structure where every node "
            "has a key. The rule is that keys in the left subtree are always smaller than the root, "
            "and keys in the right are larger. This allows O(log n) complexity on average for operations. "
            "But, like, in degenerate cases, it can degrade to a linear chain, meaning O(n) worst-case."
        ),
        "expected_verdict": ["SUSPICIOUS", "NEEDS_REVIEW", "HIGH_RISK"],
    },
    "D_SHORT": {
        "name": "Very Short Answer (<30 words)",
        "personal": (
            "Hi I'm Rahul, third year computer science from Pune. I like building apps and "
            "tinkering with stuff. I made a weather app, a notes app, and recently started "
            "working on a small e-commerce site with my college friends. I'm really into "
            "backend stuff, I like how data flows through a system. Outside coding I play badminton."
        ),
        "technical": (
            "A Binary Search Tree is a tree where left is smaller and right is larger."
        ),
        "expected_verdict": ["GENUINE"], # Should remain Genuine since no style deviation, but with low confidence
    }
}

# ── Test Suite ────────────────────────────────────────────────────────────────

def test_accuracy_scenarios():
    results = []
    
    # Load model
    clf = None
    if MODEL_PATH.exists():
        clf = joblib.load(MODEL_PATH)
    else:
        print("\n[Warning] trained ML classifier .pkl file not found. Running in heuristic mode only.")

    for case_id, case in CASES.items():
        personal = case["personal"]
        technical = case["technical"]
        
        # 1. Heuristic engine execution
        h_res = calculate_style_shift(personal, technical)
        
        # Profiles
        p_prof = h_res["personal_profile"]
        t_prof = h_res["technical_profile"]
        
        # 2. ML model prediction
        ml_label = "N/A"
        ml_prob = "N/A"
        if clf is not None:
            features = extract_features(personal, technical).reshape(1, -1)
            pred = clf.predict(features)[0]
            probs = clf.predict_proba(features)[0]
            ml_label = "AI-Assisted" if pred == 1 else "Genuine"
            ml_prob = f"{probs[pred]*100:.1f}%"

        # 3. Confidence engine cross-check
        conf = calculate_confidence(
            answer_word_count=t_prof["word_count"],
            personal_word_count=p_prof["word_count"],
            signal_count=h_res["strong_signal_count"],
            is_streaming_partial=False
        )
        
        # 4. Verdict aggregator cross-check
        verdict_res = compute_verdict(
            lsdi_score=h_res["shift_score"],
            confidence_level=conf["level"],
            signal_count=h_res["strong_signal_count"],
            ai_combo=h_res.get("ai_combo", False),
            answer_word_count=t_prof["word_count"],
            temporal_has_spike=h_res.get("temporal_drift", {}).get("has_spike", False),
            style_shift=h_res["style_shift"]
        )

        results.append({
            "id": case_id,
            "name": case["name"],
            "words": t_prof["word_count"],
            "heuristic_score": h_res["shift_score"],
            "authenticity_score": h_res["authenticity_score"],
            "style_shift": h_res["style_shift"],
            "ml_verdict": ml_label,
            "ml_conf": ml_prob,
            "final_verdict": verdict_res["verdict"],
            "confidence": conf["label"],
            "capped": verdict_res["capped_reason"] or "No",
        })

    # Assertions
    for res in results:
        case = CASES[res["id"]]
        # Ensure Case D (Short) has low confidence indicators
        if res["id"] == "D_SHORT":
            assert res["final_verdict"] == "GENUINE"
            assert "Low" in res["confidence"]
        
        # Assertions on expected verdict bounds
        assert res["final_verdict"] in case["expected_verdict"], f"Case {res['id']}: Verdict {res['final_verdict']} not in expected bounds {case['expected_verdict']}!"

    # Compile results table to print at the end of the test run
    print("\n\n==========================================================================================")
    print("DETECTION ACCURACY TEST RESULTS TABLE")
    print("==========================================================================================")
    print(f"{'Case ID':<10} | {'Heuristic':<9} | {'Auth':<4} | {'Verdict':<15} | {'ML Label':<12} | {'ML Conf':<7} | {'Capped':<15}")
    print("-" * 90)
    for res in results:
        print(f"{res['id']:<10} | {res['heuristic_score']:>9.1f} | {res['authenticity_score']:>4.1f} | {res['final_verdict']:<15} | {res['ml_verdict']:<12} | {res['ml_conf']:<7} | {res['capped']:<15}")
    print("==========================================================================================\n")
