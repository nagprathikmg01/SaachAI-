"""
fetch_and_train.py — Download ALL HC3 splits + retrain with expanded features.

Downloads: open_qa, finance, medicine, reddit_eli5, wiki_csai (~5 splits)
Total expected: ~3,500-5,000 labeled pairs
New feature vector: 29 features (up from 18)

Run:
    cd backend
    venv\\Scripts\\python fetch_and_train.py
"""

import json, sys, warnings, math
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import httpx
import numpy as np

MODEL_DIR = Path(__file__).parent / "voice_module" / "model"
MODEL_DIR.mkdir(exist_ok=True)

HC3_SPLITS = [
    "open_qa", "finance", "medicine", "reddit_eli5", "wiki_csai"
]
HC3_BASE = "https://huggingface.co/datasets/Hello-SimpleAI/HC3/resolve/main/{split}.jsonl"

# ── Download all splits ───────────────────────────────────────────────────────
def download_split(split: str) -> Path:
    cache = MODEL_DIR / f"hc3_{split}.jsonl"
    if cache.exists():
        print(f"  [{split}] cached OK")
        return cache
    url = HC3_BASE.format(split=split)
    print(f"  [{split}] downloading from HuggingFace...")
    try:
        with httpx.stream("GET", url, timeout=90, follow_redirects=True) as r:
            r.raise_for_status()
            with open(cache, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)
        print(f"  [{split}] saved ({cache.stat().st_size//1024} KB)")
        return cache
    except Exception as e:
        print(f"  [{split}] FAILED: {e}")
        return None

print("=== Downloading HC3 dataset splits ===")
files = []
for split in HC3_SPLITS:
    f = download_split(split)
    if f: files.append((split, f))

# ── Parse pairs ───────────────────────────────────────────────────────────────
def parse_hc3_file(path: Path, max_per_label: int = 600):
    genuine, ai_pairs = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                q   = (row.get("question") or "").strip()
                humans  = row.get("human_answers") or []
                chatgpt = row.get("chatgpt_answers") or []
                for h in humans[:1]:
                    if len(h.split()) >= 25:
                        genuine.append((q, h, 0))
                        if len(genuine) >= max_per_label: break
                for c in chatgpt[:1]:
                    if len(c.split()) >= 25:
                        ai_pairs.append((q, c, 1))
                        if len(ai_pairs) >= max_per_label: break
            except Exception:
                pass
    return genuine[:max_per_label], ai_pairs[:max_per_label]

print("\n=== Parsing pairs ===")
all_pairs = []
for split, path in files:
    g, a = parse_hc3_file(path)
    all_pairs.extend(g)
    all_pairs.extend(a)
    print(f"  [{split}] {len(g)} genuine + {len(a)} AI = {len(g)+len(a)}")

# Add synthetic baseline pairs (reliable anchor)
SYNTHETIC = [
    ("Hi I'm Ravi. I studied CS at VTU. I like building mobile apps and have done some internships.",
     "In my internship I built a React Native app that fetched data from a REST API. I used Redux for state management.", 0),
    ("Hey I'm Priya. I mostly work with Python and have done a few ML projects.",
     "My ML project used scikit-learn to classify spam emails. Random forest gave about 92% accuracy.", 0),
    ("I'm James. I like backend stuff and databases.",
     "I built a REST API using Node.js and Express with PostgreSQL. I handled user authentication.", 0),
    ("I'm Chen. I work with Java mostly. Been coding for three years.",
     "I built a Spring Boot service with REST endpoints. I used JPA for database access and Redis for caching.", 0),
    ("Hi I'm Aryan, um I studied CS and I like coding and stuff.",
     "The solution leverages microservices architecture with containerized deployment via Docker and Kubernetes. The system incorporates sophisticated load balancing and horizontal scaling for optimal resource utilization.", 1),
    ("I'm Meera. I've done some Python projects, basically web apps.",
     "The application implements a robust Model-View-Controller paradigm with comprehensive dependency injection. The codebase adheres to SOLID principles incorporating Repository and Factory patterns.", 1),
    ("Hey I'm Jake. I know JavaScript kind of well. Learning for two years.",
     "The frontend employs unidirectional data flow via Redux Toolkit. React Query handles sophisticated server-state synchronization ensuring optimal cache invalidation.", 1),
    ("I'm Sunita. I work with SQL and backend stuff mostly.",
     "The database implements comprehensive normalization through third normal form compliance with carefully designed constraint mechanisms and advanced indexing strategies.", 1),
]
all_pairs.extend(SYNTHETIC)

print(f"\nTotal: {len(all_pairs)} pairs "
      f"({sum(1 for _,_,l in all_pairs if l==0)} genuine, "
      f"{sum(1 for _,_,l in all_pairs if l==1)} AI-assisted)")

# ── Feature extraction (matches new style_comparator.py) ─────────────────────
from voice_module.style_comparator import (
    _build_profile, _transition_diff, _cosine_similarity
)

def extract_features(personal: str, technical: str) -> np.ndarray:
    p = _build_profile(personal)
    t = _build_profile(technical)

    voc_jump   = t["vocabulary_level"]    - p["vocabulary_level"]
    form_jump  = t["formality_score"]     - p["formality_score"]
    gram_jump  = t["grammar_score"]       - p["grammar_score"]
    sent_jump  = t["avg_sentence_len"]    - p["avg_sentence_len"]
    fill_drop  = p["filler_ratio"]        - t["filler_ratio"]
    mattr_diff = abs(t["mattr"]           - p["mattr"])
    trans_diff = _transition_diff(p["transition_density"], t["transition_density"])
    word_ratio = t["word_count"] / max(1, p["word_count"])
    sent_ratio = t["avg_sentence_len"] / max(p["avg_sentence_len"], 1.0)
    fk_jump    = t["flesch_kincaid"]      - p["flesch_kincaid"]
    fog_jump   = t["gunning_fog"]         - p["gunning_fog"]
    hedge_jmp  = t["hedging_density"]     - p["hedging_density"]
    passv_jmp  = t["passive_voice_ratio"] - p["passive_voice_ratio"]
    burst_drop = p["sentence_burstiness"] - t["sentence_burstiness"]
    ivar_diff  = t["intra_style_var"]     - p["intra_style_var"]

    strong = sum([
        voc_jump > 10, form_jump > 12, gram_jump > 10, sent_jump > 5,
        fk_jump > 2, fog_jump > 2, hedge_jmp > 0.15, passv_jmp > 0.15,
        burst_drop > 0.15,
        fill_drop > 0.02 and p["filler_ratio"] > 0.01,
        trans_diff > 25,
    ])

    return np.array([
        # Deltas (15)
        voc_jump, form_jump, gram_jump, sent_jump, fill_drop,
        mattr_diff, trans_diff, word_ratio, sent_ratio,
        fk_jump, fog_jump, hedge_jmp, passv_jmp, burst_drop, ivar_diff,
        # Raw technical profile (9)
        t["vocabulary_level"], t["formality_score"], t["grammar_score"],
        t["avg_sentence_len"], t["transition_density"], t["filler_ratio"],
        t["flesch_kincaid"], t["gunning_fog"], t["sentence_burstiness"],
        # Raw personal profile (4)
        p["filler_ratio"], p["vocabulary_level"],
        p["sentence_burstiness"], p["flesch_kincaid"],
        # Composite (1)
        float(strong),
    ], dtype=np.float32)

FEATURE_NAMES = [
    "voc_jump","form_jump","gram_jump","sent_jump","fill_drop",
    "mattr_diff","trans_diff","word_ratio","sent_ratio",
    "fk_jump","fog_jump","hedge_jmp","passv_jmp","burst_drop","ivar_diff",
    "t_vocab","t_formal","t_gram","t_sent","t_trans","t_fill",
    "t_fk","t_fog","t_burst",
    "p_fill","p_vocab","p_burst","p_fk",
    "strong_count",
]

print("\nExtracting features...")
X, y = [], []
skipped = 0
for personal, technical, label in all_pairs:
    try:
        X.append(extract_features(personal, technical))
        y.append(label)
    except Exception:
        skipped += 1

X = np.array(X); y = np.array(y)
print(f"Feature matrix: {X.shape}  skipped={skipped}")

# ── Train ─────────────────────────────────────────────────────────────────────
from sklearn.ensemble import (
    RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, classification_report
import joblib

lr  = LogisticRegression(C=0.8, max_iter=1000, class_weight='balanced', random_state=42)
rf  = RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=3,
                              class_weight='balanced', random_state=42)
gb  = GradientBoostingClassifier(n_estimators=200, learning_rate=0.07,
                                  max_depth=5, subsample=0.85, random_state=42)

pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('clf', VotingClassifier(
        estimators=[('lr', lr), ('rf', rf), ('gb', gb)],
        voting='soft', weights=[1, 2, 3],
    )),
])

print("\nRunning 5-fold Stratified Cross-Validation...")
cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_acc  = cross_val_score(pipeline, X, y, cv=cv, scoring='accuracy')
cv_f1   = cross_val_score(pipeline, X, y, cv=cv, scoring='f1')
cv_prec = cross_val_score(pipeline, X, y, cv=cv, scoring='precision')
cv_rec  = cross_val_score(pipeline, X, y, cv=cv, scoring='recall')

print(f"\n{'='*58}")
print(f"  FINAL MODEL RESULTS")
print(f"{'='*58}")
print(f"  Dataset          : {len(X)} samples (HC3 + synthetic)")
print(f"  CV Accuracy      : {cv_acc.mean()*100:.1f}% +/- {cv_acc.std()*100:.1f}%")
print(f"  CV F1 Score      : {cv_f1.mean()*100:.1f}% +/- {cv_f1.std()*100:.1f}%")
print(f"  CV Precision     : {cv_prec.mean()*100:.1f}%")
print(f"  CV Recall        : {cv_rec.mean()*100:.1f}%")
print(f"  Per-fold acc     : {[f'{s*100:.1f}%' for s in cv_acc]}")

print("\nTraining final model on full dataset...")
pipeline.fit(X, y)
train_acc = accuracy_score(y, pipeline.predict(X))
print(f"  Train Accuracy   : {train_acc*100:.1f}%")
print()
print(classification_report(y, pipeline.predict(X),
                             target_names=["Genuine","AI-Assisted"]))

# ── Feature importance (RF component) ────────────────────────────────────────
try:
    rf_model = pipeline.named_steps['clf'].estimators_[1]
    importances = rf_model.feature_importances_
    top = sorted(zip(FEATURE_NAMES, importances), key=lambda x: -x[1])[:8]
    print("  Top 8 features by importance:")
    for name, imp in top:
        bar = '#' * int(imp * 200)
        print(f"    {name:<20} {imp:.4f}  {bar}")
except Exception:
    pass

# ── Save ──────────────────────────────────────────────────────────────────────
joblib.dump(pipeline, MODEL_DIR / "sachhAI_classifier.pkl")

meta = {
    "cv_accuracy_mean": round(cv_acc.mean()*100, 1),
    "cv_accuracy_std":  round(cv_acc.std()*100, 1),
    "cv_f1_mean":       round(cv_f1.mean()*100, 1),
    "cv_precision":     round(cv_prec.mean()*100, 1),
    "cv_recall":        round(cv_rec.mean()*100, 1),
    "train_accuracy":   round(train_acc*100, 1),
    "n_samples":        len(X),
    "n_genuine":        int((y==0).sum()),
    "n_ai_assisted":    int((y==1).sum()),
    "features":         FEATURE_NAMES,
    "n_features":       len(FEATURE_NAMES),
    "model_type":       "VotingClassifier(LR+RF300+GB200) + StandardScaler",
    "dataset":          "HC3 (open_qa+finance+medicine+reddit_eli5+wiki_csai) + synthetic",
}
with open(MODEL_DIR / "model_meta.json", "w") as f:
    json.dump(meta, f, indent=2)

print(f"\n  Model saved -> {MODEL_DIR / 'sachhAI_classifier.pkl'}")
print(f"  CV Accuracy: {meta['cv_accuracy_mean']}% +/- {meta['cv_accuracy_std']}%")
print(f"  Features: {meta['n_features']}")
print(f"{'='*58}")
print("\nDone. Restart the backend server to load the new model.")
