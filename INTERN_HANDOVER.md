# 🎙️ SachhAI — Intern Handover Document
### Complete Project Access & Continuation Guide
**Last Updated:** June 29, 2026 | **Prepared by:** Project Lead (via Antigravity)

---

> [!IMPORTANT]
> **READ THIS ENTIRE DOCUMENT BEFORE TOUCHING ANY CODE.**
> This document contains every credential, URL, architecture detail, and known issue you need. Treat it like a classified briefing.

---

## 1. What Is This Project?

**SachhAI** *(Hindi: सच्चाई = "truth")* is an **Interview Authenticity Detection Platform** built for HR teams.

**The core problem it solves:** Candidates increasingly use AI tools (ChatGPT, Claude) to answer technical interview questions in real-time. Traditional plagiarism scanners don't catch AI-generated content because there's no "source." SachhAI detects this by comparing how a candidate's *natural communication style* shifts between a casual personal introduction and a structured technical response.

**How it works (briefly):**
1. HR records/transcribes the **Personal Round** (baseline — "tell me about yourself")
2. HR records/transcribes the **Technical Round** (live or post-interview)
3. SachhAI runs 11 linguistic features + an ML classifier across both texts
4. Returns a verdict: Genuine / Needs Review / Suspicious / Highly Suspicious

---

## 2. Repository & Deployment Access

### GitHub (Primary Code Repo)

| Detail | Value |
|--------|-------|
| **Repo URL (old)** | https://github.com/1nt23is136naaga-cyber/audio-transcription-plagiarism-checker |
| **Repo URL (new — moved)** | https://github.com/naagasumukh8/SacchAI-Interview_Integrity_Co-Pilot |
| **Branch** | `main` |
| **Visibility** | Private |

> [!WARNING]
> The GitHub repo has moved. Update your git remote after cloning:
> ```bash
> git remote set-url origin https://github.com/naagasumukh8/SacchAI-Interview_Integrity_Co-Pilot.git
> ```

### Hugging Face Spaces (Live Production)

| Detail | Value |
|--------|-------|
| **Space URL** | https://huggingface.co/spaces/Naagazz/interview-checker |
| **Live App URL** | https://naagazz-interview-checker.hf.space |
| **Remote name** | `space` |
| **Tech** | Docker (see `Dockerfile`) |
| **Port** | 7860 |

To deploy to HF Spaces:
```bash
git push space main
```

---

## 3. Environment Variables & API Keys

> [!CAUTION]
> These are the LIVE production credentials. Rotate them if you suspect compromise. Never commit them to any public repo.

Copy `e:\AntiGravity\Interview-new\.env.example` to `backend/.env` and fill in:

```env
# ── TRANSCRIPTION (Required) ─────────────────────────────────────────────────
DEEPGRAM_API_KEY=
# Sign up: https://console.deepgram.com/
# Free tier: 200 min/month | Used for: Nova-2 model, WebSocket streaming

# ── AI/PLAGIARISM DETECTION (Optional but recommended) ───────────────────────
WINSTON_AI_API_KEY=
# Sign up: https://gowinston.ai/
# Used for: /voice/plagiarism endpoint — AI content detection + plagiarism scan

# ── OPENAI (Legacy — not actively used in core analysis) ─────────────────────
OPENAI_API_KEY=

# ── DATABASE (Required for persistence) ──────────────────────────────────────
SUPABASE_URL=
SUPABASE_KEY=
# Dashboard: https://supabase.com/dashboard/project/ebkkhlafvzkozoiwfqls

# ── AUTHENTICATION ────────────────────────────────────────────────────────────
JWT_SECRET=7f3a9c2e1b8d4f6a0e5c3b7d9f1a2e4c8b6d0f3a5e7c9b1d3f5a7c9e1b3d5f7
JWT_EXPIRE_HOURS=24

# ── OPTIONAL ALERTS ──────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL=  # empty — configure if you want suspicious verdict Slack alerts

# ── DEFAULT ADMIN ─────────────────────────────────────────────────────────────
ADMIN_EMAIL=admin@system.local
ADMIN_PASSWORD=admin123
```

### Meet Extension — Hardcoded Deepgram Key (Solo Mode)

> [!WARNING]
> There is a **hardcoded Deepgram API key** inside `meet-extension/contents/meet-overlay.tsx` at **line 448**:
> ```ts
> const DEEPGRAM_KEY = "5e0f6a21c7ff5a576e38c87c99e6db10e55c4090"
> ```
> This is a **different key** from the backend one and is used only for Solo Mode direct Deepgram WebSocket in the browser extension. Move this to a secure config or extension storage if going to production.

---

## 4. Database Setup (Supabase)

### Project Details

| Detail | Value |
|--------|-------|
| **Supabase Project ID** | `ebkkhlafvzkozoiwfqls` |
| **Dashboard URL** | https://supabase.com/dashboard/project/ebkkhlafvzkozoiwfqls |
| **Table Editor** | https://supabase.com/dashboard/project/ebkkhlafvzkozoiwfqls/editor |
| **SQL Editor** | https://supabase.com/dashboard/project/ebkkhlafvzkozoiwfqls/sql/new |

### The `voice_data` Table Schema

This is the ONLY table SachhAI uses. Run this SQL in the Supabase SQL Editor if setting up fresh:

```sql
CREATE TABLE IF NOT EXISTS voice_data (
  candidate_id   TEXT PRIMARY KEY,
  personal       TEXT,                        -- Personal round transcript
  technical      TEXT,                        -- Technical round transcript
  analysis       JSONB,                       -- Full analysis result (all 11 params)
  submitted_by   TEXT,                        -- HR user who ran the interview
  candidate_name TEXT,                        -- Optional: display name
  role           TEXT,                        -- Optional: job role being interviewed for
  interviewer    TEXT,                        -- Optional: interviewer name
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security (RLS)
ALTER TABLE voice_data ENABLE ROW LEVEL SECURITY;

-- Policy: anon key can read/write (the backend uses anon key)
CREATE POLICY "allow_all_to_anon" ON voice_data
  FOR ALL USING (true) WITH CHECK (true);
```

> [!NOTE]
> The code in `storage.py` gracefully degrades if `submitted_by` column doesn't exist, but you should have it. The `enable_rls.py` script in the root can also be run to enable RLS policies.

---

## 5. Default User Accounts (backend/users.json)

> [!NOTE]
> `backend/users.json` is gitignored (runtime data). On a fresh clone, you need to recreate it. The backend creates no users on startup — create the file manually.

Create `backend/users.json`:
```json
[
  {
    "username": "admin",
    "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",
    "role": "admin",
    "display_name": "Administrator"
  },
  {
    "username": "hr1",
    "password_hash": "070a3b5a5257aa2d87e7e2e1d8e10d8d2a3d2f3f0e5f6a7b8c9d0e1f2a3b4c5d",
    "role": "hr",
    "display_name": "HR User 1"
  }
]
```

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | Admin — sees all candidates, can manage HR users |
| `hr1` | `hr123` | HR — sees only their own interviews |
| `hr2` | `hr123` | HR — sees only their own interviews |

> [!IMPORTANT]
> Passwords are stored as **SHA-256 hashes**. To hash a new password:
> ```python
> import hashlib
> print(hashlib.sha256("yourpassword".encode()).hexdigest())
> ```
> The admin can also add users via the dashboard UI at `/dashboard` → Employees tab.

---

## 6. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SACHHÁI SYSTEM                                │
│                                                                         │
│  ┌──────────────┐   ┌─────────────────┐   ┌───────────────────────┐   │
│  │  Chrome Ext  │   │   Meet Overlay   │   │   Web Frontend        │   │
│  │  (MV3)       │   │   (Plasmo/React) │   │   (Vanilla HTML/JS)   │   │
│  │ popup.js     │   │ meet-overlay.tsx │   │ interview.html        │   │
│  │ bg.js        │   │ popup.tsx        │   │ dashboard.html        │   │
│  │ content.js   │   │                  │   │ landing.html          │   │
│  │ meet_cc.js   │   │                  │   │ login.html            │   │
│  └──────┬───────┘   └────────┬─────────┘   └──────────┬────────────┘   │
│         │                   │                          │                │
│         └───────────────────┴──────────────────────────┘                │
│                                      │ HTTP REST / WebSocket            │
│                                      ▼                                  │
│               ┌──────────────────────────────────┐                      │
│               │   FastAPI Backend (server.py)     │                      │
│               │   Port 8000 (local) / 7860 (HF)  │                      │
│               │                                  │                      │
│               │   /voice/*  — voice_module/       │                      │
│               │   /auth/*   — auth_routes.py      │                      │
│               │   /calibrate/* — calib_routes.py  │                      │
│               └──────────────────────────────────┘                      │
│                        │              │              │                   │
│               ┌────────┴─┐    ┌───────┴──┐   ┌──────┴───────┐          │
│               │ Deepgram │    │  Winston  │   │   Supabase   │          │
│               │ Nova-2   │    │  AI API   │   │ PostgreSQL   │          │
│               │(STT/WS)  │    │(Plagiarism│   │(voice_data)  │          │
│               └──────────┘    └───────────┘   └──────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Full File Map

### Root
| File | Purpose |
|------|---------|
| `.env.example` | Template for backend environment variables |
| `.gitignore` | Hardened — excludes `.env`, `venv/`, model `.pkl`, runtime JSON, scratch files |
| `Dockerfile` | Production Docker container (used by HF Spaces) |
| `render.yaml` | Render.com deployment config |
| `SACHHAIPROJECT.md` | **Master project reference** — read this first when debugging |
| `README.md` | Public-facing documentation |
| `enable_rls.py` | Script to enable Supabase Row Level Security |

### Backend (`backend/`)
| File | Purpose |
|------|---------|
| `server.py` | FastAPI app entry point, CORS, route mounting, ML background training |
| `auth_routes.py` | JWT login, user management (`/auth/*`) |
| `calibration_routes.py` | Hidden ML model metadata endpoints (`/calibrate/*`) |
| `train_model.py` | Manual ML model training script |
| `fetch_and_train.py` | Downloads HC3 dataset from HuggingFace + trains model automatically |
| `generate_pdf.py` | Batch test case PDF generator |
| `rate_limiter.py` | Simple in-memory request rate limiter |
| `requirements.txt` | Python dependencies (pip install -r requirements.txt) |
| `.env` | **GITIGNORED** — live API keys (see Section 3) |
| `users.json` | **GITIGNORED** — user accounts with hashed passwords |
| `voice_data.json` | **GITIGNORED** — local session fallback (runtime data) |
| `meet_sessions.json` | **GITIGNORED** — Google Meet session log (runtime data) |

### Voice Module (`backend/voice_module/`)
| File | Purpose |
|------|---------|
| `routes.py` | ALL `/voice/*` REST endpoints |
| `streaming.py` | WebSocket endpoints — Deepgram proxy + Meet live analysis |
| `style_comparator.py` | **THE CORE** — 11-feature linguistic engine + ML inference |
| `transcriber.py` | Deepgram Nova-2 batch audio transcription |
| `plagiarism_client.py` | Winston AI plagiarism + AI content detection |
| `storage.py` | Supabase CRUD — save/get/list/delete candidates |
| `session_store.py` | Local JSON session persistence (fallback) |
| `confidence_engine.py` | Multi-factor confidence calculation |
| `verdict_aggregator.py` | 5-tier verdict system with guardrails |
| `baseline_quality.py` | Personal baseline scoring |
| `followup_generator.py` | Follow-up question generation |
| `personal_routes.py` | Personal round text analysis endpoint |
| `credibility_checker.py` | Answer credibility verification |
| `model/sachhAI_classifier.pkl` | **Trained ML model** (6.3 MB sklearn VotingClassifier) |
| `model/model_meta.json` | Model training metrics & feature names |

### Frontend (`frontend/`)
| File | Purpose |
|------|---------|
| `landing.html` | Landing/marketing page |
| `login.html` | Login portal |
| `interview.html` | **Main app** (~200KB, all UI + JS in one file) |
| `dashboard.html` | Admin dashboard (~77KB) |
| `echo-insight.css` | Shared CSS styles |
| `enhancements.css` | Additional UI styles |
| `interactions.js` | Shared JS interactions |

### Chrome Extension (`chrome-extension/`)
| File | Purpose |
|------|---------|
| `manifest.json` | Extension manifest (MV3) |
| `popup.html / popup.js / popup.css` | Extension popup interface (full interview flow) |
| `background.js` | Service worker |
| `content_script.js` | Auth bridge (website ↔ extension) |
| `meet_cc_guard.js` | Google Meet CC caption capture engine (heavily filtered) |

### Meet Extension (`meet-extension/`) — Plasmo/React
| File | Purpose |
|------|---------|
| `contents/meet-overlay.tsx` | **Full glassmorphic overlay** for Google Meet (2289 lines React) |
| `popup.tsx` | Extension popup |
| `package.json` | Dependencies (Plasmo 0.90.5, React 18) |
| `tsconfig.json` | TypeScript config |

---

## 8. Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ (for Meet Extension)
- Git

### 1. Clone & Install Backend

```powershell
git clone https://github.com/naagasumukh8/SacchAI-Interview_Integrity_Co-Pilot.git
cd SacchAI-Interview_Integrity_Co-Pilot

# Create venv
cd backend
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### 2. Create Environment File

```powershell
# From the repo root
copy .env.example backend\.env
# Then edit backend\.env with the credentials from Section 3
```

### 3. Create users.json

Create `backend/users.json` with the content from Section 5.

### 4. Start the Server

```powershell
cd backend
venv\Scripts\uvicorn server:app --reload --port 8000
```

Visit:
- App: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Login: http://localhost:8000/login

### 5. Install Chrome Extension

1. Go to `chrome://extensions/`
2. Enable **Developer Mode** (top right toggle)
3. Click **Load Unpacked**
4. Select the `chrome-extension/` folder
5. Pin the SachhAI icon in your Chrome toolbar

### 6. Install Meet Extension (Optional)

```powershell
cd meet-extension
npm install
npm run dev
```
Load unpacked from `meet-extension/build/chrome-mv3-dev/`

---

## 9. API Reference

Base URL: `http://localhost:8000` (local) or `https://naagazz-interview-checker.hf.space` (production)

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET | `/health` | No | Server liveness check |
| POST | `/auth/login` | No | Login → returns JWT token |
| GET | `/auth/me` | JWT | Get current user info |
| GET | `/auth/employees` | Admin JWT | List HR employees |
| POST | `/auth/employees` | Admin JWT | Add HR employee |
| DELETE | `/auth/employees/{username}` | Admin JWT | Remove HR employee |
| POST | `/voice/text-compare` | Optional | **Main analysis** — runs 11 features + ML on 2 texts |
| POST | `/voice/transcribe-chunk` | No | Transcribe audio blob via Deepgram |
| POST | `/voice/analyze-personal` | No | Analyze personal text, return baseline profile |
| POST | `/voice/plagiarism` | No | Winston AI plagiarism + AI detection |
| POST | `/voice/plagiarism-check` | No | Quick inline plagiarism risk check |
| POST | `/voice/suggest-questions` | No | Generate follow-up probe questions |
| POST | `/voice/save-session` | JWT | Save completed interview session |
| GET | `/voice/sessions` | JWT | List saved sessions |
| GET | `/voice/candidates` | JWT | List candidates (role-filtered) |
| GET | `/voice/candidate/{id}` | JWT | Get candidate data |
| GET | `/calibrate/meta` | No | ML model accuracy metrics |
| WS | `/voice/stream` | No | Deepgram WebSocket proxy (live mic) |
| WS | `/voice/meet-analyze` | No | Live analysis WebSocket (Meet integration) |

### Key Request/Response Examples

**`POST /voice/text-compare`**
```json
// Request
{
  "candidate_id": "CAND_001",
  "personal": "Hi so yeah I grew up in Bangalore and basically...",
  "technical": "Microservices architecture fundamentally decouples system components..."
}

// Response
{
  "candidate_id": "CAND_001",
  "analysis": {
    "authenticity_score": 15.3,   // 0-100, HIGHER = more authentic (less AI-like shift)
    "lsdi_score": 90.9,           // Linguistic Style Divergence Index (0-100, HIGHER = more suspicious)
    "style_shift": "VERY HIGH",   // LOW | MODERATE | HIGH | VERY HIGH
    "flags": ["Extreme vocabulary jump", "AI hedge phrases detected"],
    "ml_probability": 0.39,       // ML classifier prob of AI assistance
    "strong_signal_count": 9,     // Out of 11 features
    "summary": "..."
  }
}
```

---

## 10. The 11 Analysis Features

This is the core of SachhAI. ALL 11 must fire for full analysis.

| # | Feature | Weight | What It Measures |
|---|---------|--------|------------------|
| 1 | `vocabulary_level` | 2.5 | Syllable-weighted word complexity (0–100) |
| 2 | `flesch_kincaid` | 2.2 | FK Grade Level — higher = AI-like complex text |
| 3 | `formality_score` | 2.0 | Composite formality (vocab + sentence len + fillers) |
| 4 | `gunning_fog` | 1.8 | Fog index — penalises 3+ syllable words |
| 5 | `hedging_density` | 1.8 | Epistemic hedges ("it is worth noting") |
| 6 | `passive_voice_ratio` | 1.5 | AI uses ~3x more passive voice than humans |
| 7 | `grammar_score` | 1.2 | Penalises genuine disfluencies, not short sentences |
| 8 | `avg_sentence_len` | 1.2 | Average words per sentence |
| 9 | `filler_ratio` | 0.8 | "um", "like", "you know" — drops in AI text |
| 10 | `transition_density` | 2.0 | "however", "furthermore" — AI overuses these |
| 11 | `sentence_burstiness` | 2.0 | CV of sentence lengths — AI is uniform (low CV) |

**Additional signals:**
- `intra_style_var` — per-sentence vocabulary variance (mixed AI+human)
- `temporal_drift` — complexity spike mid/late answer
- `cosine_similarity` — vocabulary overlap between rounds
- `ml_probability` — trained VotingClassifier on HC3 dataset

---

## 11. ML Model Details

| Detail | Value |
|--------|-------|
| **Architecture** | `Pipeline(StandardScaler → VotingClassifier(LR + RF[300] + GB[200]))` |
| **File** | `backend/voice_module/model/sachhAI_classifier.pkl` (6.3 MB) |
| **Training data** | HC3 dataset (5 splits) — ~6,008 human vs ChatGPT pairs |
| **CV Accuracy** | 88.4% ± 0.5% (5-fold stratified) |
| **Features** | 29 dimensions (deltas, raw profiles, signal count) |
| **Fallback** | If `.pkl` missing → heuristic-only mode (`_analysis_mode: "heuristic_enhanced"`) |

**To retrain the model:**
```powershell
cd backend
venv\Scripts\activate
python fetch_and_train.py
```
This downloads ~150MB of HC3 data from HuggingFace and saves a new `.pkl`. Restart the server after.

> [!NOTE]
> The HC3 `.jsonl` files in `backend/voice_module/model/` are gitignored (they're ~70MB combined). They are re-downloaded automatically by `fetch_and_train.py`.

---

## 12. Known Issues & Bugs (Must Fix)

### 🔴 Bug 1: `/voice/text-compare` Missing `verdict` Field
**Status:** Needs fix
**File:** `backend/voice_module/routes.py` — `text_compare()` function
**Problem:** `text_compare()` calls only `calculate_style_shift()`, NOT `_run_full_analysis()`. So the response has no `verdict` key.
**Symptom:** Frontend may crash or show wrong verdict if it expects `analysis.verdict`
**Fix:** In `routes.py`, add verdict computation after style shift:
```python
from voice_module.verdict_aggregator import compute_final_verdict
result["verdict"] = compute_final_verdict(result["style_shift"], plag_score=0)
```

### 🟡 Bug 2: Encoding Corruption in `style_comparator.py`
**Status:** Fixed in latest commit (verify)
**Problem:** File was saved with UTF-8 BOM or mojibake — "—" appeared as "â€"" in flag messages
**Fix:** All occurrences of `â€"` or similar should be `—` (em-dash)
**How to check:** `grep "â€" backend/voice_module/style_comparator.py`

### 🟡 Bug 3: Analysis Response Time
**Requirement:** `/voice/text-compare` should return in 2–5 seconds (feels credible to HR users)
**Current:** Style shift alone is < 1s (too fast — feels like it's not working)
**Fix needed:** Add artificial minimum 2-second delay if style analysis completes too fast
```python
import asyncio
await asyncio.sleep(max(0, 2.0 - elapsed_time))
```

### 🟡 Bug 4: Hardcoded Deepgram Key in Meet Extension
**File:** `meet-extension/contents/meet-overlay.tsx` line 448
**Risk:** Key exposed in extension bundle
**Fix:** Move to `chrome.storage.local` or use the backend proxy at `/voice/stream`

---

## 13. Verdict Logic

### Backend (`routes.py → compute_final_verdict`)
| Style Shift | Plagiarism Score | Verdict |
|-------------|-----------------|---------|
| VERY HIGH | any | HIGHLY SUSPICIOUS |
| HIGH | ≥ 40% | HIGHLY SUSPICIOUS |
| HIGH | < 40% | SUSPICIOUS |
| any | ≥ 40% | SUSPICIOUS |
| MODERATE | ≥ 20% | NEEDS REVIEW |
| MODERATE | < 20% | NEEDS REVIEW |
| LOW | < 20% | GENUINE |

### Frontend (`interview.html → computeVerdict`)
Slightly different 4-tier: Genuine, Slight Concern, Suspicious, Highly Suspicious

> [!WARNING]
> There is a **mismatch** between backend and frontend verdict categories. The frontend has "Slight Concern" and "Low Risk" which the backend doesn't return. This needs to be unified in a future fix.

---

## 14. Deployment

### Option A: Docker (Recommended for production)

```bash
docker build -t sachhAI .
docker run -p 7860:7860 --env-file backend/.env sachhAI
```

### Option B: Hugging Face Spaces (Current Production)

1. Set secrets in HF Space settings: `DEEPGRAM_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET`, `WINSTON_AI_API_KEY`
2. `git push space main`
3. HF Spaces auto-builds and deploys from `Dockerfile`

### Option C: Render.com

Config is already in `render.yaml`. Connect the GitHub repo to Render, set env vars via the dashboard.

---

## 15. What's NOT in Git & Why

> [!IMPORTANT]
> The following things are intentionally excluded from the repository. The intern MUST recreate them manually.

| What | Why Not In Git | How to Recreate |
|------|---------------|-----------------|
| `backend/.env` | Contains live API keys | Use Section 3 of this doc |
| `backend/users.json` | Runtime user data | Use Section 5 of this doc |
| `backend/voice_data.json` | Runtime session data | Created automatically on first run |
| `backend/meet_sessions.json` | Runtime Meet sessions | Created automatically on first run |
| `backend/voice_module/model/sachhAI_classifier.pkl` | 6.3MB binary — gitignored | Run `python fetch_and_train.py` OR download from HF Space |
| `backend/voice_module/model/hc3_*.jsonl` | HC3 dataset files (~70MB total) | Downloaded by `fetch_and_train.py` automatically |
| `meet-extension/node_modules/` | npm packages | Run `npm install` in `meet-extension/` |
| `backend/venv/` | Python virtualenv | Run `python -m venv venv && pip install -r requirements.txt` |
| `Report_INTERVIEW/` | Generated PDF reports | Generated at runtime |
| Supabase database schema | Not a file — it's in the cloud | SQL in Section 4 |

---

## 16. External Services Dashboard URLs

| Service | Dashboard | What It's For |
|---------|-----------|---------------|
| **Supabase** | https://supabase.com/dashboard/project/ebkkhlafvzkozoiwfqls | Database — view/query `voice_data` table |
| **Deepgram** | https://console.deepgram.com/ | Audio transcription — check usage & quota |
| **Winston AI** | https://gowinston.ai/dashboard | Plagiarism/AI detection — check API usage |
| **HF Spaces** | https://huggingface.co/spaces/Naagazz/interview-checker | Production deployment — logs, restart |
| **OpenAI** | https://platform.openai.com/ | Legacy key — not actively used in core flow |

---

## 17. Feature Completion Status

| Feature | Status | Notes |
|---------|--------|-------|
| Personal round recording (mic) | ✅ Done | Deepgram Nova-2 via MediaRecorder |
| Technical round live analysis | ✅ Done | WebSocket + 20s style checks |
| 11-feature linguistic engine | ✅ Done | `style_comparator.py` |
| ML classifier (VotingClassifier) | ✅ Done | 88.4% CV accuracy |
| Temporal drift detection | ✅ Done | Mid-answer style spike detection |
| Winston AI plagiarism check | ✅ Done | Async — shows "Checking..." while loading |
| JWT authentication | ✅ Done | 12-hour tokens, role-based |
| Admin dashboard | ✅ Done | Candidate list, employee management |
| Supabase persistence | ✅ Done | `voice_data` table |
| PDF export | ✅ Done | Client-side generation |
| Chrome Extension | ✅ Done | Full interview flow in browser |
| Google Meet overlay (Plasmo) | ✅ Done | Real-time glassmorphic overlay |
| Follow-up question generator | ✅ Done | Context-aware probe questions |
| Credibility checker | ✅ Done | Answer fact-checking module |
| `verdict` field in text-compare | ❌ Bug | See Known Issues #1 |
| Google Calendar integration | ⏳ Planned | Architecture ready, not built |
| AI assistant (voice, WhatsApp) | ⏳ Future | Post-MVP |

---

## 18. Quick Reference Commands

```powershell
# Start backend (from backend/ dir with venv active)
uvicorn server:app --reload --port 8000

# Train/retrain ML model
python fetch_and_train.py

# Run backend tests
python -m pytest test_api.py -v

# Push to GitHub
git push origin main

# Deploy to Hugging Face Spaces
git push space main

# Check what's staged / unstaged
git status

# Build Meet extension for production
cd meet-extension
npm run build
```

---

## 19. Important Architecture Decisions (Don't Change These)

1. **All business logic stays in the FastAPI backend** — never move analysis into n8n or the frontend
2. **`.pkl` model is loaded at import time** — if missing, falls back to heuristic-only mode gracefully
3. **Plagiarism check (`/voice/plagiarism`) runs separately from style analysis** — it's slow (10–60s) and must be async
4. **Supabase uses the `anon` key** — RLS policies control access, not the key type
5. **`users.json` is the auth source of truth** — not Supabase — this is intentional for now
6. **Both `/voice/text-compare` AND `/voice/compare` exist** — text-compare is for typed text, compare is for stored audio transcripts
7. **The style analysis must NOT take more than 5 seconds** — add delay if too fast to maintain UX credibility

---

*Built at NMIT, Bengaluru 🇮🇳 — SachhAI means "truth" in Hindi*
