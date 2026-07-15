import sys
sys.path.insert(0, r'e:\AntiGravity\Interview-new\backend')
from voice_module.style_comparator import calculate_style_shift, _build_profile

personal = (
    "okay okay I am nagasanam create from nmit college Bengaluru I am currently studying "
    "in 3rd year at IRD department I am actually more interested in working on some project "
    "break interview generation resume preparation and asking person regarding it I am totally "
    "focus done MS related careers in my first year and have a set of obviously playing with "
    "friends cricket roaming with my friends talking to them watching movies"
)

technical = (
    "An API Application Programming Interface is a set of rules that allows different software "
    "applications to communicate and share data with each other It acts like a bridge between two "
    "systems enabling one application to request services or information from another without knowing "
    "how the internal system works For example when a weather app shows live weather updates it uses "
    "an API to collect data from a weather server APIs are widely used in websites mobile apps payment "
    "systems social media platforms and AI tools to improve functionality automation and integration between services"
)

p = _build_profile(personal)
t = _build_profile(technical)

print("=== PERSONAL PROFILE ===")
print(f"  words={p['word_count']}, sentences={p['sentence_count']}")
print(f"  avg_sentence_len={p['avg_sentence_len']}")
print(f"  filler_ratio={p['filler_ratio']}")
print(f"  vocab_level={p['vocabulary_level']}")
print(f"  formality={p['formality_score']}")
print(f"  transition_density={p['transition_density']}")

print("\n=== TECHNICAL PROFILE ===")
print(f"  words={t['word_count']}, sentences={t['sentence_count']}")
print(f"  avg_sentence_len={t['avg_sentence_len']}")
print(f"  filler_ratio={t['filler_ratio']}")
print(f"  vocab_level={t['vocabulary_level']}")
print(f"  formality={t['formality_score']}")
print(f"  transition_density={t['transition_density']}")

print("\n=== DELTAS ===")
print(f"  filler DROP   = {p['filler_ratio'] - t['filler_ratio']:+.3f}")
print(f"  vocab JUMP    = {t['vocabulary_level'] - p['vocabulary_level']:+.1f}")
print(f"  formality     = {t['formality_score'] - p['formality_score']:+.1f}")
print(f"  sent_len      = {t['avg_sentence_len'] - p['avg_sentence_len']:+.1f}")
print(f"  transition    = {t['transition_density'] - p['transition_density']:+.4f}")

result = calculate_style_shift(personal, technical)
print("\n=== RESULT ===")
print(f"  LSDI: {result['lsdi_score']} | Style shift: {result['style_shift']}")
print(f"  Auth score: {result['authenticity_score']} | AI combo: {result['ai_combo']}")
print(f"  Strong signals: {result['strong_signal_count']}/6")
print(f"  Flags ({len(result['flags'])}):")
for f in result['flags']:
    print(f"    - {f[:100]}")
print(f"\n  Summary: {result['summary'][:150]}")
