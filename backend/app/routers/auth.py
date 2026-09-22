from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import (
    create_token,
    decode_token,
    get_current_user,
    token_digest,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import RefreshToken, User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.services import write_audit

router = APIRouter(prefix="/auth", tags=["Auth"])
_ATTEMPTS: dict[str, deque[datetime]] = defaultdict(deque)
_ATTEMPT_LOCK = Lock()
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 10


def _check_login_rate_limit(client_id: str) -> None:
    now = datetime.now(UTC)
    with _ATTEMPT_LOCK:
        attempts = _ATTEMPTS[client_id]
        while attempts and (now - attempts[0]).total_seconds() > _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.", headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)})
        attempts.append(now)


def _issue_tokens(user: User, db: Session) -> TokenResponse:
    access = create_token(user.id, "access", settings.access_token_expire_minutes)
    refresh_minutes = settings.access_token_expire_minutes * 4
    refresh = create_token(user.id, "refresh", refresh_minutes)
    db.add(RefreshToken(user_id=user.id, token_hash=token_digest(refresh), expires_at=datetime.now(UTC) + timedelta(minutes=refresh_minutes)))
    return TokenResponse(access_token=access, refresh_token=refresh, role=user.role, username=user.username, user_id=user.id)  # type: ignore[arg-type]


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _check_login_rate_limit(request.client.host if request.client else "unknown")
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login_at = datetime.now(UTC)
    write_audit(db, "login", "user", user.id, user_id=user.id)
    response = _issue_tokens(user, db)
    db.commit()
    return response


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_digest(body.refresh_token)).first()
    now = datetime.now(UTC)
    expires_at = stored.expires_at.replace(tzinfo=UTC) if stored and stored.expires_at.tzinfo is None else (stored.expires_at if stored else None)
    if not stored or stored.revoked_at or not expires_at or expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    stored.revoked_at = now
    response = _issue_tokens(user, db)
    db.commit()
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        username=user.username,
        role=user.role,  # type: ignore[arg-type]
        site_scope=user.site_scope or [],
        email=user.email,
        is_active=user.is_active,
    )
