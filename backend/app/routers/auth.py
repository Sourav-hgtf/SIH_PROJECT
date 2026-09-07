from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, verify_password
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.services import write_audit

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.last_login_at = datetime.now(timezone.utc)
    write_audit(db, "login", "user", user.id, user_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_token(user.id, "access", settings.access_token_expire_minutes),
        refresh_token=create_token(user.id, "refresh", settings.access_token_expire_minutes * 4),
        role=user.role,  # type: ignore[arg-type]
        username=user.username,
        user_id=user.id,
    )


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
