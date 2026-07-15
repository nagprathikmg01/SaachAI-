"""
transcriber.py — Deepgram Nova-2 audio transcription for the voice_module.

Compatible with deepgram-sdk v3.x (object-attribute response, not dict).
Returns: transcript text + rich audio signals (confidence, speech rate, pauses).
"""

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_client():
    from deepgram import DeepgramClient
    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set in environment")
    return DeepgramClient(api_key)


def _safe_get(obj, *keys, default=None):
    """Safely traverse nested object/dict attributes."""
    cur = obj
    for key in keys:
        if cur is None:
            return default
        try:
            # Try attribute access (SDK v3 objects)
            cur = getattr(cur, key)
        except AttributeError:
            try:
                # Fall back to dict access
                cur = cur[key]
            except (KeyError, TypeError, IndexError):
                return default
    return cur if cur is not None else default


def _extract_words(response: Any) -> list:
    """Extract word list from Deepgram v3 response (works on dict or SDK object)."""
    try:
        if not isinstance(response, dict):
            response = response.to_dict() if hasattr(response, "to_dict") else {}
        channels = response.get("results", {}).get("channels", [])
        if not channels:
            return []
        alts = channels[0].get("alternatives", [])
        return (alts[0].get("words") or []) if alts else []
    except Exception:
        return []


def _extract_transcript(response: Any) -> str:
    """Extract plain transcript string from Deepgram v3 response (dict or object)."""
    try:
        if not isinstance(response, dict):
            response = response.to_dict() if hasattr(response, "to_dict") else {}
        channels = response.get("results", {}).get("channels", [])
        if not channels:
            return ""
        alts = channels[0].get("alternatives", [])
        return ((alts[0].get("transcript") or "") if alts else "").strip()
    except Exception:
        return ""


def _extract_duration(response: Any) -> float:
    """Extract audio duration from Deepgram v3 response (dict or object)."""
    try:
        if not isinstance(response, dict):
            response = response.to_dict() if hasattr(response, "to_dict") else {}
        return float(response.get("metadata", {}).get("duration") or 0)
    except Exception:
        return 0.0


def _extract_audio_signals(response: Any) -> dict:
    """
    Extract rich audio signals from a Deepgram v3 response object.

    Signals:
      - avg_confidence     : mean word-level confidence (0–1)
      - confidence_variance: std-dev of confidence scores
      - speech_rate_wpm   : words per minute
      - pause_count        : pauses > 0.5 s
      - long_pause_count  : pauses > 1.5 s
      - avg_pause_duration : mean pause gap (s)
      - filler_word_count  : count of filler words
      - duration_seconds   : total audio duration
      - word_count         : total word count
    """
    words    = _extract_words(response)
    duration = _extract_duration(response)

    if not words:
        return {}

    # Helper to read word fields (objects or dicts)
    def wf(w, field, default=None):
        v = getattr(w, field, None)
        if v is None:
            v = w.get(field, default) if isinstance(w, dict) else default
        return v

    # ── Confidence ─────────────────────────────────────────────────────────────
    confidences = [wf(w, "confidence", 1.0) for w in words]
    confidences = [float(c) for c in confidences if c is not None]
    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else None

    if len(confidences) > 1:
        mean = sum(confidences) / len(confidences)
        conf_variance = round((sum((c - mean) ** 2 for c in confidences) / len(confidences)) ** 0.5, 4)
    else:
        conf_variance = None

    # ── Speech rate ─────────────────────────────────────────────────────────────
    word_count   = len(words)
    duration_min = duration / 60 if duration > 0 else None
    wpm = round(word_count / duration_min, 1) if duration_min else None

    # ── Pauses ──────────────────────────────────────────────────────────────────
    pause_threshold = 0.5
    long_threshold  = 1.5
    gaps = []
    for i in range(len(words) - 1):
        end_i   = float(wf(words[i],     "end",   0) or 0)
        start_j = float(wf(words[i + 1], "start", 0) or 0)
        gap = start_j - end_i
        if gap > 0:
            gaps.append(gap)

    pauses      = [g for g in gaps if g >= pause_threshold]
    long_pauses = [g for g in gaps if g >= long_threshold]
    avg_pause   = round(sum(pauses) / len(pauses), 2) if pauses else 0.0

    # ── Filler words ────────────────────────────────────────────────────────────
    FILLERS = {"um", "uh", "like", "literally", "basically", "actually",
               "you know", "i mean", "kind of", "sort of"}
    word_texts   = [(wf(w, "word", "") or "").lower() for w in words]
    filler_count = sum(1 for w in word_texts if w in FILLERS)

    return {
        "avg_confidence":      avg_conf,
        "confidence_variance": conf_variance,
        "speech_rate_wpm":     wpm,
        "pause_count":         len(pauses),
        "long_pause_count":    len(long_pauses),
        "avg_pause_duration":  avg_pause,
        "filler_word_count":   filler_count,
        "duration_seconds":    round(duration, 1),
        "word_count":          word_count,
    }


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "recording.webm",
    include_signals: bool = True,
) -> dict:
    """
    Transcribe raw audio bytes using Deepgram Nova-2 (SDK v3).

    Args:
        audio_bytes:     Raw audio data.
        filename:        Original filename — used to detect MIME type.
        include_signals: If True, extract audio confidence/pause signals.

    Returns:
        { "text": str, "signals": dict | None }

    Raises:
        RuntimeError: On API failure or missing key.
        ValueError:   If audio_bytes is empty.
    """
    if not audio_bytes:
        raise ValueError("audio_bytes must not be empty")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
    mime_map = {
        "webm": "audio/webm",
        "mp3":  "audio/mpeg",
        "wav":  "audio/wav",
        "m4a":  "audio/mp4",
        "ogg":  "audio/ogg",
        "flac": "audio/flac",
    }
    mimetype = mime_map.get(ext, "audio/webm")

    logger.info(
        "[transcriber] Sending %.1f KB to Deepgram Nova-2 (file=%s, mime=%s)...",
        len(audio_bytes) / 1024, filename, mimetype,
    )

    def _do_transcribe():
        from deepgram import PrerecordedOptions
        client  = _get_client()
        payload = {"buffer": audio_bytes, "mimetype": mimetype}
        options = PrerecordedOptions(
            model="nova-2",
            language="en",
            smart_format=True,
            punctuate=True,
            paragraphs=True,        # preserve natural breaks
            utterances=True,        # detect utterance boundaries
            utt_split=1000,         # flush after 1 s of silence (catches fast readers)
            filler_words=True,      # capture um/uh for analysis
            numerals=True,          # convert "two" → "2" for technical responses
            diarize=False,          # single-speaker per round
        )
        return client.listen.prerecorded.v("1").transcribe_file(payload, options)


    try:
        response = await asyncio.to_thread(_do_transcribe)
        # Normalise: always work with a plain dict from this point on
        if hasattr(response, "to_dict"):
            response = response.to_dict()
        elif not isinstance(response, dict):
            response = {}
    except Exception as exc:
        logger.exception("[transcriber] Deepgram API error")
        raise RuntimeError(f"Deepgram transcription failed: {exc}") from exc

    # Extract transcript
    text = _extract_transcript(response)

    if not text:
        # Second attempt — try raw dict fallback
        try:
            alts = response.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])
            text = (alts[0].get("transcript", "") if alts else "").strip()
        except Exception:
            pass

    # Extract signals
    signals = None
    if include_signals:
        try:
            signals = _extract_audio_signals(response)
        except Exception:
            logger.warning("[transcriber] Could not extract audio signals — skipping")
            signals = {}

    logger.info(
        "[transcriber] Done — %d chars | signals=%s",
        len(text), bool(signals),
    )

    return {"text": text, "signals": signals}
