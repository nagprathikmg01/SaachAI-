"""
rate_limiter.py — File-backed rate limiter that survives server restarts.

Uses a JSON file in /tmp (or the backend dir) to persist request counts.
Resets windows automatically. Thread-safe with a lock.

Usage:
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    if not limiter.allow(ip_address):
        raise HTTPException(429, "Too many requests")
"""

import json
import os
import time
import threading
from pathlib import Path

_LOCK = threading.Lock()

import tempfile

# Store in standard cross-platform temp directory (survives restarts)
_default_store = os.path.join(tempfile.gettempdir(), "sachhAI_rate_limits.json")
_STORE_PATH = Path(os.environ.get("RATE_LIMIT_STORE", _default_store))


def _load() -> dict:
    try:
        if _STORE_PATH.exists():
            with open(_STORE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_STORE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass  # Never crash the request over rate limit storage


class RateLimiter:
    """
    Sliding window rate limiter backed by a JSON file.
    Thread-safe. Survives in-process restarts (file persists in /tmp).
    """

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        """
        Returns True if the request is allowed, False if rate-limited.
        key: typically an IP address or username
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with _LOCK:
            data = _load()

            # Get timestamps for this key
            timestamps = [t for t in data.get(key, []) if t > cutoff]

            if len(timestamps) >= self.max_requests:
                _save(data)  # persist even on rejection
                return False

            timestamps.append(now)
            data[key] = timestamps
            _save(data)
            return True

    def remaining(self, key: str) -> int:
        """How many requests remain in the current window."""
        now = time.time()
        cutoff = now - self.window_seconds
        with _LOCK:
            data = _load()
            timestamps = [t for t in data.get(key, []) if t > cutoff]
            return max(0, self.max_requests - len(timestamps))


# ── Shared instances ──────────────────────────────────────────────────────────

# Analysis endpoint: 15 requests per minute per IP (generous for real usage)
analysis_limiter = RateLimiter(max_requests=15, window_seconds=60)

# Auth endpoint: 10 login attempts per minute per IP
auth_limiter = RateLimiter(max_requests=10, window_seconds=60)
