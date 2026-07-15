"""diagnose.py — Senior QA diagnostic for SachhAI calibration pairs."""
import sys, json
sys.path.insert(0, '.')
from voice_module.style_comparator import calculate_style_shift, _build_profile

gen_p = (
    "So I am Nagasamukh Bis. I am currently studying at NMIT in ISC department. "
    "I am passionate about building projects and working publications and learning courses "
    "that are trending currently. I have a good academic background with 91 percent in CBSE, "
    "and I have a good scoring QC as well with 95 percentage. I have a steadily growing CDPA "
    "in current graduation as well. So my hobbies are playing cricket, roaming with friends, "
    "listening to music, etcetera. Thanks."
)
gen_t = (
    "So API means application programming interface where you can use another application "
    "in another software. Right? Assume there is a software which can transcribe the audio, "
    "and using that transcriber, I using that API, I can transcribe someone voice that which "
    "actually works like that software in my software. That is how API works."
)
ai_p = (
    "Hello. Myself, Nigam Alraj, and I am from NMIT. And I am currently studying in ISC NMIT, "
    "pass out year 2027. So my major goal is to become a successful engineer, getting, like, "
    "billions in package and joining Google, and I just want to add Google. Thank you."
)
ai_t = (
    "An API is application program interface. It is a system that allows different software "
    "applications to communicate and share the information with each other. It acts like the "
    "bridge of programs, helping them to send request and receive responses without knowing "
    "the internal working of the other systems. For example, whenever the app shows up, live "
    "updates goes. It helps API to collect data from the weather center API are widely used "
    "in mobile apps. Thank you."
)

KEYS = [
    'avg_sentence_len', 'sentence_burstiness', 'flesch_kincaid', 'gunning_fog',
    'formality_score', 'vocabulary_level', 'passive_voice_ratio', 'hedging_density',
    'filler_ratio', 'transition_density', 'grammar_score', 'ai_boilerplate',
    'personal_pronoun_ratio', 'ai_sentence_starters', 'lexical_diversity'
]

def show_profiles(name, p_text, t_text):
    p = _build_profile(p_text)
    t = _build_profile(t_text)
    print(f"\n{'='*60}")
    print(f"  PAIR: {name}")
    print(f"{'='*60}")
    print(f"  {'Feature':<25} {'Personal':>10} {'Technical':>10} {'Delta':>10}")
    print(f"  {'-'*57}")
    for k in KEYS:
        delta = t[k] - p[k]
        flag = " <-- SIGNAL" if abs(delta) > (0.3 if 'ratio' in k or 'density' in k or 'burstiness' in k else 3) else ""
        print(f"  {k:<25} {p[k]:>10.3f} {t[k]:>10.3f} {delta:>+10.3f}{flag}")
    r = calculate_style_shift(p_text, t_text)
    print(f"\n  shift_score        = {r['shift_score']}")
    print(f"  style_shift        = {r['style_shift']}")
    print(f"  authenticity_score = {r['authenticity_score']}")
    print(f"  ml_probability     = {r['ml_probability']}")
    print(f"  strong_signals     = {r['strong_signal_count']}")
    print(f"  breakdown:")
    for k, v in sorted(r['shift_breakdown'].items(), key=lambda x: -x[1]):
        bar = '#' * int(v / 5)
        print(f"    {k:<25} {v:>6.1f}  {bar}")
    print(f"  flags ({len(r['flags'])}):")
    for f in r['flags']:
        print(f"    - {f}")
    return r

r_gen = show_profiles("GENUINE (expect LOW/MODERATE)", gen_p, gen_t)
r_ai  = show_profiles("AI-ASSISTED (expect HIGH/VERY HIGH)", ai_p, ai_t)

print(f"\n{'='*60}")
print(f"  SEPARATION ANALYSIS")
print(f"{'='*60}")
print(f"  Genuine  score : {r_gen['shift_score']:>6.1f}")
print(f"  AI       score : {r_ai['shift_score']:>6.1f}")
print(f"  Gap            : {r_ai['shift_score'] - r_gen['shift_score']:>+6.1f}  (target: >35)")
print(f"  Verdict: {'GOOD' if r_ai['shift_score'] - r_gen['shift_score'] > 35 else 'NEEDS IMPROVEMENT'}")
