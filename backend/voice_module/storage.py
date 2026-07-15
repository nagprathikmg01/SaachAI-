"""
storage.py — Supabase-based persistence for voice interview data.

Data is stored in the `voice_data` table on Supabase.
"""

import os
import logging
from typing import Optional
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Ensure env vars are loaded
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

VALID_TYPES = frozenset({"personal", "technical", "analysis"})


def _get_supabase_config():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
    return url, key


def _headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def save_response(
    candidate_id: str,
    response_type: str,
    text: str,
    submitted_by: Optional[str] = None,
) -> None:
    """Persist a transcription for a candidate to Supabase (upsert)."""
    if response_type not in VALID_TYPES:
        raise ValueError(f"response_type must be one of {VALID_TYPES}")

    try:
        url, key = _get_supabase_config()
    except RuntimeError as e:
        logger.warning("Supabase not configured — skipping save: %s", e)
        return  # Graceful degradation — don't crash the route

    # Fetch existing to merge
    existing = get_candidate(candidate_id) or {}
    existing[response_type] = text

    payload = {
        "candidate_id": candidate_id,
        "personal":     existing.get("personal"),
        "technical":    existing.get("technical"),
        # Clear the cached analysis if the transcripts are changing, so it's not stale
        "analysis":     None,
    }
    if submitted_by:
        payload["submitted_by"] = submitted_by

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{url}/rest/v1/voice_data",
                headers={**_headers(key), "Prefer": "resolution=merge-duplicates"},
                json=payload,
            )
            if not resp.is_success:
                logger.error("Supabase upsert failed: %s %s", resp.status_code, resp.text)
                # Don't raise — let the route continue
    except Exception as exc:
        logger.error("Supabase save error: %s", exc)
        # Don't crash the route over a DB error

    logger.info(
        "[voice_module] Stored %s response for candidate=%s (%d chars)",
        response_type, candidate_id, len(text),
    )


def save_analysis(candidate_id: str, analysis_data: dict) -> None:
    """Persist the full analysis result to Supabase (PATCH update on existing row)."""
    try:
        url, key = _get_supabase_config()
    except RuntimeError:
        return

    try:
        with httpx.Client(timeout=10) as client:
            # Use PATCH to update ONLY the analysis field on the existing row.
            # This avoids triggering upsert-related constraints while still being safe.
            resp = client.patch(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"candidate_id": f"eq.{candidate_id}"},
                json={"analysis": analysis_data},
            )
            if resp.is_success:
                logger.info("[voice_module] Stored analysis for candidate=%s", candidate_id)
                return
            # If PATCH fails (row doesn't exist yet), fall back to INSERT
            logger.warning("PATCH failed (%s), trying INSERT: %s", resp.status_code, resp.text[:100])

            # Fetch full existing row first
            fetch_resp = client.get(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"candidate_id": f"eq.{candidate_id}", "select": "*"},
            )
            existing_row = fetch_resp.json()[0] if fetch_resp.is_success and fetch_resp.json() else {}

            insert_payload = {
                "candidate_id": candidate_id,
                "analysis":     analysis_data,
            }
            for col in ("personal", "technical", "submitted_by", "candidate_name", "role"):
                val = existing_row.get(col)
                if val is not None:
                    insert_payload[col] = val

            ins = client.post(
                f"{url}/rest/v1/voice_data",
                headers={**_headers(key), "Prefer": "resolution=merge-duplicates"},
                json=insert_payload,
            )
            if not ins.is_success:
                logger.error("Supabase analysis INSERT failed: %s %s", ins.status_code, ins.text)
            else:
                logger.info("[voice_module] Inserted analysis for candidate=%s", candidate_id)
    except Exception as exc:
        logger.error("Supabase analysis save error: %s", exc)




def get_candidate(candidate_id: str) -> Optional[dict]:
    """Retrieve all stored responses for a candidate."""
    try:
        url, key = _get_supabase_config()
    except RuntimeError:
        return None

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"candidate_id": f"eq.{candidate_id}", "select": "*"},
            )
            if not resp.is_success:
                logger.error("Supabase fetch failed: %s", resp.text)
                return None

            data = resp.json()
            if not data:
                return None

            row = data[0]
            # Return all relevant non-null fields
            _RETURN_COLS = {"personal", "technical", "analysis", "submitted_by",
                            "candidate_name", "role", "interviewer", "created_at"}
            return {k: v for k, v in row.items() if v is not None and k in _RETURN_COLS}
    except Exception as exc:
        logger.error("Supabase get error: %s", exc)
        return None



def delete_candidate(candidate_id: str) -> bool:
    """Delete all data for a candidate."""
    try:
        url, key = _get_supabase_config()
    except RuntimeError:
        return False

    existing = get_candidate(candidate_id)
    if existing is None:
        return False

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.delete(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"candidate_id": f"eq.{candidate_id}"},
            )
            if not resp.is_success:
                logger.error("Supabase delete failed: %s", resp.text)
                return False
    except Exception as exc:
        logger.error("Supabase delete error: %s", exc)
        return False

    logger.info("[voice_module] Deleted candidate=%s", candidate_id)
    return True


def list_candidates(
    submitted_by: Optional[str] = None,
    role: Optional[str] = None,
) -> list:
    """
    Return stored candidate IDs.

    - If role == 'admin' → return ALL candidates regardless of submitted_by.
    - If role == 'hr' and submitted_by is set → filter to that user's submissions.
    - Falls back gracefully if submitted_by column doesn't exist in Supabase.
    """
    try:
        url, key = _get_supabase_config()
    except RuntimeError:
        return []

    def _fetch_all(client: httpx.Client) -> list:
        """Fetch all candidates, with submitted_by if available."""
        resp = client.get(
            f"{url}/rest/v1/voice_data",
            headers=_headers(key),
            params={"select": "candidate_id,submitted_by"},
        )
        if resp.is_success:
            return [{"id": row["candidate_id"], "by": row.get("submitted_by") or "unknown"} for row in resp.json()]

        # submitted_by column missing — fetch without it
        if "42703" in resp.text or "does not exist" in resp.text:
            resp2 = client.get(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"select": "candidate_id"},
            )
            if resp2.is_success:
                return [{"id": row["candidate_id"], "by": "unknown"} for row in resp2.json()]
            logger.error("Supabase list (no-col fallback) failed: %s", resp2.text)
            return []

        logger.error("Supabase list failed: %s", resp.text)
        return []

    try:
        with httpx.Client(timeout=10) as client:
            # Admin: always return everything
            if role == "admin" or not submitted_by:
                return _fetch_all(client)

            # HR: try filtered query first
            resp = client.get(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"select": "candidate_id,submitted_by", "submitted_by": f"eq.{submitted_by}"},
            )
            if resp.is_success:
                rows = resp.json()
                # If the column exists but this HR user has 0 records,
                # still return the filtered result (empty list is correct).
                return [{"id": row["candidate_id"], "by": row.get("submitted_by") or submitted_by} for row in rows]

            # Column missing — return all records so nothing is lost
            if "42703" in resp.text or "does not exist" in resp.text:
                logger.warning(
                    "[storage] submitted_by column not found — returning all candidates. "
                    "Add the column to voice_data in Supabase to enable proper HR filtering."
                )
                return _fetch_all(client)

            logger.error("Supabase HR list failed: %s", resp.text)
            return []

    except Exception as exc:
        logger.error("Supabase list error: %s", exc)
        return []


def check_db_connection() -> bool:
    """Check if the Supabase database is connected and responding."""
    try:
        url, key = _get_supabase_config()
        with httpx.Client(timeout=3) as client:
            resp = client.get(
                f"{url}/rest/v1/voice_data",
                headers=_headers(key),
                params={"limit": 1}
            )
            return resp.is_success
    except Exception:
        return False
