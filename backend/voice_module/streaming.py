"""
streaming.py — Deepgram Live Transcription + Long-Session Interview Analysis.

Mounts at /voice/stream (WebSocket) and /voice/meet-analyze (WebSocket).

Real-world design:
  - /stream: raw PCM → Deepgram → live transcript
  - /meet-analyze: handles HOURS of continuous speech by:
      • Building an adaptive baseline from first 60 words (refreshed every 15 min)
      • Analysing in 60-word sliding windows (every 20 new words)
      • Maintaining a full session timeline (list of {t, score, verdict})
      • Never dropping old text — rolling segment buffer capped at 1800 words (≈30 min)
      • Detecting mid-session authenticity drift even after hour 1+
"""

import asyncio
import logging
import os
import time
import json
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import re

try:
    from .style_comparator import calculate_style_shift
except ImportError:
    from backend.voice_module.style_comparator import calculate_style_shift

logger = logging.getLogger(__name__)
stream_router = APIRouter(tags=["Streaming"])


def align_and_merge(buffer: list, chunk: list, max_overlap: int = 40) -> list:
    """Finds the maximum overlap between the end of the buffer and the start of the chunk,
    allowing minor ASR changes / mismatches, and returns only the new suffix words.
    """
    if not buffer:
        return chunk
    if not chunk:
        return []
    
    n_buf = len(buffer)
    n_chk = len(chunk)
    
    # Normalize words (remove punctuation, lowercase) to prevent punctuation diffs from breaking alignment
    def normalize(word):
        return re.sub(r"[^\w]", "", str(word)).lower()

    buf_norm = [normalize(w) for w in buffer]
    chk_norm = [normalize(w) for w in chunk]
    
    best_k = 0
    for k in range(min(n_buf, n_chk, max_overlap), 0, -1):
        buf_slice = buf_norm[-k:]
        chk_slice = chk_norm[:k]
        mismatches = sum(1 for a, b in zip(buf_slice, chk_slice) if a != b)
        
        # Allow 1 mismatch for 3-5 words, and scale up for larger overlaps
        allowed_mismatches = 0 if k < 3 else (1 if k < 6 else k // 5)
        if mismatches <= allowed_mismatches:
            best_k = k
            break
            
    return chunk[best_k:]


# ── /voice/stream — Deepgram proxy ────────────────────────────────────────────

@stream_router.websocket("/stream")
async def deepgram_stream(websocket: WebSocket):
    """
    WebSocket proxy between browser mic and Deepgram Live Transcription.

    Protocol:
      Browser → server: raw audio bytes (any chunk size)
      Server  → browser: JSON strings {"type":"partial"|"final","text":"...","is_final":bool}
    """
    token = websocket.query_params.get("token")
    is_authorized = False

    try:
        from auth_routes import _decode_token
    except ImportError:
        from backend.auth_routes import _decode_token

    if os.getenv("TESTING") == "true":
        is_authorized = True
    elif token:
        payload = _decode_token(token)
        if payload is not None:
            is_authorized = True

    if not is_authorized:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Authentication required. Invalid or missing token."})
        await websocket.close()
        return

    await websocket.accept()

    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        await websocket.send_json({"type": "error", "text": "DEEPGRAM_API_KEY not configured"})
        await websocket.close()
        return

    import httpx
    dg_url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-2"
        "&language=en"
        "&punctuate=true"
        "&smart_format=true"
        "&interim_results=true"
        "&endpointing=150"          # emit sooner — was 300ms, now 150ms
        "&utterance_end_ms=1000"
        "&no_delay=true"            # prioritise low-latency over accuracy tradeoff
        "&filler_words=true"        # capture um/uh naturally
        "&words=true"
        "&diarize=false"
    )

    import websockets

    try:
        async with websockets.connect(
            dg_url,
            extra_headers={"Authorization": f"Token {api_key}"},
            ping_interval=20,
            ping_timeout=10,
        ) as dg_ws:
            logger.info("[stream] Deepgram connection established")

            async def forward_browser_to_dg():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await dg_ws.send(data)
                except WebSocketDisconnect:
                    try:
                        await dg_ws.send(b'')
                    except Exception:
                        pass

            async def forward_dg_to_browser():
                async for msg in dg_ws:
                    try:
                        data = json.loads(msg)
                        channel    = data.get("channel", {})
                        alts       = channel.get("alternatives", [{}])
                        transcript = alts[0].get("transcript", "") if alts else ""
                        is_final   = data.get("is_final", False)
                        speech_final = data.get("speech_final", False)
                        if transcript:
                            await websocket.send_json({
                                "type":         "final" if is_final else "partial",
                                "text":         transcript,
                                "is_final":     is_final,
                                "speech_final": speech_final,
                            })
                    except Exception as exc:
                        logger.debug("[stream] Parse error: %s", exc)

            await asyncio.gather(
                forward_browser_to_dg(),
                forward_dg_to_browser(),
            )

    except WebSocketDisconnect:
        logger.info("[stream] Browser disconnected cleanly")
    except Exception as exc:
        logger.error("[stream] Streaming error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "text": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── /voice/meet-analyze — Long-session interview analysis ────────────────────

# Design for multi-hour continuous interviews:
#
#   BASELINE_WORDS      = 60   words — initial calibration window
#   ANALYSIS_STRIDE     = 20   words — run analysis every 20 new words
#   ANALYSIS_WINDOW     = 120  words — last N words used for each analysis snapshot
#   BASELINE_REFRESH_S  = 900  sec  — re-anchor baseline every 15 min (first 60 words of that period)
#   SESSION_BUFFER_CAP  = 3600 words — full session rolling ring buffer (~60 min of speech)
#   TIMELINE_MAX        = 200  data points kept in session timeline

BASELINE_WORDS     = 60   # words needed to lock baseline
ANALYSIS_STRIDE    = 20   # run analysis every N new words (stable pacing)
ANALYSIS_WINDOW    = 120  # rolling window size in words (enough context for stable reading)
BASELINE_REFRESH_S = 900
SESSION_BUFFER_CAP = 3600
TIMELINE_MAX       = 200
MIN_WINDOW_WORDS   = 50   # minimum words before first analysis (was 40)

# Smoothing: exponential moving average alpha for score transitions
# Lower = smoother / slower transitions. 0.3 = 30% new, 70% old.
_EMA_ALPHA         = 0.30


@stream_router.websocket("/meet-analyze")
async def meet_analyze_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Google Meet live transcript analysis.
    Designed for multi-hour continuous interview sessions.

    Protocol:
      Browser  → Server: {"type": "transcript", "text": "...", "speaker": "Candidate"}
      Server   → Browser: {"type": "analysis", ...full metrics...}
                          {"type": "status",   "message": "..."}
                          {"type": "timeline",  "points": [{t,score,verdict},...]}
    """
    token = websocket.query_params.get("token")
    is_authorized = False

    try:
        from auth_routes import _decode_token
    except ImportError:
        from backend.auth_routes import _decode_token

    if os.getenv("TESTING") == "true":
        is_authorized = True
    elif token:
        payload = _decode_token(token)
        if payload is not None:
            is_authorized = True

    if not is_authorized:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Authentication required. Invalid or missing token."})
        await websocket.close()
        return

    await websocket.accept()

    # ── Session state ──────────────────────────────────────────────────────────
    session_start   = time.time()

    # Baseline: first BASELINE_WORDS words of the session (or of each 15-min period)
    baseline_words: list[str] = []
    baseline_locked = False
    baseline_refresh_at = session_start + BASELINE_REFRESH_S
    baseline_text = ""

    # Rolling analysis window — last ANALYSIS_WINDOW words of candidate speech
    analysis_window: deque[str] = deque(maxlen=ANALYSIS_WINDOW)

    # Full session buffer (ring, for drift detection over full interview)
    session_buffer: deque[str] = deque(maxlen=SESSION_BUFFER_CAP)

    # Session timeline — list of (elapsed_s, score, verdict) snapshots
    timeline: list[dict] = []

    # Count words added since last analysis run
    words_since_last_analysis = 0

    # Total candidate words this session
    total_candidate_words = 0

    # Per-segment accumulators for long-range drift
    segment_scores: list[float] = []   # one per ANALYSIS_STRIDE

    # EMA smoothed score — prevents sudden spikes in live display
    _ema_score: float | None = None

    # ── Flag deduplication — track which flag types have fired this session ──
    seen_flag_types: set[str] = set()

    def _flag_type(flag_text: str) -> str:
        """Extract a type key from the first 4 words of a flag string."""
        return " ".join(flag_text.lower().split()[:4])

    def _deduplicate_flags(flags: list) -> list:
        """Return only flags whose type hasn't been seen yet this session."""
        new_flags = []
        for f in flags:
            ft = _flag_type(f)
            if ft not in seen_flag_types:
                seen_flag_types.add(ft)
                new_flags.append(f)
        return new_flags

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ── Personal baseline injected from Meet overlay ──────────────────
            if data.get("type") == "baseline":
                injected = data.get("text", "").strip()
                if injected and len(injected.split()) >= 15:
                    baseline_text   = injected
                    baseline_locked = True
                    baseline_words  = injected.split()
                    logger.info("[meet-analyze] Personal baseline injected (%d words)", len(baseline_words))
                    await websocket.send_json({
                        "type": "status",
                        "message": f"Baseline locked from personal text ({len(baseline_words)} words) — live analysis ready",
                        "elapsed": 0,
                        "total_words": 0,
                    })
                continue

            if data.get("type") == "transcript":
                chunk = data.get("text", "").strip()
                speaker = data.get("speaker", "Candidate")

                # Only process candidate speech
                if not chunk or speaker.lower() == "interviewer":
                    continue

                chunk_words = chunk.split()
                now = time.time()
                elapsed = round(now - session_start)

                # Deduplicate overlapping ASR chunks (fixes the word count explosion & metric bias)
                new_words = align_and_merge(list(session_buffer), chunk_words)
                if not new_words:
                    continue

                # ── Append to all buffers ──────────────────────────────────
                session_buffer.extend(new_words)
                analysis_window.extend(new_words)
                total_candidate_words += len(new_words)
                words_since_last_analysis += len(new_words)

                # ── Phase 1: Baseline collection ──────────────────────────
                if not baseline_locked:
                    baseline_words.extend(new_words)
                    count = len(baseline_words)

                    if count < BASELINE_WORDS:
                        await websocket.send_json({
                            "type": "status",
                            "message": f"Calibrating baseline... ({count}/{BASELINE_WORDS} words)",
                            "elapsed": elapsed,
                            "total_words": total_candidate_words,
                        })
                        continue  # keep collecting baseline

                    # Baseline is now complete
                    baseline_text = " ".join(baseline_words[:BASELINE_WORDS])
                    baseline_locked = True
                    await websocket.send_json({
                        "type": "status",
                        "message": "Baseline locked — live analysis active",
                        "elapsed": elapsed,
                        "total_words": total_candidate_words,
                    })

                # ── Adaptive baseline refresh (every 15 min) ──────────────
                # Re-anchor baseline to the candidate's current speaking style
                # This handles the natural style shift from nerves → comfort over
                # a long interview. We take the most recent BASELINE_WORDS as the
                # new anchor, but only if the candidate has been speaking normally
                # (score < 55) for the last several snapshots.
                if now >= baseline_refresh_at and len(segment_scores) >= 5:
                    recent_avg = sum(segment_scores[-5:]) / 5
                    if recent_avg < 55:   # only refresh if recent period looks genuine
                        fresh_words = list(session_buffer)[-BASELINE_WORDS:]
                        if len(fresh_words) >= BASELINE_WORDS // 2:
                            baseline_text = " ".join(fresh_words)
                            baseline_refresh_at = now + BASELINE_REFRESH_S
                            logger.info(
                                "[meet-analyze] Baseline refreshed at %.0f min (recent avg=%.1f)",
                                elapsed / 60, recent_avg
                            )
                            await websocket.send_json({
                                "type": "status",
                                "message": f"Baseline refreshed at {elapsed//60}m — adapting to current style",
                                "elapsed": elapsed,
                                "total_words": total_candidate_words,
                            })

                # ── Phase 2: Analysis on stride ────────────────────────────
                if words_since_last_analysis < ANALYSIS_STRIDE:
                    continue

                words_since_last_analysis = 0

                # ── Recency-weighted window for faster real-time response ──────
                # Split window into thirds: recent words are repeated to weight
                # them more heavily. This makes the score update quickly when the
                # candidate switches style (e.g. from AI-read to natural speech).
                raw_window = list(analysis_window)
                n = len(raw_window)
                if n >= MIN_WINDOW_WORDS * 2:
                    third = n // 3
                    old_words    = raw_window[:third]          # oldest — count once
                    mid_words    = raw_window[third:2*third]   # middle — count 2x
                    recent_words = raw_window[2*third:]        # recent — count 3x
                    weighted = old_words + mid_words * 2 + recent_words * 3
                    window_text = " ".join(weighted)
                else:
                    window_text = " ".join(raw_window)


                if len(analysis_window) < MIN_WINDOW_WORDS:
                    await websocket.send_json({
                        "type": "status",
                        "message": f"Listening... ({len(analysis_window)}/{MIN_WINDOW_WORDS} words needed)",
                        "elapsed": elapsed,
                        "total_words": total_candidate_words,
                    })
                    continue

                # ── Run style comparator ──────────────────────────────────
                try:
                    analysis = calculate_style_shift(baseline_text, window_text)
                except Exception as e:
                    logger.error("[meet-analyze] Analysis error: %s", e)
                    continue

                score = analysis.get("lsdi_score", 0.0)
                auth  = analysis.get("authenticity_score", 100.0)

                # ── EMA smoothing: blend new score with running average ────────
                # Prevents sudden jumps from single noisy analysis windows.
                # First reading anchors the EMA; subsequent ones blend in gradually.
                if _ema_score is None:
                    _ema_score = auth
                else:
                    _ema_score = _EMA_ALPHA * auth + (1.0 - _EMA_ALPHA) * _ema_score
                auth = round(_ema_score, 1)

                segment_scores.append(score)

                # Verdict derived from smoothed score
                if auth < 40:
                    verdict = "HIGHLY SUSPICIOUS"
                elif auth < 60:
                    verdict = "SUSPICIOUS"
                elif auth < 80:
                    verdict = "NEEDS REVIEW"
                else:
                    verdict = "GENUINE"

                # ── Session timeline update ───────────────────────────────
                if len(timeline) < TIMELINE_MAX:
                    timeline.append({
                        "t":       elapsed,
                        "score":   auth,
                        "verdict": verdict,
                        "words":   total_candidate_words,
                    })
                else:
                    # Downsample: keep every-other point and append latest
                    timeline = timeline[::2] + [{
                        "t":       elapsed,
                        "score":   auth,
                        "verdict": verdict,
                        "words":   total_candidate_words,
                    }]

                # ── Compute long-range session drift ─────────────────────
                # Compare first 10 snapshots vs last 10 snapshots
                session_drift = None
                if len(segment_scores) >= 20:
                    early_avg = sum(segment_scores[:10]) / 10
                    recent_avg_10 = sum(segment_scores[-10:]) / 10
                    session_drift = round(recent_avg_10 - early_avg, 1)

                tp      = analysis.get("technical_profile", {})
                pp      = analysis.get("personal_profile", {})
                temporal = analysis.get("temporal_drift", {})
                conf    = analysis.get("confidence_interval", {})

                # ── Inline plagiarism risk (6-parameter model) ────────────
                raw_cosine  = analysis.get("cosine_similarity", 0.0)
                voc_jump    = tp.get("vocabulary_level", 0) - pp.get("vocabulary_level", 0)
                form_jump   = tp.get("formality_score", 0) - pp.get("formality_score", 0)
                fill_drop   = pp.get("filler_ratio", 0) - tp.get("filler_ratio", 0)
                plag_risk   = 0.0
                plag_signals: list[str] = []
                if raw_cosine > 0.65:
                    plag_risk += 35
                    plag_signals.append(f"High textual overlap (cosine={raw_cosine:.2f}) — may be reading notes")
                elif raw_cosine > 0.45:
                    plag_risk += 15
                if voc_jump > 18:
                    plag_risk += 25
                    plag_signals.append(f"Vocabulary jumped +{voc_jump:.0f}pts from personal baseline")
                elif voc_jump > 10:
                    plag_risk += 12
                if form_jump > 20:
                    plag_risk += 20
                    plag_signals.append(f"Formality jumped +{form_jump:.0f}pts — structured/written language detected")
                if fill_drop > 0.03 and pp.get("filler_ratio", 0) > 0.01:
                    plag_risk += 15
                    plag_signals.append("Filler words disappeared in technical round — naturalness lost")
                plag_risk = min(100.0, round(plag_risk, 1))

                # ── Send full analysis payload ────────────────────────────
                await websocket.send_json({
                    "type": "analysis",
                    # Core authenticity
                    "score":              auth,
                    "verdict":            analysis.get("verdict", verdict),   # v2 5-tier
                    "verdict_info":       analysis.get("verdict_info", {}),
                    "lsdi":               score,
                    "style_shift":        analysis.get("style_shift", "LOW"),
                    # Session metadata
                    "elapsed":            elapsed,
                    "total_words":        total_candidate_words,
                    "session_drift":      session_drift,
                    "baseline_age":       round(now - (baseline_refresh_at - BASELINE_REFRESH_S)),
                    # ML classifier
                    "ml_prob":            analysis.get("ml_probability"),
                    "analysis_mode":      analysis.get("_analysis_mode", "heuristic"),
                    "strong_signals":     analysis.get("strong_signal_count", 0),
                    "cosine_sim":         raw_cosine,
                    # Confidence — old + new
                    "confidence":         analysis.get("confidence_level", "Low"),
                    "conf_low":           conf.get("low", 0),
                    "conf_high":          conf.get("high", 0),
                    # confidence_v2: build a consistent object the overlay can always read
                    "confidence_v2": {
                        "level": (
                            "high"   if analysis.get("confidence_level", "Low") == "High"   else
                            "medium" if analysis.get("confidence_level", "Low") == "Medium" else
                            "low"
                        ),
                        "label": analysis.get("confidence_level", "Low"),
                        **( analysis.get("confidence", {}) if isinstance(analysis.get("confidence"), dict) else {} )
                    },
                    # v2: Evidence + signals
                    "evidence":           analysis.get("evidence", []),
                    "active_signals":     analysis.get("active_signals", []),
                    "primary_signal":     analysis.get("primary_signal"),
                    "supporting_signals": analysis.get("supporting_signals", []),
                    # v2: Explainability
                    "followup_questions": analysis.get("followup_questions", []),
                    "short_guardrail":    analysis.get("short_guardrail"),
                    "safe_interpretation":analysis.get("safe_interpretation", ""),
                    "disclaimer":         analysis.get("disclaimer", ""),
                    "capped_reason":      analysis.get("capped_reason"),
                    # Live linguistic metrics (11-parameter model)
                    "formality":          tp.get("formality_score", 0),
                    "vocabulary":         tp.get("vocabulary_level", 0),
                    "grammar":            tp.get("grammar_score", 0),
                    "lexical_diversity":  tp.get("lexical_diversity", 0),
                    "filler_ratio":       tp.get("filler_ratio", 0),
                    "avg_sent_len":       tp.get("avg_sentence_len", 0),
                    "transition_density": tp.get("transition_density", 0),
                    "flesch_kincaid":     tp.get("flesch_kincaid", 0),
                    "gunning_fog":        tp.get("gunning_fog", 0),
                    "passive_voice":      tp.get("passive_voice_ratio", 0),
                    "hedging":            tp.get("hedging_density", 0),
                    "sentence_burstiness":tp.get("sentence_burstiness", 0),
                    "ai_boilerplate":     tp.get("ai_boilerplate", 0),
                    "pronouns":           tp.get("personal_pronoun_ratio", 0),
                    "ai_starters":        tp.get("ai_sentence_starters", 0),
                    # Personal baseline (for delta bars)
                    "base_formality":     pp.get("formality_score", 0),
                    "base_vocabulary":    pp.get("vocabulary_level", 0),
                    "base_grammar":       pp.get("grammar_score", 0),
                    "base_filler":        pp.get("filler_ratio", 0),
                    # Temporal drift
                    "drift_score":        temporal.get("drift_score", 0),
                    "has_spike":          temporal.get("has_spike", False),
                    "drift_window":       temporal.get("drift_window", 0),
                    # Plagiarism / script-reading
                    "plagiarism_risk":    plag_risk,
                    "plagiarism_signals": plag_signals,
                    # Flags and summary
                    "flags":              _deduplicate_flags(analysis.get("flags", [])),
                    "summary":            analysis.get("summary", ""),
                    "fairness_applied":   analysis.get("fairness_adjusted", False),
                    # Session timeline (last 50 points)
                    "timeline":           timeline[-50:],

                })

    except WebSocketDisconnect:
        elapsed_total = round(time.time() - session_start)
        logger.info(
            "[meet-analyze] Session ended after %d min | %d candidate words | %d snapshots",
            elapsed_total // 60, total_candidate_words, len(segment_scores)
        )
    except Exception as exc:
        logger.error("[meet-analyze] Error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        # BUG FIX: always close cleanly to free server resources
        try:
            await websocket.close()
        except Exception:
            pass
