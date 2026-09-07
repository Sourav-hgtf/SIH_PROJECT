from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
try:
    from jose import JWTError, jwt
except ImportError:  # pragma: no cover
    try:
        import jwt
        JWTError = jwt.PyJWTError  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        JWTError = Exception  # type: ignore[assignment,misc]
        jwt = None  # type: ignore[assignment]
import hashlib

try:
    import bcrypt  # type: ignore
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    def verify_password(password: str, password_hash: str) -> bool:
        if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
            try:
                return bcrypt.checkpw(password[:72].encode("utf-8"), password_hash.encode("utf-8"))
            except Exception:
                return False
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash
except ImportError:  # pragma: no cover
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()
    def verify_password(password: str, password_hash: str) -> bool:
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == password_hash

from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {
    "analyst": {"analyst"},
    "site_manager": {"analyst", "site_manager"},
    "leadership": {"leadership"},
    "admin": {"admin"},
}


def create_token(subject: str, token_type: str, minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(creds.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or missing user")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def scoped_site_ids(user: User) -> list[str] | None:
    """Return allowed site IDs, or None for org-wide access."""
    if user.role in ("leadership", "admin"):
        return None
    scope = user.site_scope or []
    return list(scope)
