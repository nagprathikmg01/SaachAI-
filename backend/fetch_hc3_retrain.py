"""
fetch_hc3_retrain.py — Download HC3 dataset and retrain the SachhAI classifier.

HC3 (Human ChatGPT Comparison Corpus) contains 58k+ Q&A pairs comparing
human vs ChatGPT answers — perfect signal for style-shift detection.

Run:
    cd backend
    venv\\Scripts\\python fetch_hc3_retrain.py
"""

import json, sys, warnings, os
warnings.filterwarnings("ignore")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Download HC3 open_qa split via httpx (already in venv) ───────────────────
import httpx

HC3_URL = "https://huggingface.co/datasets/Hello-SimpleAI/HC3/resolve/main/open_qa.jsonl"
CACHE    = Path(__file__).parent / "voice_module" / "model" / "hc3_open_qa.jsonl"
CACHE.parent.mkdir(exist_ok=True)

if not CACHE.exists():
    print(f"Downloading HC3 open_qa from HuggingFace (~4 MB)...")
    try:
        with httpx.stream("GET", HC3_URL, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with open(CACHE, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        print(f"  Saved to {CACHE}")
    except Exception as e:
        print(f"  Download failed: {e}")
        print("  Falling back to synthetic dataset only.")
        CACHE = None
else:
    print(f"HC3 cache found: {CACHE}")

# ── Parse HC3 pairs ───────────────────────────────────────────────────────────
hc3_pairs = []  # (personal_proxy, technical, label)

if CACHE and CACHE.exists():
    print("Parsing HC3 pairs...")
    with open(CACHE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 600:  # cap at 600 rows for speed
                break
            try:
                row = json.loads(line)
                q   = row.get("question", "")
                humans  = row.get("human_answers", [])
                chatgpt = row.get("chatgpt_answers", [])

                # Use question as "personal" proxy (short, informal)
                # human_answer = genuine pair (label 0)
                # chatgpt_answer = AI-assisted pair (label 1)
                for h in humans[:1]:
                    if len(h.split()) >= 20:
                        hc3_pairs.append((q, h, 0))
                for c in chatgpt[:1]:
                    if len(c.split()) >= 20:
                        hc3_pairs.append((q, c, 1))
            except Exception:
                pass

    print(f"  Loaded {len(hc3_pairs)} HC3 pairs "
          f"({sum(1 for _,_,l in hc3_pairs if l==0)} genuine, "
          f"{sum(1 for _,_,l in hc3_pairs if l==1)} AI-assisted)")

# ── Synthetic dataset (from train_model.py) ───────────────────────────────────
SYNTHETIC = [
    ("Hi I'm Ravi. I studied CS at VTU. I like building mobile apps and have done some internships.",
     "In my internship I built a React Native app that fetched data from a REST API. I used Redux for state management and it was deployed on both iOS and Android.", 0),
    ("Hey, I'm Priya. I did my degree in IT. I mostly work with Python and have done a few ML projects.",
     "My ML project used scikit-learn to classify spam emails. I tried logistic regression and random forest and random forest gave about 92 percent accuracy on the test set.", 0),
    ("I'm James. I graduated last year in software engineering. I like backend stuff and databases.",
     "I built a REST API using Node.js and Express. The database was PostgreSQL and I wrote queries to handle user authentication and session management.", 0),
    ("My name is Sara. I studied computer science. I enjoy frontend work, especially CSS and JavaScript.",
     "I built a portfolio site using plain HTML CSS and JavaScript. I added animations with CSS keyframes and made it mobile responsive using media queries.", 0),
    ("I'm Chen. I work with Java mostly. Did my masters from IIT and been coding for about three years.",
     "I built a Spring Boot service that exposed REST endpoints for our e-commerce app. I used JPA for database access and implemented basic caching with Redis.", 0),
    ("Hi, I'm Aditya. I'm a final year student. I work with Python and have done web development.",
     "I built a simple Django app with user login and a product listing page. It connected to a SQLite database and I used Bootstrap for the frontend.", 0),
    ("My name is Maria. I studied data science. I like working with data and building dashboards.",
     "I used pandas and matplotlib to clean and visualize sales data. I built a simple dashboard in Streamlit that showed monthly revenue trends.", 0),
    ("Hi I'm Tom. I did electrical engineering but moved into software. I mostly work on embedded systems.",
     "I wrote firmware in C for a temperature sensor project. The microcontroller read ADC values and sent them over UART to a Raspberry Pi for logging.", 0),
    ("I'm Anjali. I graduated in 2023. I've been working with React for frontend development at a startup.",
     "I built reusable components in React and used hooks for state management. We integrated with a backend API and added basic routing using React Router.", 0),
    ("Hey I'm David. I've worked with Python and Flask for about two years now, mainly doing backend APIs.",
     "I built a Flask API that handled user authentication using JWT tokens. The API had endpoints for CRUD operations on a MySQL database.", 0),
    ("I'm Nisha. I did my BCA and then worked for a year in web development. I mainly use JavaScript.",
     "I built a simple todo app using vanilla JavaScript and localStorage. It supported adding, editing and deleting tasks without any backend.", 0),
    ("Hi, I'm Kevin. I studied computer science and I love algorithms and problem solving.",
     "I solved graph traversal problems using BFS and DFS in Python. I also implemented Dijkstra's algorithm for a shortest path problem in my algorithms course.", 0),
    ("I'm Rahul. I work with data and have some experience in machine learning and Python.",
     "I built a simple regression model to predict house prices using scikit-learn. I did feature engineering and used cross validation to evaluate the model.", 0),
    ("Hey, I'm Sofia. I studied information technology and I love UI design and frontend development.",
     "I designed and built a landing page using HTML CSS and a bit of JavaScript. I focused on making it look clean and professional using Flexbox for layout.", 0),
    ("My name is Ben. I'm a junior developer and I mainly work on React and TypeScript.",
     "I built a small dashboard app in React with TypeScript. I used hooks for state and effects and consumed a public weather API to show weather data.", 0),
    ("Hi I'm Aryan, um I studied computer science and I like coding and stuff.",
     "The proposed solution leverages a microservices architecture implementing containerized deployment strategies utilizing Docker and Kubernetes orchestration. Furthermore, the system incorporates sophisticated load balancing mechanisms and horizontal scaling capabilities to ensure optimal resource utilization and high availability in distributed environments.", 1),
    ("I'm Meera. I've done some projects in Python, you know just basic stuff like web apps.",
     "The application implements a robust Model-View-Controller architectural paradigm with comprehensive dependency injection patterns. Additionally, the codebase adheres to SOLID principles and incorporates advanced design patterns such as Repository and Factory patterns to ensure maintainability and extensibility of the software system.", 1),
    ("Hey I'm Jake. I know JavaScript and React kind of well. I've been learning for like two years.",
     "The frontend architecture employs a unidirectional data flow paradigm utilizing Redux Toolkit for state management. Furthermore, the implementation leverages React Query for sophisticated server-state synchronization, ensuring optimal cache invalidation strategies and minimizing redundant network requests through memoization techniques.", 1),
    ("I'm Sunita. I basically work with databases and SQL and like backend stuff mostly.",
     "The database architecture implements comprehensive normalization through third normal form compliance, ensuring data integrity through carefully designed constraint mechanisms. Additionally, the system leverages advanced indexing strategies including composite indexes and partial indexes to optimize query execution plans and minimize I/O operations.", 1),
    ("Hi I'm Raj. Um I like machine learning you know, I've done some projects with Python.",
     "The machine learning pipeline incorporates sophisticated feature engineering methodologies including dimensionality reduction via Principal Component Analysis and comprehensive hyperparameter optimization through Bayesian optimization techniques. Consequently, the model achieves superior generalization performance while mitigating overfitting through regularization strategies.", 1),
    ("I'm Preethi. I studied IT and I kind of like web development and building things online.",
     "The web application implements a comprehensive security architecture incorporating JWT-based authentication with refresh token rotation mechanisms. Furthermore, the system employs CSRF protection, XSS prevention through Content Security Policy headers, and implements rate limiting to mitigate distributed denial-of-service attack vectors.", 1),
    ("Hey I'm Nathan. I mostly do Android stuff and I've learned Java and a bit of Kotlin.",
     "The Android application architecture adheres to the MVVM design pattern utilizing Android Architecture Components including LiveData and ViewModel to ensure lifecycle-aware data management. Additionally, the implementation incorporates Dependency Injection through Hilt, facilitating testability and modularity across the application layers.", 1),
    ("My name is Rekha. I have experience with Python you know basically data science projects.",
     "The data science solution implements an ensemble methodology combining gradient boosting algorithms with neural network architectures. Specifically, the system leverages XGBoost for structured data processing while employing convolutional neural networks for feature extraction, subsequently combining predictions through stacking meta-learners.", 1),
    ("Hi I'm Sam. I sort of know JavaScript. I've made like a few small projects.",
     "The JavaScript implementation employs sophisticated asynchronous programming paradigms utilizing Promise chains and async/await syntax for non-blocking I/O operations. Furthermore, the codebase implements comprehensive error handling through custom exception hierarchies and leverages event-driven architecture for optimal performance characteristics.", 1),
    ("I'm Deepak. I know some cloud stuff and I've played with AWS a little bit.",
     "The cloud infrastructure architecture implements a multi-tier deployment strategy utilizing Amazon Web Services, incorporating Auto Scaling Groups with sophisticated scaling policies based on custom CloudWatch metrics. Furthermore, the solution leverages Infrastructure as Code through Terraform for reproducible environment provisioning and drift detection.", 1),
    ("Hey I'm Anika. I basically do frontend work. React and CSS mostly, nothing too complex.",
     "The frontend implementation demonstrates sophisticated progressive web application characteristics including service worker integration for offline functionality and background synchronization. Additionally, the architecture employs code splitting and lazy loading strategies to optimize the critical rendering path and achieve superior Core Web Vitals metrics.", 1),
    ("Hi I'm Tejas. I've worked with SQL and databases a bit. I like backend development.",
     "The relational database design implements comprehensive partitioning strategies including range partitioning for temporal data and hash partitioning for uniform distribution of transactional records. Furthermore, the architecture incorporates read replicas with asynchronous replication to distribute query loads and ensure high availability during planned maintenance windows.", 1),
    ("My name is Lisa. I sort of know Python and I've done some web stuff with Flask.",
     "The RESTful API design adheres to Richardson Maturity Model Level 3 with comprehensive hypermedia controls following the HATEOAS architectural constraint. Furthermore, the implementation incorporates sophisticated content negotiation mechanisms and versioning strategies to ensure backward compatibility while enabling progressive API evolution.", 1),
    ("I'm Carlos. I've been learning DevOps things lately. I know a bit about Docker.",
     "The DevOps implementation establishes a comprehensive CI/CD pipeline architecture utilizing GitOps principles for declarative infrastructure management. The pipeline incorporates automated testing gates including unit tests, integration tests, and end-to-end tests, with sophisticated canary deployment strategies to minimize risk during production releases.", 1),
    ("Hi I'm Tanya. I've done some machine learning in college, basically just assignments.",
     "The neural architecture implements transformer-based attention mechanisms with multi-head self-attention layers enabling the model to capture long-range dependencies across sequential data. Furthermore, the training methodology incorporates curriculum learning strategies and sophisticated learning rate scheduling through cosine annealing with warm restarts.", 1),
]

# ── Combine datasets ──────────────────────────────────────────────────────────
all_pairs = SYNTHETIC + hc3_pairs
print(f"\nTotal dataset: {len(all_pairs)} pairs "
      f"({sum(1 for _,_,l in all_pairs if l==0)} genuine, "
      f"{sum(1 for _,_,l in all_pairs if l==1)} AI-assisted)")

# ── Feature extraction ────────────────────────────────────────────────────────
from voice_module.style_comparator import _build_profile, _transition_diff
import numpy as np

def extract_features(personal, technical):
    p = _build_profile(personal)
    t = _build_profile(technical)
    vocab_jump  = t["vocabulary_level"]  - p["vocabulary_level"]
    formal_jump = t["formality_score"]   - p["formality_score"]
    gram_jump   = t["grammar_score"]     - p["grammar_score"]
    sent_jump   = t["avg_sentence_len"]  - p["avg_sentence_len"]
    fill_drop   = p["filler_ratio"]      - t["filler_ratio"]
    div_diff    = abs(t["lexical_diversity"] - p["lexical_diversity"])
    trans_diff  = _transition_diff(p["transition_density"], t["transition_density"])
    word_ratio  = t["word_count"] / max(1, p["word_count"])
    sent_ratio  = t["avg_sentence_len"] / max(p["avg_sentence_len"], 1.0)
    strong = sum([vocab_jump>12, formal_jump>15, gram_jump>12, sent_jump>5,
                  fill_drop>0.02 and p["filler_ratio"]>0.01, trans_diff>30])
    return np.array([
        vocab_jump, formal_jump, gram_jump, sent_jump,
        fill_drop, div_diff, trans_diff, word_ratio, sent_ratio,
        t["vocabulary_level"], t["formality_score"], t["grammar_score"],
        t["avg_sentence_len"], t["transition_density"], t["filler_ratio"],
        p["filler_ratio"], p["vocabulary_level"], float(strong),
    ], dtype=np.float32)

print("Extracting features...")
X, y = [], []
skipped = 0
for personal, technical, label in all_pairs:
    try:
        X.append(extract_features(personal, technical))
        y.append(label)
    except Exception:
        skipped += 1

X = np.array(X)
y = np.array(y)
print(f"Feature matrix: {X.shape}  (skipped {skipped})")

# ── Train ─────────────────────────────────────────────────────────────────────
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import accuracy_score, f1_score
import joblib

lr  = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced', random_state=42)
rf  = RandomForestClassifier(n_estimators=200, max_depth=6, class_weight='balanced', random_state=42)
gb  = GradientBoostingClassifier(n_estimators=150, learning_rate=0.08, max_depth=4, random_state=42)

pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('clf', VotingClassifier(
        estimators=[('lr', lr), ('rf', rf), ('gb', gb)],
        voting='soft', weights=[1, 2, 2],
    )),
])

print("\nRunning 5-Fold Cross-Validation...")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_acc = cross_val_score(pipeline, X, y, cv=cv, scoring='accuracy')
cv_f1  = cross_val_score(pipeline, X, y, cv=cv, scoring='f1')

print(f"\n{'='*55}")
print(f"  RESULTS WITH HC3 + SYNTHETIC DATA")
print(f"{'='*55}")
print(f"  Training samples : {len(X)}")
print(f"  CV Accuracy      : {cv_acc.mean()*100:.1f}% ± {cv_acc.std()*100:.1f}%")
print(f"  CV F1 Score      : {cv_f1.mean()*100:.1f}% ± {cv_f1.std()*100:.1f}%")
print(f"  Per-fold acc     : {[f'{s*100:.1f}%' for s in cv_acc]}")

pipeline.fit(X, y)
train_acc = accuracy_score(y, pipeline.predict(X))
print(f"  Train Accuracy   : {train_acc*100:.1f}%")

# ── Save ──────────────────────────────────────────────────────────────────────
MODEL_DIR  = Path(__file__).parent / "voice_module" / "model"
MODEL_PATH = MODEL_DIR / "sachhAI_classifier.pkl"
META_PATH  = MODEL_DIR / "model_meta.json"

joblib.dump(pipeline, MODEL_PATH)

meta = {
    "cv_accuracy_mean": round(cv_acc.mean()*100, 1),
    "cv_accuracy_std":  round(cv_acc.std()*100, 1),
    "cv_f1_mean":       round(cv_f1.mean()*100, 1),
    "train_accuracy":   round(train_acc*100, 1),
    "n_samples":        len(X),
    "n_genuine":        int((y==0).sum()),
    "n_ai_assisted":    int((y==1).sum()),
    "features":         ["vocab_jump","formal_jump","gram_jump","sent_jump",
                         "fill_drop","div_diff","trans_diff","word_ratio","sent_ratio",
                         "t_vocab","t_formal","t_gram","t_sent","t_trans","t_fill",
                         "p_fill","p_vocab","strong_count"],
    "model_type": "VotingClassifier(LR+RF+GB) + StandardScaler",
    "dataset":    "HC3 open_qa + synthetic pairs",
}
import json
with open(META_PATH, "w") as f:
    json.dump(meta, f, indent=2)

print(f"\n  Model saved → {MODEL_PATH}")
print(f"  CV Accuracy: {meta['cv_accuracy_mean']}% ± {meta['cv_accuracy_std']}%")
print(f"{'='*55}")
print("\nRetraining complete! Restart the server to load the new model.")
