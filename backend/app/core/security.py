import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# Initialize the password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plain text password using passlib bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain text password against its matching hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    """
    Generate a short-lived JWT access token.
    Uses python-jose, HS256 algorithm, and a 30-minute expiration.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
    return encoded_jwt


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Generate a long-lived JWT refresh token with an explicit JTI claim.
    Returns a tuple containing: (raw_jwt_string, jti_uuid_string)
    Uses REFRESH_SECRET_KEY and a 30-day expiration.
    """
    settings = get_settings()
    jti_uuid = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "jti": jti_uuid
    }
    
    raw_token = jwt.encode(to_encode, settings.refresh_secret_key, algorithm="HS256")
    return raw_token, jti_uuid


def hash_token(raw_token: str) -> str:
    """
    Generate a secure SHA-256 hash of a raw token string.
    This prevents database exposure of active refresh tokens.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Raises an HTTP 401 Unauthorized exception if invalid or expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_refresh_token(token: str) -> dict:
    """
    Decode and validate a JWT refresh token.
    Raises an HTTP 401 Unauthorized exception if invalid or expired.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.refresh_secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token",
        )