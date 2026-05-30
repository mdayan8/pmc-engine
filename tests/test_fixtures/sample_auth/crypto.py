"""
Cryptography utilities — Password hashing and token generation.
"""
import hashlib
import jwt as pyjwt
from datetime import datetime, timedelta
from typing import Optional


JWT_SECRET = "test-secret-key"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24


def hash_password(password: str) -> str:
    """Hash a password using bcrypt-style SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(plain) == hashed


def generate_token(user_id: int, email: str) -> str:
    """Generate a JWT token for a user."""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None
