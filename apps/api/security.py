from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import ClientSession, Onboarding, User, UserSession, utcnow


password_hasher = PasswordHasher()
APP_MODE = os.getenv("APP_MODE", "DEMO").upper()
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "demo-internal-key")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "demo-webhook-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
PORTAL_SIGNING_KEY = os.getenv("PORTAL_SIGNING_KEY", INTERNAL_KEY)
OPERATOR_SESSION_HOURS = 8
CLIENT_SESSION_HOURS = 4

if os.getenv("CONNECTOR_MODE", "demo").lower() == "connected":
    if APP_MODE != "CONNECTED" or os.getenv("MODEL_MODE", "demo").lower() != "connected":
        raise RuntimeError("APP_MODE and MODEL_MODE must both be connected when CONNECTOR_MODE is connected")
    for name, value in (("INTERNAL_KEY", INTERNAL_KEY), ("WEBHOOK_SECRET", WEBHOOK_SECRET)):
        if len(value) < 32 or value.startswith("demo-") or value.startswith("REPLACE_WITH_"):
            raise RuntimeError(f"{name} must be a unique random secret of at least 32 characters in connected mode")
    if hmac.compare_digest(INTERNAL_KEY, WEBHOOK_SECRET):
        raise RuntimeError("INTERNAL_KEY and WEBHOOK_SECRET must differ in connected mode")
    if not COOKIE_SECURE:
        raise RuntimeError("COOKIE_SECURE=true is required in connected mode")


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(36)


def csrf_for_session(token: str) -> str:
    return hmac.new(INTERNAL_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


def portal_token_for(onboarding_id: str, plan_id: str) -> str:
    return hmac.new(PORTAL_SIGNING_KEY.encode(), f"portal:{onboarding_id}:{plan_id}".encode(), hashlib.sha256).hexdigest()


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def verify_webhook(payload: dict, signature: str | None) -> None:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), canonical, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid event signature")


@dataclass
class OperatorActor:
    user: User
    session: UserSession
    via_cookie: bool


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def operator_actor(request: Request, db: Session = Depends(get_db)) -> OperatorActor:
    bearer = _bearer_token(request)
    token = bearer or request.cookies.get("clientlaunch_session")
    if not token:
        raise HTTPException(status_code=401, detail="Operator login required")
    record = db.scalar(select(UserSession).where(UserSession.token_hash == digest(token)))
    if not record or record.revoked_at or aware(record.expires_at) <= utcnow() or not record.user.active:
        raise HTTPException(status_code=401, detail="Session expired")
    if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
        submitted = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(record.csrf_token_hash, digest(submitted)):
            raise HTTPException(status_code=403, detail="CSRF token required")
    return OperatorActor(record.user, record, not bool(bearer))


def operator_writer(actor: OperatorActor = Depends(operator_actor)) -> OperatorActor:
    if actor.user.role not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Operator role required")
    return actor


def internal_service(x_internal_key: str | None = Header(default=None)) -> None:
    if not x_internal_key or not hmac.compare_digest(x_internal_key, INTERNAL_KEY):
        raise HTTPException(status_code=401, detail="Internal service key required")


def client_onboarding(request: Request, db: Session = Depends(get_db)) -> Onboarding:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Client session required")
    session = db.scalar(select(ClientSession).where(ClientSession.token_hash == digest(token)))
    if not session or session.revoked_at or aware(session.expires_at) <= utcnow():
        raise HTTPException(status_code=401, detail="Client session expired")
    onboarding = db.get(Onboarding, session.onboarding_id)
    if onboarding is None:
        raise HTTPException(status_code=404, detail="Onboarding unavailable")
    return onboarding


def fresh_session_expiry(client: bool = False):
    return utcnow() + timedelta(hours=CLIENT_SESSION_HOURS if client else OPERATOR_SESSION_HOURS)
