con# SacchAI — Interview Integrity Co-Pilot
## Master Project Reference (Read this before touching any file)

---

## What This Project Is

SacchAI is an **interview authenticity detection system** for HR teams.
It detects whether a candidate's technical interview responses are genuinely their own or externally assisted (AI-generated / pre-written).

It works by:
1. Collecting a **personal round** response (casual, natural speech — establishes baseline)
2. Collecting a **technical round** response (formal, technical content)
3. Running 11 linguistic/acoustic features to compare the two and compute an authenticity score

---

## System Architecture

```
browser (frontend/interview.html)
        ↓ HTTP REST
backend/server.py (FastAPI, port 8000)
        ├── /voice/*       ← voice_module/routes.py
        │       ├── /record/personal   — transcribes audio via Deepgram
        │       ├── /record/technical  — transcribes audio via Deepgram
        │       ├── /text-compare      — runs style analysis (main analysis route)
        │       ├── /compare           — runs full analysis on stored audio transcripts
        │       ├── /plagiarism        — calls Winston AI for plagiarism + AI detection
        │       ├── /candidates        — lists all candidate IDs from Supabase
        │       └── /candidate/{id}    — get stored data for one candidate
        ├── /auth/*        ← auth_routes.py  (JWT login/register)
        └── /calibrate/*   ← calibration_routes.py (hidden from users)
```

---

## The 11 Analysis Parameters (Core of the system)

These are the 11 style dimensions compared between personal and technical responses.
ALL 11 MUST fire for full analysis. Weights in `calculate_style_shift()`:

| # | Parameter              | Weight | What it measures                                      |
|---|------------------------|--------|-------------------------------------------------------|
| 1 | vocabulary_level       | 2.5    | Syllable-weighted word complexity (0–100)             |
| 2 | flesch_kincaid         | 2.2    | FK Grade Level — higher = AI-like complex text        |
| 3 | formality_score        | 2.0    | Composite formality (vocab + sentence len + fillers)  |
| 4 | gunning_fog            | 1.8    | Fog index — penalises 3+ syllable words               |
| 5 | hedging_density        | 1.8    | Epistemic hedges ("it is worth noting", etc.)         |
| 6 | passive_voice_ratio    | 1.5    | AI uses ~3x more passive voice than natural speech    |
| 7 | grammar_score          | 1.2    | Penalises only genuine disfluencies, not short sents  |
| 8 | avg_sentence_len       | 1.2    | Average words per sentence                            |
| 9 | filler_ratio           | 0.8    | "um", "like", "you know" — drops in AI text           |
|10 | transition_density     | 2.0    | "however", "furthermore" — AI overuses these          |
|11 | sentence_burstiness    | 2.0    | CV of sentence lengths — AI is uniform (low CV)       |

**Additional signals (not in weight map but used for scoring):**
- `intra_style_var` — per-sentence vocabulary variance (mixed AI+human flag)
- `temporal_drift` — complexity spike mid/late answer (AI entered partway through)
- `cosine_similarity` — low overlap between personal/technical vocabularies
- `ml_probability` — trained classifier on HC3 dataset (sachhAI_classifier.pkl)

---

## Key Files

### Backend
| File | Purpose |
|------|---------|
| `backend/server.py` | FastAPI app, CORS, route mounting, static serving, lifespan ML training |
| `backend/voice_module/routes.py` | All `/voice/*` API endpoints |
| `backend/voice_module/style_comparator.py` | THE CORE — all 11 parameter analysis engine |
| `backend/voice_module/transcriber.py` | Deepgram Nova-2 audio transcription + audio signals |
| `backend/voice_module/plagiarism_client.py` | Winston AI plagiarism + AI content detection |
| `backend/voice_module/storage.py` | Supabase persistence (voice_data table) |
| `backend/voice_module/streaming.py` | WebSocket streaming transcription |
| `backend/voice_module/model/sachhAI_classifier.pkl` | Trained ML model (sklearn pipeline) |
| `backend/train_model.py` | Model training script |
| `backend/fetch_and_train.py` | Downloads HC3 dataset and trains model |
| `backend/calibration_routes.py` | Hidden calibration/test endpoints |
| `backend/auth_routes.py` | JWT auth (login, register, users) |
| `backend/.env` | API keys — Deepgram, Winston AI, Supabase, JWT secret |
| `backend/requirements.txt` | Python deps |

### Frontend
| File | Purpose |
|------|---------|
| `frontend/interview.html` | Main app (~5228 lines) — all UI + JS in one file |
| `frontend/landing.html` | Landing/marketing page |
| `frontend/echo-insight.css` | Shared CSS |

### Chrome Extension
| File | Purpose |
|------|---------|
| `chrome-extension/manifest.json` | Extension manifest |
| `chrome-extension/popup.js` | Extension popup logic |
| `chrome-extension/content_script.js` | Content script for in-page injection |

---

## Environment Keys (backend/.env)

```
OPENAI_API_KEY=...          (legacy, not actively used)
DEEPGRAM_API_KEY=...        (transcription — Nova-2 model)
WINSTON_AI_API_KEY=...      (plagiarism + AI content detection)
SUPABASE_URL=...            (database)
SUPABASE_KEY=...            (anon key)
JWT_SECRET=...              (auth token signing)
JWT_EXPIRE_HOURS=24
SLACK_WEBHOOK_URL=          (optional — alerts on suspicious verdicts)
ADMIN_EMAIL=admin@system.local
ADMIN_PASSWORD=<your_admin_password>
```

---

## How to Start the Backend

```powershell
cd e:\AntiGravity\Interview-new\backend
venv\Scripts\uvicorn server:app --reload --port 8000
```

Access at: http://localhost:8000
API docs: http://localhost:8000/docs

---

## Analysis Flow (Step by Step)

1. User enters Candidate ID
2. Records/types **Personal response** → saved via `save_response(id, "personal", text)`
3. Records/types **Technical response** → saved via `save_response(id, "technical", text)`
4. Clicks "Analyse" → frontend POSTs to `/voice/text-compare`
   - Body: `{candidate_id, personal, technical, personal_signals, technical_signals}`
   - Returns: full analysis dict (all 11 params, flags, scores, ML prob, etc.)
5. Frontend renders results section (scores grid, flags chips, summary box, breakdown chart)
6. Frontend separately calls `/voice/plagiarism` for Winston AI check (takes 10–60s)
   - Returns: `{personal: {plagiarism, ai_detection}, technical: {plagiarism, ai_detection}}`
   - Updates verdict banner and plagiarism tile

---

## Known Issues & Fixes Applied

### Issue 1: Encoding Corruption in style_comparator.py
- **Status:** FIXED (but check the file — "â€"" should be "—")
- **Root cause:** File was saved with UTF-8 BOM or mojibake issue
- **Symptom:** Flag messages show "A⁷ᴬ⁰" or "â€"" instead of "—" em-dashes
- **Fix:** Replace all corrupted char sequences in style_comparator.py with proper Unicode

### Issue 2: text-compare route missing verdict field
- **Status:** NEEDS FIX
- **Root cause:** `text_compare()` in routes.py calls only `calculate_style_shift()`, not
  `_run_full_analysis()`. So the response has no `verdict` key.
- **Symptom:** Frontend may crash or show wrong verdict if it expects `analysis.verdict`
- **Fix:** Either add verdict computation in text_compare, or call _run_full_analysis

### Issue 3: Analysis response time
- **Requirement:** Analysis should take 2–5 seconds (not less than 2s, not more than 5s)
- **Current:** Style shift alone is <1s. With plagiarism it's 10–60s.
- **Fix:** The text-compare endpoint should return in 2–5s (style shift + ML).
  Plagiarism check runs separately (async, shows loading).
  Add artificial min 2s delay if style analysis completes too fast.

### Issue 4: save_response clears analysis cache
- **Status:** Known behavior — intentional. When new text is saved, old cached analysis is cleared.
  This is correct to avoid stale results.

### Issue 5: Supabase storage
- **get_candidate()** only returns fields in VALID_TYPES = {"personal", "technical", "analysis"}
- Does NOT return `submitted_by` from the candidate fetch
- `list_candidates()` has a separate query for `submitted_by`

---

## Verdict Logic

### Backend (routes.py `compute_final_verdict`)
| Style Shift | Plag Score | Verdict |
|------------|------------|---------|
| VERY HIGH  | any        | HIGHLY SUSPICIOUS |
| HIGH       | >= 40%     | HIGHLY SUSPICIOUS |
| HIGH       | < 40%      | SUSPICIOUS |
| any        | >= 40%     | SUSPICIOUS |
| MODERATE   | >= 20%     | NEEDS REVIEW |
| MODERATE   | < 20%      | NEEDS REVIEW |
| LOW        | < 20%      | GENUINE |

### Frontend (interview.html `computeVerdict`)
Slightly different 4-tier: Genuine, Slight Concern, Suspicious, Highly Suspicious

---

## ML Model Details

- **Type:** Sklearn Pipeline (scaler + RandomForest/GradientBoosting)
- **Features (29 total):**
  - 15 deltas (t - p for each feature)
  - 9 raw technical profile values
  - 4 raw personal profile values
  - 1 composite (strong_signal_count)
- **Training data:** HC3 dataset (human vs ChatGPT responses)
- **Location:** `backend/voice_module/model/sachhAI_classifier.pkl`
- **Loading:** At import time in style_comparator.py via `_load_model()`
- **Fallback:** If model missing → heuristic-only mode (`_analysis_mode: "heuristic_enhanced"`)

---

## Analysis Response Schema (from /voice/text-compare)

```json
{
  "candidate_id": "...",
  "personal_preview": "...",
  "technical_preview": "...",
  "analysis": {
    "authenticity_score": 15.3,     // 0-100, higher = more authentic
    "lsdi_score": 90.9,             // Linguistic Stability Divergence Index (0-100)
    "style_shift": "VERY HIGH",     // LOW | MODERATE | HIGH | VERY HIGH
    "shift_score": 90.9,            // alias for lsdi_score
    "confidence_interval": {...},
    "confidence_level": "Low",
    "flags": ["..."],               // human-readable flag messages
    "summary": "...",               // one-paragraph verdict summary
    "personal_profile": {...},      // all 11 feature values for personal round
    "technical_profile": {...},     // all 11 feature values for technical round
    "shift_breakdown": {...},       // per-feature shift scores
    "strong_signal_count": 9,       // how many of 11 signals fired
    "cosine_similarity": 0.04,
    "ml_probability": 0.39,
    "temporal_drift": {...},
    "fairness_adjusted": false,
    "_analysis_mode": "model_augmented"
  }
}
```

---

## Plagiarism Response Schema (from /voice/plagiarism)

```json
{
  "personal": {
    "plagiarism": {"score": 2.3, "sources": [...]},
    "ai_detection": {"score": 15.0, "error": null}
  },
  "technical": {
    "plagiarism": {"score": 45.2, "sources": [...]},
    "ai_detection": {"score": 87.5, "error": null}
  }
}
```

---

## Timing Requirements

- `/voice/text-compare` must respond in **2–5 seconds** (style analysis + ML)
- `/voice/plagiarism` runs separately and can take **10–60 seconds** (Winston AI is slow)
- Frontend shows plagiarism as "Checking..." with spinner until the separate call completes

---

## Last Updated
2026-05-10 — Created from full project audit
