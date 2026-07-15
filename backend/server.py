"""
server.py — SachhAI API

Runs the FastAPI app with CORS, serves interview.html, and mounts
the voice_module router (transcription + style comparison + plagiarism).

Local:
    cd backend && uvicorn server:app --reload --port 8000

Docker / Hugging Face:
    uvicorn backend.server:app --host 0.0.0.0 --port 7860
"""

import sys
import os
from pathlib import Path

# Load .env from backend directory
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

import logging
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _train_model_background():
    """Train ML model in background if sachhAI_classifier.pkl is missing."""
    model_path = Path(__file__).parent / "voice_module" / "model" / "sachhAI_classifier.pkl"
    if model_path.exists():
        logger.info("[startup] ML model already present — skipping training.")
        return
    logger.info("[startup] No ML model found — starting background training (fetch_and_train.py)...")
    try:
        # Run the training script in the same Python interpreter
        import runpy
        train_script = Path(__file__).parent / "fetch_and_train.py"
        if train_script.exists():
            runpy.run_path(str(train_script), run_name="__main__")
            logger.info("[startup] Background training complete.")
        else:
            logger.warning("[startup] fetch_and_train.py not found — running in heuristic mode only.")
    except Exception as exc:
        logger.error("[startup] Background training failed: %s", exc)

def _keep_alive():
    """Ping /health every 4 minutes to prevent HF free tier from sleeping."""
    import time, urllib.request
    time.sleep(30)   # wait for server to be fully up
    while True:
        try:
            urllib.request.urlopen("http://localhost:7860/health", timeout=5)
            logger.info("[keep-alive] pinged /health — space stays active")
        except Exception as e:
            logger.debug("[keep-alive] ping failed (ok on local): %s", e)
        time.sleep(240)   # every 4 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start model training in background thread — server is live immediately
    t = threading.Thread(target=_train_model_background, daemon=True)
    t.start()
    # Keep-alive: prevent HF free tier from sleeping
    ka = threading.Thread(target=_keep_alive, daemon=True)
    ka.start()
    yield

app = FastAPI(title="SachhAI", lifespan=lifespan)

# ── Security Headers (Helmet Equivalent) Middleware ───────────────────────────
from fastapi.responses import Response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Enforce HSTS only on production spaces (not local debug)
    host = request.headers.get("host", "")
    if "localhost" not in host and "127.0.0.1" not in host:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"

    # Strict Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' wss: ws: https://api.deepgram.com; "
        "frame-ancestors 'none';"
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://meet\.google\.com$|^chrome-extension://.*|^https://[a-zA-Z0-9-]+\.hf\.space$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount voice module router ──────────────────────────────────────────────────
# Support both: `uvicorn server:app` (local) and `uvicorn backend.server:app` (Docker)
try:
    from voice_module.routes import router as voice_router
    from voice_module.streaming import stream_router
    from voice_module.personal_routes import personal_router
    from auth_routes import router as auth_router
    from calibration_routes import router as calib_router
except ModuleNotFoundError:
    from backend.voice_module.routes import router as voice_router
    from backend.voice_module.streaming import stream_router
    from backend.voice_module.personal_routes import personal_router
    from backend.auth_routes import router as auth_router
    from backend.calibration_routes import router as calib_router

app.include_router(voice_router, prefix="/voice")
app.include_router(stream_router, prefix="/voice")
app.include_router(personal_router, prefix="/voice")
app.include_router(auth_router)
app.include_router(calib_router)

# ── Health check (must be before catch-all static route) ──────────────────────
@app.get("/health")
def health():
    try:
        from voice_module.style_comparator import clf_model
        from voice_module.storage import check_db_connection
    except ModuleNotFoundError:
        from backend.voice_module.style_comparator import clf_model
        from backend.voice_module.storage import check_db_connection

    return {
        "status": "ok",
        "model_loaded": clf_model is not None,
        "database_connected": check_db_connection()
    }

# ── Serve frontend ─────────────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/", include_in_schema=False)
def serve_landing():
    return FileResponse(FRONTEND_DIR / "landing.html")

@app.get("/login", include_in_schema=False)
def serve_login():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/privacy", include_in_schema=False)
def serve_privacy():
    return FileResponse(FRONTEND_DIR / "privacy.html")

@app.get("/terms", include_in_schema=False)
def serve_terms():
    return FileResponse(FRONTEND_DIR / "terms.html")

@app.get("/dashboard", include_in_schema=False)
def serve_dashboard():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

@app.get("/interview", include_in_schema=False)
def serve_interview():
    # Interview analysis is now done via the Chrome extension.
    # Redirect to dashboard.
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/{filename:path}", include_in_schema=False)
def serve_static(filename: str):
    file_path = FRONTEND_DIR / filename
    if file_path.is_file() and file_path.suffix in {".css", ".js", ".png", ".ico", ".svg", ".json"}:
        return FileResponse(file_path)
    # Default: serve dashboard for all unknown paths
    return FileResponse(FRONTEND_DIR / "dashboard.html")
