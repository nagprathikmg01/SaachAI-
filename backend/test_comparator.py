import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from voice_module.style_comparator import calculate_style_shift

# Test 1: AI-assisted candidate
p1 = "Hi um I am Rahul you know I love coding like I did some projects basically web dev stuff I think its interesting I guess"
t1 = "Furthermore, in order to implement a scalable distributed system, one must consider eventual consistency. The CAP theorem necessitates careful trade-off analysis with respect to partition tolerance and high availability architectures."
r1 = calculate_style_shift(p1, t1)
print("=== Test 1: AI-assisted candidate ===")
print("Shift:", r1["shift_score"], "| Verdict:", r1["style_shift"], "| Auth:", r1["authenticity_score"])
print("Signals:", r1["strong_signal_count"])
for f in r1["flags"]:
    print(" -", f)

# Test 2: Genuine speaker
p2 = "I have been working on backend development for about three years now. I mainly use Python and FastAPI for building REST services. I enjoy solving problems and working in teams."
t2 = "I used Redis for caching and Postgres for the database. We had connection pooling issues at first but I fixed them by tuning the pool size. It took a bit of trial and error but the latency improved a lot."
r2 = calculate_style_shift(p2, t2)
print()
print("=== Test 2: Genuine speaker ===")
print("Shift:", r2["shift_score"], "| Verdict:", r2["style_shift"], "| Auth:", r2["authenticity_score"])
print("Signals:", r2["strong_signal_count"])
for f in r2["flags"]:
    print(" -", f)

print()
print("Analysis mode:", r1["_analysis_mode"])
print("Temporal drift Test1:", r1["temporal_drift"])
