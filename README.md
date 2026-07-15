<div align="center">

# 🎙️ SacchAI — Interview Integrity Co-Pilot

**Real-time AI detection for technical interviews. Know who's really talking.**

Detect AI-assisted and pre-written interview responses in real time using linguistic style-shift analysis, ML classification, and live audio transcription.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Deepgram](https://img.shields.io/badge/Deepgram-Nova--2-13EF93?logo=deepgram&logoColor=white)](https://deepgram.com)

</div>

---

## 🧠 Problem

Remote technical interviews are increasingly compromised by candidates using AI tools (ChatGPT, Claude, etc.) to generate answers in real-time. Traditional plagiarism scanners cannot detect AI-generated content because it has no "source." 

SacchAI solves this by measuring **how a candidate's natural communication style shifts** between a casual personal introduction and a structured technical response — a behavioral pattern that is extremely difficult to fake consistently.

---

## 🔍 How It Works

SacchAI combines two independent detection signals:

| Signal | Method |
|--------|--------|
| **Style Shift Detection** | Compares 11 linguistic features between personal and technical rounds using a rule-based engine augmented by an ML ensemble classifier |
| **AI Content Detection** | Optional Winston AI integration for plagiarism scanning and AI-generated content detection |

### Interview Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Personal Round  │────▶│ Technical Round  │────▶│  Final Report   │
│   (Baseline)     │     │    (LIVE)        │     │                 │
│                  │     │                  │     │  Verdict +      │
│ "Tell me about   │     │ "Explain how     │     │  Evidence +     │
│  yourself..."    │     │  microservices   │     │  Follow-up Qs   │
│                  │     │  architecture    │     │                 │
│ ✓ Builds         │     │  works..."       │     │ ✓ LSDI Score    │
│   linguistic     │     │                  │     │ ✓ 5-tier Verdict│
│   baseline       │     │ ✓ 20s live       │     │ ✓ Style Flags   │
│                  │     │   style checks   │     │ ✓ Confidence    │
│                  │     │ ✓ Probe question │     │ ✓ PDF Export    │
│                  │     │   suggestions    │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 5-Tier Verdict System

| Verdict | Description |
|---------|-------------|
| 🟢 **Genuine** | No significant indicators — natural responses |
| 🔵 **Low Risk** | Minor style differences — likely natural variation |
| 🟡 **Needs Review** | Noticeable style shift — could reflect preparation or assistance |
| 🟠 **Suspicious** | Multiple style signals — consistent with possible AI assistance |
| 🔴 **High Risk** | Strong divergence across multiple dimensions |

> **⚠️ Disclaimer:** SacchAI supports interviewer judgment and should not be used as the sole basis for any hiring decision. Style differences can reflect rehearsal, fluency, communication style, or language background — not only AI assistance.

---

## ✨ Features

### Core Analysis
- **11-feature linguistic engine** — Vocabulary level, Flesch-Kincaid, Gunning Fog, sentence burstiness, passive voice, hedging density, formality, grammar, filler ratio, transition density, lexical diversity
- **ML ensemble classifier** — VotingClassifier (LR + RF₃₀₀ + GB₂₀₀), trained on HC3 dataset (~6,000 human/AI pairs), CV accuracy **88.4% ± 0.5%**
- **Temporal drift detection** — Identifies mid-answer style spikes (candidate starts naturally, then switches to prepared material)
- **Confidence engine** — Factors in answer length, baseline quality, and signal consistency before issuing verdicts
- **Guardrails** — Short answers automatically cap verdict severity

### Live Interview
- **Real-time transcription** — Deepgram Nova-2 via WebSocket streams words as the candidate speaks
- **20-second live style checks** — During technical round, background analysis runs every 20 seconds
- **Live alert system** — Interviewers see style-shift alerts with confidence bars and probe question suggestions
- **Google Meet integration** — Chrome extension + Plasmo-based Meet overlay capture closed captions automatically

### Platform
- **Web portal** — Landing page, login, interview interface, admin dashboard
- **Chrome extension** — Full interview flow without leaving the browser tab
- **Meet overlay extension** — Glassmorphic overlay directly on Google Meet with real-time scoring
- **Role-based access** — Admin sees all records; HR users see only their own interviews
- **Session persistence** — All sessions saved to Supabase with full audit trail
- **PDF export** — Downloadable candidate reports generated client-side
- **Follow-up question generator** — AI-powered contextual questions based on detected signals

---

## 🏗️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Vanilla HTML/CSS/JS, glassmorphic design system |
| **Backend** | Python 3.11, FastAPI, Uvicorn |
| **Transcription** | Deepgram Nova-2 (WebSocket streaming + batch) |
| **Style Analysis** | Custom rule engine + scikit-learn VotingClassifier |
| **Training Data** | [Hello-SimpleAI/HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3) (human vs ChatGPT) |
| **AI Detection** | Winston AI (optional — works without it) |
| **Database** | Supabase (PostgreSQL via REST) |
| **Auth** | JWT (HS256) with role-based access control |
| **Extensions** | Chrome Extension (Manifest V3) + Plasmo Framework |
| **Deployment** | Docker / Hugging Face Spaces |

---

## 📁 Project Structure

```
sacchAI/
├── frontend/
│   ├── landing.html              Landing / marketing page
│   ├── login.html                Authentication portal
│   ├── interview.html            Main interview interface
│   ├── dashboard.html            Admin dashboard
│   └── *.css / *.js              Shared styles and interactions
│
├── backend/
│   ├── server.py                 FastAPI entry point + lifespan manager
│   ├── auth_routes.py            JWT auth, login, employee CRUD
│   ├── calibration_routes.py     ML model metadata + test endpoints
│   ├── fetch_and_train.py        HC3 download + model training
│   ├── generate_pdf.py           Batch test case PDF generator
│   ├── requirements.txt
│   │
│   └── voice_module/
│       ├── routes.py             REST API endpoints (/voice/*)
│       ├── streaming.py          WebSocket endpoints (Deepgram proxy + Meet analysis)
│       ├── style_comparator.py   11-feature linguistic engine + ML inference
│       ├── transcriber.py        Deepgram batch transcription
│       ├── plagiarism_client.py  Winston AI integration
│       ├── storage.py            Supabase CRUD helpers
│       ├── session_store.py      Local JSON session persistence
│       ├── confidence_engine.py  Multi-factor confidence calculation
│       ├── verdict_aggregator.py 5-tier verdict system with guardrails
│       ├── baseline_quality.py   Personal baseline scoring
│       ├── followup_generator.py Follow-up question generation
│       ├── personal_routes.py    Personal text analysis endpoint
│       └── model/
│           ├── sachhAI_classifier.pkl   Trained VotingClassifier pipeline
│           └── model_meta.json          Training metrics + feature list
│
├── chrome-extension/             Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── popup.html / popup.js     Extension popup interface
│   ├── popup.css                 Extension styles
│   ├── background.js             Service worker
│   ├── content_script.js         Auth bridge (website → extension)
│   └── meet_cc_guard.js          Google Meet CC caption capture engine
│
├── meet-extension/               Plasmo-based Meet Overlay Extension
│   ├── contents/meet-overlay.tsx Full interview overlay for Google Meet
│   ├── popup.tsx                 Extension popup
│   └── package.json
│
├── .env.example                  Environment variable template
├── .gitignore                    Security-hardened gitignore
├── Dockerfile                    Production container
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **[Deepgram API key](https://console.deepgram.com/)** — free tier includes 200 minutes/month (required for transcription)
- **[Supabase project](https://supabase.com/)** — free tier available (required for data persistence)
- **[Winston AI API key](https://gowinston.ai/)** — optional (AI/plagiarism detection works without it)

### 1. Clone & Setup

```bash
git clone https://github.com/<your-username>/sacchAI.git
cd sacchAI/backend

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy the template
cp ../.env.example .env    # macOS/Linux
copy ..\.env.example .env  # Windows
```

Edit `backend/.env` and fill in your own keys — see `.env.example` for the full list with descriptions:

```env
# Required
DEEPGRAM_API_KEY=your_deepgram_api_key_here          # https://console.deepgram.com/
SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxxx.supabase.co # Your Supabase project URL
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6Ikp...     # Supabase anon/public key
JWT_SECRET=a1b2c3d4e5f6...                           # 64-char random hex (see below)

# Optional — the system works without these
WINSTON_AI_API_KEY=your_winston_ai_api_key_here      # https://gowinston.ai/
OPENAI_API_KEY=your_openai_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... # Suspicious verdict alerts
```

> **Generate a secure JWT secret:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
>
> ⚠️ **Never commit `backend/.env`** — it is gitignored. Only commit `.env.example` with placeholder values.

### 3. Setup Supabase Table

Create a `voice_data` table in your Supabase project:

```sql
CREATE TABLE voice_data (
  candidate_id TEXT PRIMARY KEY,
  personal TEXT,
  technical TEXT,
  analysis JSONB,
  submitted_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Start the Server

```bash
uvicorn server:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

### 5. Sign In (Demo / Admin Accounts)

The database auto-seeds default credentials on startup:
* **Demo HR Account**: Username: `hr1` | Password: `hr123`
* **Admin Account**: Username: `admin` | Password: Set by `ADMIN_PASSWORD` in `.env` (defaults to `admin123`)

### 6. Chrome Extension (Optional)

1. Open `chrome://extensions/`
2. Enable **Developer Mode**
3. Click **Load Unpacked** → select the `chrome-extension/` folder
4. Pin the SacchAI extension icon

### 6. Meet Extension (Optional)

```bash
cd meet-extension
npm install
npm run dev
```

Load the unpacked extension from `meet-extension/build/chrome-mv3-dev/`.

---

## 🧪 Training the ML Model

To retrain on the HC3 dataset (downloads ~150 MB automatically):

```bash
cd backend
python fetch_and_train.py
```

This downloads 5 HC3 splits from HuggingFace, extracts 29 features per pair, trains the ensemble, and saves `voice_module/model/sachhAI_classifier.pkl`. Restart the server to load the new model.

---

## 📡 API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/auth/login` | Authenticate and receive JWT token |
| `POST` | `/voice/text-compare` | Run full style-shift analysis on two text strings |
| `POST` | `/voice/transcribe-chunk` | Transcribe an audio blob via Deepgram |
| `POST` | `/voice/analyze-personal` | Analyze personal text and return baseline profile |
| `POST` | `/voice/plagiarism` | Submit text for Winston AI plagiarism + AI detection |
| `POST` | `/voice/plagiarism-check` | Quick inline plagiarism risk check |
| `POST` | `/voice/suggest-questions` | Generate follow-up probe questions |
| `POST` | `/voice/save-session` | Save a completed interview session |
| `GET` | `/voice/sessions` | List all saved sessions |
| `GET` | `/voice/candidates` | List candidates visible to authenticated user |
| `GET` | `/voice/candidate/{id}` | Get stored data for a specific candidate |
| `GET` | `/calibrate/meta` | Return model metadata (accuracy, features, samples) |
| `WS` | `/voice/stream` | Deepgram WebSocket proxy for live transcription |
| `WS` | `/voice/meet-analyze` | Live style analysis WebSocket for Meet integration |

Full interactive docs available at `http://localhost:8000/docs` (Swagger UI).

---

## 📊 Scoring Details

### Linguistic Style Divergence Index (LSDI)

11 linguistic features are compared between personal and technical responses, each weighted by their discrimination power:

| Feature | Weight | Signal |
|---------|--------|--------|
| Vocabulary level | 2.5 | Syllable count + long-word ratio |
| Flesch-Kincaid grade | 2.2 | Readability — higher in AI text |
| Sentence burstiness | 2.0 | CV of sentence lengths — AI text is uniform |
| Formality score | 2.0 | Composite of vocabulary, sentence length, fillers |
| Transition density | 2.0 | Formal connectors per word ("furthermore", "however") |
| Gunning Fog index | 1.8 | Complex-word readability |
| Hedging density | 1.8 | Epistemic hedge phrases ("it is worth noting") |
| Passive voice ratio | 1.5 | AI text uses ~3× more passive constructions |
| Grammar score | 1.2 | Disfluencies and fragment detection |
| Avg sentence length | 1.2 | Words per sentence |
| Filler ratio | 0.8 | Natural hesitation markers — inverse signal |

### ML Ensemble

- **Architecture**: `Pipeline(StandardScaler → VotingClassifier(LR + RF[300] + GB[200]))`
- **Training data**: HC3 (5 splits) + curated synthetic pairs — ~6,008 samples
- **CV accuracy**: 88.4% ± 0.5% (5-fold stratified)
- **Feature vector**: 29 dimensions (deltas, raw technical profile, raw personal profile, signal count)

### Score Blending

| Condition | Heuristic Weight | ML Weight |
|-----------|-----------------|-----------|
| 4+ strong signals | 85% | 15% |
| 2–3 strong signals | 70% | 30% |
| ML probability > 0.75 | max(heuristic, ML × 0.85) | — |
| Default | 50% | 50% |

---

## 🔒 Security

- **No secrets in source code** — All API keys loaded from environment variables only
- **`.env` is gitignored** — Secrets never enter version control
- **JWT authentication** — All API endpoints require valid tokens
- **Role-based access control** — Enforced at the Supabase query layer
- **No audio persistence** — Only transcribed text is stored; raw audio is discarded after transcription
- **Password hashing** — SHA-256 hashed credentials in the user store
- **CORS configured** — Restricted to known origins in production

---

## 🐳 Docker Deployment

```bash
docker build -t sacchAI .
docker run -p 7860:7860 --env-file backend/.env sacchAI
```

For Hugging Face Spaces: add each environment variable as a Secret in **Settings → Repository secrets**.

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- **[Deepgram](https://deepgram.com/)** — Nova-2 speech-to-text engine
- **[Hello-SimpleAI/HC3](https://huggingface.co/datasets/Hello-SimpleAI/HC3)** — Human vs ChatGPT dataset
- **[Supabase](https://supabase.com/)** — PostgreSQL backend
- **[Winston AI](https://gowinston.ai/)** — AI content detection

---

<div align="center">

*Built at NMIT, Bengaluru 🇮🇳*

**SacchAI** — *सच्चाई (Sacchāī) means "truth" in Hindi. Your interview's co-pilot for integrity.*

</div>
