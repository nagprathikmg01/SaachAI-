"""
calibration_routes.py — Calibration Mode endpoints.

Mounted at /calibrate. Allows HR users to:
  POST /calibrate/test   — test a known pair and see if SachhAI flags it correctly
  GET  /calibrate/meta   — get current model info (accuracy, mode, dataset size)
  POST /calibrate/sensitivity — adjust global sensitivity thresholds (stored in memory)
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import json

try:
    from auth_routes import _get_current_user
except ImportError:
    from backend.auth_routes import _get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Calibration"])

# ── Global sensitivity state (in-memory, resets on restart) ──────────────────
# 'aggressive' = lower thresholds (flag more), 'lenient' = higher thresholds
_SENSITIVITY_MAP = {
    "aggressive": {"LOW": 10, "MODERATE": 25, "HIGH": 45, "VERY_HIGH": 65},
    "balanced":   {"LOW": 20, "MODERATE": 40, "HIGH": 60, "VERY_HIGH": 80},
    "lenient":    {"LOW": 30, "MODERATE": 50, "HIGH": 70, "VERY_HIGH": 90},
}
_current_sensitivity = "balanced"


class CalibrateTestRequest(BaseModel):
    genuine_personal:   str
    genuine_technical:  str
    ai_personal:        str
    ai_technical:       str


class SensitivityRequest(BaseModel):
    level: str  # 'aggressive' | 'balanced' | 'lenient'


@router.post("/calibrate/test", summary="Test calibration with known genuine/AI pair")
async def calibrate_test(
    req: CalibrateTestRequest,
    user: dict = Depends(_get_current_user),
):
    """
    Run analysis on two known pairs:
      1. A pair the HR knows is genuine (human-written both sides)
      2. A pair the HR knows is AI-assisted
    Returns whether SachhAI correctly classified each.
    """
    try:
        from voice_module.style_comparator import calculate_style_shift
    except ImportError:
        from backend.voice_module.style_comparator import calculate_style_shift

    genuine_result = await __import__('asyncio').to_thread(
        calculate_style_shift, req.genuine_personal, req.genuine_technical
    )
    ai_result = await __import__('asyncio').to_thread(
        calculate_style_shift, req.ai_personal, req.ai_technical
    )

    genuine_passed = genuine_result["style_shift"] in ("LOW", "MODERATE")
    ai_passed      = ai_result["style_shift"] in ("HIGH", "VERY HIGH")
    both_correct   = genuine_passed and ai_passed

    return {
        "genuine_pair": {
            "shift":             genuine_result["style_shift"],
            "score":             genuine_result["shift_score"],
            "authenticity":      genuine_result["authenticity_score"],
            "correctly_flagged": genuine_passed,
            "expected":          "LOW or MODERATE",
        },
        "ai_pair": {
            "shift":             ai_result["style_shift"],
            "score":             ai_result["shift_score"],
            "authenticity":      ai_result["authenticity_score"],
            "correctly_flagged": ai_passed,
            "expected":          "HIGH or VERY HIGH",
        },
        "calibration_passed": both_correct,
        "current_sensitivity": _current_sensitivity,
        "recommendation": (
            "Model is well-calibrated ✓" if both_correct else
            "Consider switching to 'aggressive' sensitivity — genuine pair was over-flagged" if not genuine_passed else
            "Consider switching to 'aggressive' sensitivity — AI pair was missed"
        ),
    }


@router.get("/calibrate/meta", summary="Get current model metadata and accuracy")
def calibrate_meta(user: dict = Depends(_get_current_user)):
    """Return the trained model's accuracy metrics and configuration."""
    meta_path = Path(__file__).parent / "voice_module" / "model" / "model_meta.json"
    if not meta_path.exists():
        return {
            "model_available": False,
            "analysis_mode":   "heuristic_only",
            "message":         "Run train_model.py to train the ML classifier",
        }

    try:
        with open(meta_path) as f:
            meta = json.load(f)
        return {
            "model_available":    True,
            "analysis_mode":      "ml_augmented",
            "cv_accuracy":        f"{meta['cv_accuracy_mean']}% ± {meta['cv_accuracy_std']}%",
            "cv_f1_score":        f"{meta['cv_f1_mean']}%",
            "train_accuracy":     f"{meta['train_accuracy']}%",
            "training_samples":   meta["n_samples"],
            "genuine_samples":    meta["n_genuine"],
            "ai_samples":         meta["n_ai_assisted"],
            "model_type":         meta["model_type"],
            "feature_count":      len(meta["features"]),
            "current_sensitivity": _current_sensitivity,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/calibrate/sensitivity", summary="Adjust global detection sensitivity")
def set_sensitivity(
    req: SensitivityRequest,
    user: dict = Depends(_get_current_user),
):
    """Set detection sensitivity: 'aggressive' | 'balanced' | 'lenient'."""
    global _current_sensitivity
    if req.level not in _SENSITIVITY_MAP:
        raise HTTPException(status_code=400, detail=f"level must be one of: {list(_SENSITIVITY_MAP.keys())}")
    _current_sensitivity = req.level
    thresholds = _SENSITIVITY_MAP[req.level]
    logger.info("[calibrate] Sensitivity set to %s: %s", req.level, thresholds)
    return {
        "sensitivity":  req.level,
        "thresholds":   thresholds,
        "message":      f"Detection sensitivity updated to '{req.level}'",
    }
