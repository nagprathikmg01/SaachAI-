"""
train_model.py — Train SachhAI's ML authenticity classifier.

Uses the existing style_comparator feature extraction on a curated
synthetic dataset of genuine vs AI-assisted interview response pairs.

Run:
    cd backend
    venv\\Scripts\\python train_model.py

Outputs:
    voice_module/model/sachhAI_classifier.pkl   (trained model)
    voice_module/model/model_meta.json          (accuracy + feature info)
"""

import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
from pathlib import Path

# ── Add backend to path ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from voice_module.style_comparator import _build_profile, _transition_diff

# ── Dataset ───────────────────────────────────────────────────────────────────
# Each pair: (personal_text, technical_text, label)
# label: 0 = Genuine (consistent human), 1 = AI-Assisted (suspicious shift)

DATASET = [

    # ═══ GENUINE pairs (label=0) — consistent casual-to-technical style ══════

    ("Hi I'm Ravi. I studied CS at VTU. I like building mobile apps and have done some internships.",
     "In my internship I built a React Native app that fetched data from a REST API. I used Redux for state management and it was deployed on both iOS and Android.",
     0),

    ("Hey, I'm Priya. I did my degree in IT. I mostly work with Python and have done a few ML projects.",
     "My ML project used scikit-learn to classify spam emails. I tried logistic regression and random forest and random forest gave about 92 percent accuracy on the test set.",
     0),

    ("I'm James. I graduated last year in software engineering. I like backend stuff and databases.",
     "I built a REST API using Node.js and Express. The database was PostgreSQL and I wrote queries to handle user authentication and session management.",
     0),

    ("My name is Sara. I studied computer science. I enjoy frontend work, especially CSS and JavaScript.",
     "I built a portfolio site using plain HTML CSS and JavaScript. I added animations with CSS keyframes and made it mobile responsive using media queries.",
     0),

    ("I'm Chen. I work with Java mostly. Did my masters from IIT and been coding for about three years.",
     "I built a Spring Boot service that exposed REST endpoints for our e-commerce app. I used JPA for database access and implemented basic caching with Redis.",
     0),

    ("Hi, I'm Aditya. I'm a final year student. I work with Python and have done web development.",
     "I built a simple Django app with user login and a product listing page. It connected to a SQLite database and I used Bootstrap for the frontend.",
     0),

    ("My name is Maria. I studied data science. I like working with data and building dashboards.",
     "I used pandas and matplotlib to clean and visualize sales data. I built a simple dashboard in Streamlit that showed monthly revenue trends.",
     0),

    ("Hi I'm Tom. I did electrical engineering but moved into software. I mostly work on embedded systems.",
     "I wrote firmware in C for a temperature sensor project. The microcontroller read ADC values and sent them over UART to a Raspberry Pi for logging.",
     0),

    ("I'm Anjali. I graduated in 2023. I've been working with React for frontend development at a startup.",
     "I built reusable components in React and used hooks for state management. We integrated with a backend API and added basic routing using React Router.",
     0),

    ("Hey I'm David. I've worked with Python and Flask for about two years now, mainly doing backend APIs.",
     "I built a Flask API that handled user authentication using JWT tokens. The API had endpoints for CRUD operations on a MySQL database.",
     0),

    ("I'm Nisha. I did my BCA and then worked for a year in web development. I mainly use JavaScript.",
     "I built a simple todo app using vanilla JavaScript and localStorage. It supported adding, editing and deleting tasks without any backend.",
     0),

    ("Hi, I'm Kevin. I studied computer science and I love algorithms and problem solving.",
     "I solved graph traversal problems using BFS and DFS in Python. I also implemented Dijkstra's algorithm for a shortest path problem in my algorithms course.",
     0),

    ("My name is Fatima. I have experience with Android development and have published one app.",
     "I built an Android app using Java and the Android SDK. It had a login screen a main activity and used SharedPreferences to store user settings.",
     0),

    ("I'm Akash. I mostly do backend development with Node.js. I've been coding since high school.",
     "I built a REST API with Express.js that handles CRUD for a blog application. I used MongoDB as the database and Mongoose for schema definitions.",
     0),

    ("Hi I'm Li. I studied software engineering and I've done a few projects in Python and web dev.",
     "I made a web scraper in Python using BeautifulSoup that collected product prices from an e-commerce site and stored them in a CSV file for analysis.",
     0),

    ("I'm Rahul. I work with data and have some experience in machine learning and Python.",
     "I built a simple regression model to predict house prices using scikit-learn. I did feature engineering and used cross validation to evaluate the model.",
     0),

    ("Hey, I'm Sofia. I studied information technology and I love UI design and frontend development.",
     "I designed and built a landing page using HTML CSS and a bit of JavaScript. I focused on making it look clean and professional using Flexbox for layout.",
     0),

    ("My name is Ben. I'm a junior developer and I mainly work on React and TypeScript.",
     "I built a small dashboard app in React with TypeScript. I used hooks for state and effects and consumed a public weather API to show weather data.",
     0),

    ("I'm Pooja. I did my degree in CS. I've worked on projects involving databases and Python backends.",
     "I created a Python script that automated data cleanup tasks on a PostgreSQL database. It removed duplicates and normalized phone numbers across the users table.",
     0),

    ("Hi I'm Omar. I study computer science and I've done two internships in web development.",
     "In my internship I worked on a Vue.js frontend that consumed a REST API. I implemented form validation and connected the UI to the backend endpoints.",
     0),

    ("My name is Zara. I enjoy designing systems and writing clean code. I mainly use Python.",
     "I designed a simple event-driven system where a publisher posted messages to a queue and consumers processed them. I used Python threading to simulate concurrency.",
     0),

    ("I'm Raj. I've been coding for about four years. I love Python and building automation scripts.",
     "I wrote a Python script that monitored a folder for new files and automatically converted PDFs to text using PyPDF2. It emailed a summary daily.",
     0),

    ("Hey, I'm Emma. I studied CS and I work on full stack applications mostly in React and Django.",
     "I built a full stack app where the frontend was React and the backend was Django REST framework. I used JWT for auth and deployed it on a free hosting service.",
     0),

    ("I'm Miguel. I have a background in networking and shifted to software development two years ago.",
     "I built a simple TCP client-server program in Python where the server handled multiple clients using threading. Each client could send messages and receive responses.",
     0),

    ("Hi, I'm Neha. I've been working as a frontend developer for one year. I mainly use React.",
     "I built a product listing page in React with filtering and sorting functionality. I used useState and useEffect to manage the data and UI state.",
     0),

    ("I'm Alex. I do data analysis and have used R and Python for my projects at university.",
     "I analyzed a dataset of survey responses using pandas and seaborn. I did exploratory data analysis, computed correlations, and visualized distributions with histograms.",
     0),

    ("Hey I'm Kavitha. I completed my engineering last year. I like backend development and APIs.",
     "I built a FastAPI backend with endpoints for a simple inventory management system. I used SQLAlchemy for database access and Pydantic for request validation.",
     0),

    ("My name is Chris. I mostly work with Java and Spring Boot for enterprise applications.",
     "I implemented a Spring Boot microservice that handled order processing. It used Kafka for event-driven communication and stored data in a PostgreSQL database.",
     0),

    ("I'm Divya. I studied computer applications and I work with web technologies mostly.",
     "I built a simple e-commerce frontend using HTML CSS and JavaScript. It had a product grid, a cart that used localStorage, and a basic checkout form.",
     0),

    ("Hi, I'm Lucas. I have experience in Python and I've worked on data pipelines before.",
     "I built an ETL pipeline that pulled data from a CSV, transformed it using pandas, and loaded it into a SQLite database. It ran on a daily schedule using cron.",
     0),

    # ═══ AI-ASSISTED pairs (label=1) — casual personal + formal/AI technical ══

    ("Hi I'm Aryan, um I studied computer science and I like coding and stuff.",
     "The proposed solution leverages a microservices architecture implementing containerized deployment strategies utilizing Docker and Kubernetes orchestration. Furthermore, the system incorporates sophisticated load balancing mechanisms and horizontal scaling capabilities to ensure optimal resource utilization and high availability in distributed environments.",
     1),

    ("I'm Meera. I've done some projects in Python, you know just basic stuff like web apps.",
     "The application implements a robust Model-View-Controller architectural paradigm with comprehensive dependency injection patterns. Additionally, the codebase adheres to SOLID principles and incorporates advanced design patterns such as Repository and Factory patterns to ensure maintainability and extensibility of the software system.",
     1),

    ("Hey I'm Jake. I know JavaScript and React kind of well. I've been learning for like two years.",
     "The frontend architecture employs a unidirectional data flow paradigm utilizing Redux Toolkit for state management. Furthermore, the implementation leverages React Query for sophisticated server-state synchronization, ensuring optimal cache invalidation strategies and minimizing redundant network requests through memoization techniques.",
     1),

    ("I'm Sunita. I basically work with databases and SQL and like backend stuff mostly.",
     "The database architecture implements comprehensive normalization through third normal form compliance, ensuring data integrity through carefully designed constraint mechanisms. Additionally, the system leverages advanced indexing strategies including composite indexes and partial indexes to optimize query execution plans and minimize I/O operations.",
     1),

    ("Hi I'm Raj. Um I like machine learning you know, I've done some projects with Python.",
     "The machine learning pipeline incorporates sophisticated feature engineering methodologies including dimensionality reduction via Principal Component Analysis and comprehensive hyperparameter optimization through Bayesian optimization techniques. Consequently, the model achieves superior generalization performance while mitigating overfitting through regularization strategies.",
     1),

    ("I'm Preethi. I studied IT and I kind of like web development and building things online.",
     "The web application implements a comprehensive security architecture incorporating JWT-based authentication with refresh token rotation mechanisms. Furthermore, the system employs CSRF protection, XSS prevention through Content Security Policy headers, and implements rate limiting to mitigate distributed denial-of-service attack vectors.",
     1),

    ("Hey I'm Nathan. I mostly do Android stuff and I've learned Java and a bit of Kotlin.",
     "The Android application architecture adheres to the MVVM design pattern utilizing Android Architecture Components including LiveData and ViewModel to ensure lifecycle-aware data management. Additionally, the implementation incorporates Dependency Injection through Hilt, facilitating testability and modularity across the application layers.",
     1),

    ("My name is Rekha. I have experience with Python you know basically data science projects.",
     "The data science solution implements an ensemble methodology combining gradient boosting algorithms with neural network architectures. Specifically, the system leverages XGBoost for structured data processing while employing convolutional neural networks for feature extraction, subsequently combining predictions through stacking meta-learners.",
     1),

    ("Hi I'm Sam. I sort of know JavaScript. I've made like a few small projects.",
     "The JavaScript implementation employs sophisticated asynchronous programming paradigms utilizing Promise chains and async/await syntax for non-blocking I/O operations. Furthermore, the codebase implements comprehensive error handling through custom exception hierarchies and leverages event-driven architecture for optimal performance characteristics.",
     1),

    ("I'm Deepak. I know some cloud stuff and I've played with AWS a little bit.",
     "The cloud infrastructure architecture implements a multi-tier deployment strategy utilizing Amazon Web Services, incorporating Auto Scaling Groups with sophisticated scaling policies based on custom CloudWatch metrics. Furthermore, the solution leverages Infrastructure as Code through Terraform for reproducible environment provisioning and drift detection.",
     1),

    ("Hey I'm Anika. I basically do frontend work. React and CSS mostly, nothing too complex.",
     "The frontend implementation demonstrates sophisticated progressive web application characteristics including service worker integration for offline functionality and background synchronization. Additionally, the architecture employs code splitting and lazy loading strategies to optimize the critical rendering path and achieve superior Core Web Vitals metrics.",
     1),

    ("Hi I'm Tejas. I've worked with SQL and databases a bit. I like backend development.",
     "The relational database design implements comprehensive partitioning strategies including range partitioning for temporal data and hash partitioning for uniform distribution of transactional records. Furthermore, the architecture incorporates read replicas with asynchronous replication to distribute query loads and ensure high availability during planned maintenance windows.",
     1),

    ("My name is Lisa. I sort of know Python and I've done some web stuff with Flask.",
     "The RESTful API design adheres to Richardson Maturity Model Level 3 with comprehensive hypermedia controls following the HATEOAS architectural constraint. Furthermore, the implementation incorporates sophisticated content negotiation mechanisms and versioning strategies to ensure backward compatibility while enabling progressive API evolution.",
     1),

    ("I'm Carlos. I've been learning DevOps things lately. I know a bit about Docker.",
     "The DevOps implementation establishes a comprehensive CI/CD pipeline architecture utilizing GitOps principles for declarative infrastructure management. The pipeline incorporates automated testing gates including unit tests, integration tests, and end-to-end tests, with sophisticated canary deployment strategies to minimize risk during production releases.",
     1),

    ("Hi I'm Tanya. I've done some machine learning in college, basically just assignments.",
     "The neural architecture implements transformer-based attention mechanisms with multi-head self-attention layers enabling the model to capture long-range dependencies across sequential data. Furthermore, the training methodology incorporates curriculum learning strategies and sophisticated learning rate scheduling through cosine annealing with warm restarts.",
     1),

    ("I'm Vinod. I know JavaScript and have made some small projects. I like coding generally.",
     "The JavaScript runtime optimization implements sophisticated garbage collection tuning strategies and memory pool management to minimize GC pause times in production environments. Additionally, the architecture employs WebAssembly modules for computationally intensive operations, achieving near-native performance characteristics for critical code paths.",
     1),

    ("Hey I'm Nandini. I work with Python mostly and I've done some projects with data.",
     "The data engineering pipeline implements Apache Kafka for real-time stream processing with sophisticated partitioning strategies ensuring ordered message delivery within partition boundaries. Furthermore, the architecture incorporates Apache Spark for distributed batch processing, enabling horizontal scalability across commodity hardware clusters.",
     1),

    ("I'm Derek. I've done some work with React and Node.js. I like full stack development.",
     "The full-stack architecture implements GraphQL federation for unified API gateway management, enabling independent service development while maintaining consistent schema contracts. Furthermore, the implementation incorporates sophisticated N+1 query prevention through DataLoader batching and comprehensive caching strategies at both the CDN and application layers.",
     1),

    ("Hi I'm Kavya. I've used Python for some basic projects. I'm still learning really.",
     "The Python implementation employs metaclass programming and descriptor protocols to implement sophisticated attribute validation and transformation pipelines. Furthermore, the codebase leverages abstract base classes and protocol-based structural typing to ensure comprehensive interface contracts across the distributed system components.",
     1),

    ("My name is Ryan. I do Android development. I know Java and Kotlin a little bit.",
     "The Android application implements Jetpack Compose for declarative UI rendering with sophisticated state hoisting patterns ensuring unidirectional data flow throughout the component hierarchy. Furthermore, the architecture employs coroutines with structured concurrency for lifecycle-aware asynchronous operations and Flow for reactive stream processing.",
     1),

    ("Hey I'm Ishaan. I'm basically a frontend guy, I know HTML CSS and some React.",
     "The frontend implementation achieves exceptional performance characteristics through sophisticated rendering optimization strategies including virtual DOM reconciliation algorithms and memoization through React.memo and useMemo hooks. Additionally, the architecture implements micro-frontend patterns enabling independent deployment of UI modules.",
     1),

    ("I'm Shreya. I sort of know databases and backend stuff. I've worked with Node.js.",
     "The backend architecture implements the Command Query Responsibility Segregation pattern with event sourcing for comprehensive audit trails and temporal query capabilities. Furthermore, the system employs saga patterns for distributed transaction management across microservice boundaries, ensuring eventual consistency guarantees.",
     1),

    ("Hi I'm Tony. I've been learning programming for about a year. I like Python mainly.",
     "The algorithmic implementation leverages advanced dynamic programming techniques with memoization to achieve optimal time complexity of O(n log n) for previously intractable computational problems. Furthermore, the solution employs amortized analysis principles to demonstrate superior asymptotic performance characteristics compared to naive recursive implementations.",
     1),

    ("I'm Swathi. I work with web technologies mostly you know, HTML and JavaScript and stuff.",
     "The web security implementation incorporates comprehensive cryptographic protocols including AES-256 encryption for data at rest and TLS 1.3 for data in transit. Furthermore, the system implements defense-in-depth strategies including strict Content Security Policies, Subresource Integrity checks, and comprehensive input sanitization pipelines.",
     1),

    ("Hey I'm Arjun. I basically do data analysis with Python and Excel at my internship.",
     "The analytical framework implements sophisticated multivariate statistical methodologies including principal component analysis for dimensionality reduction and hierarchical clustering algorithms for pattern discovery in high-dimensional feature spaces. Furthermore, the system employs Bayesian inference techniques for probabilistic modeling of uncertain data distributions.",
     1),

    ("My name is Kelly. I've done some projects in Java and I'm learning Spring Boot.",
     "The enterprise application implements comprehensive aspect-oriented programming paradigms through Spring AOP for cross-cutting concerns including distributed tracing, circuit breaker patterns via Resilience4j, and sophisticated retry mechanisms with exponential backoff strategies for fault-tolerant microservice communication.",
     1),

    ("Hi I'm Nikhil. I like coding and I've done some Python projects. I enjoy problem solving.",
     "The computational solution implements a highly optimized graph traversal algorithm incorporating bidirectional BFS with sophisticated heuristic pruning strategies. The implementation leverages parallel processing capabilities through multiprocessing pools to achieve linear scalability across available CPU cores for embarrassingly parallel sub-problems.",
     1),

    ("I'm Priya S. I've been working as a developer for one year. I know React and a bit of backend.",
     "The React application implements sophisticated code splitting strategies utilizing dynamic imports and React.lazy for granular bundle optimization. Furthermore, the architecture employs virtual scrolling through react-window for efficient rendering of large datasets, and implements comprehensive performance monitoring through the React Profiler API.",
     1),

    ("Hey I'm Dev. I studied computer science and I know some programming languages basically.",
     "The distributed system architecture implements Byzantine fault tolerance through Raft consensus algorithm, ensuring linearizability guarantees across replicated state machines. Furthermore, the implementation incorporates vector clocks for causality tracking and conflict-free replicated data types for eventual consistency in partition scenarios.",
     1),

    ("I'm Asha. I do web development mainly. I know JavaScript and I've used Vue.js a bit.",
     "The Vue.js application implements the Composition API with sophisticated reactive state management through Pinia, enabling fine-grained reactivity tracking and optimized re-rendering. Additionally, the architecture incorporates server-side rendering through Nuxt.js for optimal Core Web Vitals metrics and improved search engine optimization.",
     1),

]

print(f"Dataset: {len(DATASET)} pairs ({sum(1 for _,_,l in DATASET if l==0)} genuine, {sum(1 for _,_,l in DATASET if l==1)} AI-assisted)")

# ── Feature extraction ────────────────────────────────────────────────────────

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

FEATURE_NAMES = [
    "vocab_jump", "formal_jump", "gram_jump", "sent_jump",
    "fill_drop", "div_diff", "trans_diff", "word_ratio", "sent_ratio",
    "t_vocab", "t_formal", "t_gram", "t_sent", "t_trans", "t_fill",
    "p_fill", "p_vocab", "strong_count",
]

# ── Build feature matrix ──────────────────────────────────────────────────────

print("\nExtracting features...")
X, y = [], []
for personal, technical, label in DATASET:
    X.append(extract_features(personal, technical))
    y.append(label)

X = np.array(X)
y = np.array(y)
print(f"Feature matrix: {X.shape}")

# ── Train & evaluate ──────────────────────────────────────────────────────────

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib

# Build ensemble pipeline
lr  = LogisticRegression(C=1.0, max_iter=1000, class_weight='balanced', random_state=42)
rf  = RandomForestClassifier(n_estimators=200, max_depth=6, class_weight='balanced', random_state=42)
gb  = GradientBoostingClassifier(n_estimators=150, learning_rate=0.08, max_depth=4, random_state=42)

voting = VotingClassifier(
    estimators=[('lr', lr), ('rf', rf), ('gb', gb)],
    voting='soft',
    weights=[1, 2, 2],
)

pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('clf',    voting),
])

# Stratified 5-fold CV
print("\nRunning Stratified 5-Fold Cross-Validation...")
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(pipeline, X, y, cv=cv, scoring='accuracy')
cv_f1     = cross_val_score(pipeline, X, y, cv=cv, scoring='f1')

print(f"\n{'='*55}")
print(f"  CROSS-VALIDATION RESULTS (5-Fold Stratified)")
print(f"{'='*55}")
print(f"  Accuracy : {cv_scores.mean()*100:.1f}% ± {cv_scores.std()*100:.1f}%")
print(f"  F1 Score : {cv_f1.mean()*100:.1f}% ± {cv_f1.std()*100:.1f}%")
print(f"  Per-fold : {[f'{s*100:.1f}%' for s in cv_scores]}")

# Train final model on all data
print("\nTraining final model on full dataset...")
pipeline.fit(X, y)

# Final training accuracy
y_pred = pipeline.predict(X)
train_acc = accuracy_score(y, y_pred)
print(f"  Training accuracy: {train_acc*100:.1f}%")

print("\nClassification Report (training set):")
print(classification_report(y, y_pred, target_names=["Genuine", "AI-Assisted"]))

print("Confusion Matrix:")
cm = confusion_matrix(y, y_pred)
print(f"  TN={cm[0][0]}  FP={cm[0][1]}")
print(f"  FN={cm[1][0]}  TP={cm[1][1]}")

# ── Save model ────────────────────────────────────────────────────────────────

MODEL_DIR = Path(__file__).parent / "voice_module" / "model"
MODEL_DIR.mkdir(exist_ok=True)
MODEL_PATH = MODEL_DIR / "sachhAI_classifier.pkl"
META_PATH  = MODEL_DIR / "model_meta.json"

joblib.dump(pipeline, MODEL_PATH)

meta = {
    "cv_accuracy_mean":  round(cv_scores.mean() * 100, 1),
    "cv_accuracy_std":   round(cv_scores.std()  * 100, 1),
    "cv_f1_mean":        round(cv_f1.mean()     * 100, 1),
    "train_accuracy":    round(train_acc         * 100, 1),
    "n_samples":         len(DATASET),
    "n_genuine":         int(sum(1 for _,_,l in DATASET if l==0)),
    "n_ai_assisted":     int(sum(1 for _,_,l in DATASET if l==1)),
    "features":          FEATURE_NAMES,
    "model_type":        "VotingClassifier(LR+RF+GB) + StandardScaler",
}
with open(META_PATH, "w") as f:
    json.dump(meta, f, indent=2)

print(f"\n{'='*55}")
print(f"  MODEL SAVED")
print(f"  Path: {MODEL_PATH}")
print(f"  CV Accuracy: {meta['cv_accuracy_mean']}% ± {meta['cv_accuracy_std']}%")
print(f"  CV F1 Score: {meta['cv_f1_mean']}%")
print(f"{'='*55}")
print("\nDone! The backend will automatically use this model.")
