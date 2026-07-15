"""
followup_generator.py - Generates follow-up interview questions based on risk signals.

Questions are designed to be paraphrase-resistant:
- require spontaneous reasoning
- require personal experience references
- require simplification (hard to fake if AI-generated)
- require specific implementation details

The interviewer can ask these live to validate the candidate's authenticity.
"""

import re
from typing import Optional

# Tech domain keyword → follow-up question templates
_TECH_TOPICS = {
    r"\bkubernetes\w*|\bk8s\w*":    "Can you walk me through how you managed deployments and scaling in Kubernetes?",
    r"\bdocker\w*|\bcontainer\w*":  "What challenges did you face with containerization and how did you resolve them?",
    r"\bmicroservice\w*":         "How did you handle inter-service communication and fault tolerance in your microservices architecture?",
    r"\bapi\w*|\brest\w*|\bgraphql\w*": "Can you describe the API design decisions you made and why?",
    r"\bml\b|\bmachine learning\w*|\bmodel\w*": "How did you evaluate and iterate on your model's performance in production?",
    r"\bsql\w*|\bdatabase\w*|\bpostgres\w*|\bmysql\w*": "How did you handle database optimization and query performance at scale?",
    r"\breact\w*|\bvue\w*|\bangular\w*|\bfrontend\w*": "Can you describe a complex UI challenge you solved and your approach?",
    r"\bpython\w*|\bfastapi\w*|\bdjango\w*|\bflask\w*": "How did you manage async operations and performance bottlenecks in Python?",
    r"\baws\b|\bazure\w*|\bgcp\b|\bcloud\w*": "How did you approach infrastructure cost optimization in the cloud?",
    r"\bci[/ ]?cd\b|\bpipeline\w*|\bdevops\w*": "Can you walk me through your CI/CD pipeline and how you handled rollback strategies?",
    r"\bsecurity\w*|\bauth\w*|\boauth\w*": "How did you implement authentication and handle security vulnerabilities?",
    r"\bperformance\w*|\boptimiz\w*|\bcaching\w*": "What profiling tools did you use and what were your biggest performance gains?",
    r"\btest\w*|\bunit test\w*|\bintegration\w*": "How did you ensure test coverage and handle edge cases in your testing strategy?",
    r"\bdata struct\w*|\balgorithm\w*|\bbig.?o\w*": "Can you explain the time and space complexity trade-offs you made in that solution?",
    r"\bsystem design\w*|\barchitect\w*|\bscal\w*": "How would you redesign that system today knowing what you know now?",
}

# ── Follow-up question bank (signal -> questions) ─────────────────────────────

_FOLLOWUP_BANK: dict[str, list[str]] = {
    "ai_combo": [
        "Can you explain that in your own words - as if you were telling a friend?",
        "Where specifically did you use that in one of your projects?",
        "What tradeoff did you face when implementing this?",
        "What bug or problem did you hit while working on this?",
        "If you had to redo that, what would you do differently?",
    ],
    "filler_drop": [
        "Walk me through your thinking process more casually.",
        "Explain that again but imagine you are texting a friend - how would you say it?",
        "What was the first thing that came to your mind when I asked that?",
    ],
    "vocab_spike": [
        "Can you simplify that explanation for someone without a technical background?",
        "Explain that concept without using any of those technical terms.",
        "How would you describe this to a junior engineer on their first week?",
    ],
    "transition_density": [
        "Can you say that again without a formal structure - just talk naturally.",
        "What is the most important part of what you just said?",
        "Give me a one-sentence summary in your own words.",
    ],
    "formality_spike": [
        "Describe that same concept but more conversationally.",
        "How would you explain this if we were in a coffee chat?",
    ],
    "temporal_drift": [
        "What was your initial thought when I asked you that question?",
        "You started one way and finished differently - can you walk me through that shift?",
        "Finish the thought you started at the beginning of your answer.",
    ],
    "passive_voice": [
        "What did you personally do in that situation?",
        "Walk me through what you specifically implemented - not the team, just you.",
        "What decision did you make and why?",
    ],
    "fk_jump": [
        "Can you re-explain that in simpler language?",
        "What does that actually mean in plain terms?",
    ],
    "hedging_density": [
        "You said 'it is worth noting' - worth noting to whom, and why?",
        "Can you be more direct? What is your actual opinion on this?",
        "Speak from your own experience, not in general terms.",
    ],
    "generic_answer": [
        "Give me a specific example from something you personally built.",
        "Which project did you use this in, and what was the outcome?",
        "What would you do differently next time?",
        "What was the hardest part of actually implementing this?",
    ],
    "short_answer": [
        "Can you tell me more about that?",
        "Expand on that - what does that look like in practice?",
        "Give me an example from your experience.",
    ],
    "formality_only": [
        "That sounds quite formal - how would you explain it more naturally?",
        "Tell me how you actually think about this problem.",
    ],
}

# Default questions when no specific signal is matched
_DEFAULT_FOLLOWUPS = [
    "Can you walk me through a specific example from your own work?",
    "What was the most challenging part of that?",
    "How would you explain this to someone who has never heard of it?",
]


def generate_followups(
    active_signals: list[str],
    max_questions: int = 3,
    style_shift: str = "LOW",
    transcript: Optional[str] = None,
) -> list[str]:
    """
    Given a list of active signal types, returns the most relevant
    follow-up questions to ask the candidate.

    active_signals: e.g. ["ai_combo", "filler_drop", "vocab_spike"]
    max_questions: how many to return (default 3)
    style_shift: overall verdict tier for ordering priority
    transcript: optional technical transcript to extract live technical domain questions from
    """
    seen: set[str] = set()
    selected: list[str] = []

    # 1. Check technical transcript if provided, prioritizing up to 2 domain follow-up questions
    if transcript:
        lower_transcript = transcript.lower()
        tech_questions = []
        for pattern, question in _TECH_TOPICS.items():
            if re.search(pattern, lower_transcript, re.I):
                if question not in seen:
                    seen.add(question)
                    tech_questions.append(question)
        
        # Take up to 2 technical questions so we don't crowd out the behavioral risk probes
        selected.extend(tech_questions[:2])

    # Priority order — most definitive signals first
    priority_order = [
        "ai_combo", "temporal_drift", "vocab_spike",
        "filler_drop", "passive_voice", "transition_density",
        "formality_spike", "fk_jump", "hedging_density",
        "generic_answer", "short_answer", "formality_only",
    ]

    # Process in priority order, only for active signals
    for signal in priority_order:
        if signal not in active_signals:
            continue
        questions = _FOLLOWUP_BANK.get(signal, [])
        for q in questions:
            if q not in seen and len(selected) < max_questions:
                seen.add(q)
                selected.append(q)
        if len(selected) >= max_questions:
            break

    # If we still don't have enough, fill from defaults
    for q in _DEFAULT_FOLLOWUPS:
        if q not in seen and len(selected) < max_questions:
            seen.add(q)
            selected.append(q)

    return selected


def get_active_signals(
    fill_drop: float,
    voc_jump: float,
    fk_jump: float,
    fog_jump: float,
    hedge_jump: float,
    passive_jump: float,
    burst_drop: float,
    t_density_diff: float,
    temporal_has_spike: bool,
    ai_combo: bool,
    answer_word_count: int,
) -> list[str]:
    """
    Returns a list of active signal type strings based on metric values.
    Used to drive followup question selection.
    """
    signals: list[str] = []

    if ai_combo:
        signals.append("ai_combo")
    if fill_drop > 0.03:
        signals.append("filler_drop")
    if voc_jump > 12:
        signals.append("vocab_spike")
    if fk_jump > 2.0:
        signals.append("fk_jump")
    if fog_jump > 2.0:
        signals.append("fog_jump")
    if hedge_jump > 0.003:
        signals.append("hedging_density")
    if passive_jump > 0.15:
        signals.append("passive_voice")
    if burst_drop > 0.15:
        signals.append("temporal_drift")
    if t_density_diff > 20:
        signals.append("transition_density")
    if temporal_has_spike:
        signals.append("temporal_drift")
    if answer_word_count < 30:
        signals.append("short_answer")

    return list(dict.fromkeys(signals))  # deduplicate preserving order
