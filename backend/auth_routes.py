"""
auth_routes.py — Minimal JWT-based authentication for SachhAI.

Endpoints mounted at /auth:
  POST /auth/login          — validate credentials, return JWT
  GET  /auth/me             — return current user info from token
  GET  /auth/employees      — (admin only) list all HR employees
  POST /auth/employees      — (admin only) add a new HR employee
  DELETE /auth/employees/{username}  — (admin only) remove an HR employee

Passwords are stored as SHA-256 hashes in backend/users.json.
JWT secret is read from the JWT_SECRET env var (falls back to a dev default).
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

USERS_FILE = Path(__file__).parent / "users.json"
JWT_SECRET  = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGO    = "HS256"
TOKEN_TTL_H = 12   # hours

router = APIRouter(prefix="/auth", tags=["Auth"])
bearer = HTTPBearer(auto_error=False)

try:
    from rate_limiter import RateLimiter as _RL
except ImportError:
    from backend.rate_limiter import RateLimiter as _RL

_rl_login = _RL(max_requests=5, window_seconds=60)



# ── Helpers ───────────────────────────────────────────────────────────────────

import secrets

# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        600000
    )
    return f"{salt.hex()}:{key.hex()}"


def _verify_password(stored_hash: str, password: str) -> bool:
    if ":" not in stored_hash:
        # Legacy fallback
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash
    try:
        salt_hex, key_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            600000
        )
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False


def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        # Seed default users
        default_users = [
            {
                "username": "hr1",
                "password_hash": _hash("hr123"),
                "role": "hr",
                "display_name": "Demo HR"
            },
            {
                "username": "admin",
                "password_hash": _hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                "role": "admin",
                "display_name": "Administrator"
            }
        ]
        _save_users(default_users)
        return default_users
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        try:
            content = f.read().strip()
            if not content:
                raise json.JSONDecodeError("Empty file", "", 0)
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            default_users = [
                {
                    "username": "hr1",
                    "password_hash": _hash("hr123"),
                    "role": "hr",
                    "display_name": "Demo HR"
                },
                {
                    "username": "admin",
                    "password_hash": _hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                    "role": "admin",
                    "display_name": "Administrator"
                }
            ]
            _save_users(default_users)
            return default_users


def _save_users(users: list[dict]) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def _make_token(username: str, role: str, display_name: str) -> str:
    payload = {
        "sub":          username,
        "role":         role,
        "display_name": display_name,
        "exp":          datetime.now(tz=timezone.utc) + timedelta(hours=TOKEN_TTL_H),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    # Enforce JWT Bearer token validation exclusively
    if creds:
        payload = _decode_token(creds.credentials)
        if payload is not None:
            return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def _require_admin(user: dict = Depends(_get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ── Schemas ───────────────────────────────────────────────────────────────────

from pydantic import Field

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=4, max_length=100)


class AddEmployeeRequest(BaseModel):
    username:     str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_-]+$")
    password:     str = Field(..., min_length=4, max_length=100)
    display_name: str = Field("", max_length=50)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/login", summary="Authenticate and receive a JWT")
def login(req: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if os.getenv("TESTING") != "true" and not _rl_login.allow(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again after 60 seconds.",
        )
    users = _load_users()
    # Case-insensitive username lookup, stripping extra whitespace
    user  = next((u for u in users if u["username"].lower() == req.username.lower().strip()), None)

    if user is None or not _verify_password(user["password_hash"], req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Auto-upgrade to PBKDF2 hash if legacy SHA256 hash was matched
    if ":" not in user["password_hash"]:
        user["password_hash"] = _hash(req.password)
        _save_users(users)
        logger.info("[auth] password hash auto-upgraded to PBKDF2 for user: %s", user["username"])

    token = _make_token(
        username=user["username"],
        role=user["role"],
        display_name=user.get("display_name", user["username"]),
    )
    logger.info("[auth] login OK: %s (%s)", user["username"], user["role"])
    return {
        "token":        token,
        "username":     user["username"],
        "role":         user["role"],
        "display_name": user.get("display_name", user["username"]),
    }


@router.get("/me", summary="Return current user info from JWT")
def me(user: dict = Depends(_get_current_user)):
    return {
        "username":     user["sub"],
        "role":         user["role"],
        "display_name": user.get("display_name", user["sub"]),
    }


@router.get("/employees", summary="[Admin] List all HR employees")
def list_employees(admin: dict = Depends(_require_admin)):
    users = _load_users()
    return [
        {
            "username":     u["username"],
            "role":         u["role"],
            "display_name": u.get("display_name", u["username"]),
        }
        for u in users
        if u["role"] != "admin"
    ]


@router.post("/employees", summary="[Admin] Add a new HR employee", status_code=201)
def add_employee(req: AddEmployeeRequest, admin: dict = Depends(_require_admin)):
    users = _load_users()
    # Check case-insensitively
    if any(u["username"].lower() == req.username.lower().strip() for u in users):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{req.username}' already exists",
        )
    new_user = {
        "username":     req.username.lower().strip(),  # Store lowercased and stripped
        "password_hash": _hash(req.password),
        "role":         "hr",
        "display_name": req.display_name or req.username,
    }
    users.append(new_user)
    _save_users(users)
    logger.info("[auth] admin added employee: %s", req.username)
    return {"created": True, "username": req.username}


@router.delete("/employees/{username}", summary="[Admin] Remove an HR employee")
def remove_employee(username: str, admin: dict = Depends(_require_admin)):
    users = _load_users()
    # Match case-insensitively
    target = next((u for u in users if u["username"].lower() == username.lower().strip()), None)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )
    if target["role"] == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin account",
        )
    updated = [u for u in users if u["username"].lower() != username.lower().strip()]
    _save_users(updated)
    logger.info("[auth] admin removed employee: %s", username)
    return {"deleted": True, "username": username}
