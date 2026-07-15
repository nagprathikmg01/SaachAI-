import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
import json
import time

BASE = "http://127.0.0.1:8000/voice"
HEADERS = {"Content-Type": "application/json", "X-Username": "trial_user", "X-Role": "hr"}

print("===================================================================")
print(">>> SACHHAI POST-SESSION ANALYSIS TRIAL")
print("===================================================================\n")

# A candidate that suddenly switches to robotic, dense AI text
payload = {
    "candidate_id": f"trial_candidate_{int(time.time())}",
    "personal": "Hi, I'm Alex. I just graduated last year and I really like building web apps. I'm a bit nervous but excited. In my free time I play basketball.",
    "technical": "A distributed database management system is a collection of logically interrelated databases distributed over a computer network. The fundamental challenge is maintaining ACID properties across geographically dispersed nodes while optimizing for availability and partition tolerance. Techniques such as two-phase commit protocol and Paxos-based consensus algorithms ensure transactional consistency."
}

print(f"[PERSONAL ROUND] (Captured in first 30 seconds):")
print(f"\"{payload['personal']}\"\n")

print(f"[TECHNICAL ROUND] (Real-time capture):")
print(f"\"{payload['technical']}\"\n")

print("... Simulating clicking 'Stop & Analyse' ...\n")

resp = requests.post(f"{BASE}/text-compare", headers=HEADERS, json=payload)
data = resp.json().get("analysis", {})

print("[FINAL ANALYSIS REPORT]")
print("-" * 50)
print(f"Verdict            : {data.get('verdict')}")
print(f"Tier               : {data.get('tier_label')}")
print(f"Authenticity Score : {data.get('authenticity_score')}/100")
print(f"Style Shift Level  : {data.get('style_shift')}")
print(f"Plagiarism Risk    : {data.get('inline_plagiarism_risk')}%")
print("-" * 50)

print("\n[FLAGS TRIGGERED]:")
for flag in data.get('flags', []):
    print(f"  - {flag}")

print("\n[TEMPORAL DRIFT DATA]:")
td = data.get("temporal_drift", {})
if td.get("has_spike"):
    print(f"  -> Significant complexity spike detected: +{td.get('drift_score', 0):.1f} points!")
else:
    print("  -> Communication remained stable.")

print("\n[AI/ML Breakdown (Raw signals)]:")
print(f"  - Vocabulary Level Diff : +{data.get('technical_profile', {}).get('vocabulary_level', 0) - data.get('personal_profile', {}).get('vocabulary_level', 0):.1f}")
print(f"  - Formal Density Diff   : +{data.get('technical_profile', {}).get('formality_score', 0) - data.get('personal_profile', {}).get('formality_score', 0):.1f}")
print(f"  - Filler Word Drop      : {data.get('personal_profile', {}).get('filler_ratio', 0) - data.get('technical_profile', {}).get('filler_ratio', 0):.3f}")

print("\n===================================================================")
