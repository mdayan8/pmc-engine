"""
Authentication Service — Sample codebase for PMC testing.
"""
import time
from typing import Optional, Dict, Any

from database import query
from crypto import verify_password, hash_password, generate_token
from audit import log_event, log_failed_login


class AuthService:
    """Main authentication service."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.rate_limiter = RateLimiter(
            max_attempts=self.config.get("MAX_LOGIN_ATTEMPTS", 5),
            window_seconds=self.config.get("RATE_LIMIT_WINDOW", 300)
        )
        self._failed_attempts: dict[str, int] = {}

    def login(self, email: str, password: str, ip_address: str) -> Dict[str, Any]:
        """
        Authenticate user and return JWT tokens.

        Args:
            email: User email address
            password: Plain text password
            ip_address: Client IP for rate limiting

        Returns:
            Dict with token and user data

        Raises:
            AuthException: On invalid credentials
            RateLimitException: On too many attempts
        """
        if not self.rate_limiter.check(ip_address):
            log_failed_login(email, ip_address, reason="rate_limited")
            raise RateLimitException("Too many login attempts")

        user = query("SELECT * FROM users WHERE email = ?", (email,))
        if not user:
            log_failed_login(email, ip_address, reason="not_found")
            raise AuthException("Invalid credentials")

        if not verify_password(password, user["password_hash"]):
            log_failed_login(email, ip_address, reason="bad_password")
            self._lock_account(user)
            raise AuthException("Invalid credentials")

        token = generate_token(user["id"], user["email"])
        log_event("login_success", user["id"])
        return {"token": token, "user": user}

    def register(self, email: str, password: str) -> Dict[str, Any]:
        """Register a new user."""
        existing = query("SELECT id FROM users WHERE email = ?", (email,))
        if existing:
            raise AuthException("Email already registered")

        pw_hash = hash_password(password)
        user_id = query(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, pw_hash)
        )
        log_event("user_registered", user_id)
        return {"id": user_id, "email": email}

    def refresh_token(self, token: str) -> Dict[str, Any]:
        """Refresh an expired JWT token."""
        from crypto import verify_token

        payload = verify_token(token)
        if not payload:
            raise AuthException("Invalid or expired token")

        new_token = generate_token(payload["user_id"], payload["email"])
        return {"token": new_token}

    def _lock_account(self, user: dict):
        """Lock account after max failed attempts."""
        self._failed_attempts[user["email"]] = (
            self._failed_attempts.get(user["email"], 0) + 1
        )
        if self._failed_attempts[user["email"]] >= 3:
            query("UPDATE users SET locked = 1 WHERE id = ?", (user["id"],))
            log_event("account_locked", user["id"])


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        """Check if key is within rate limits."""
        now = time.time()
        window_start = now - self.window_seconds
        self._attempts[key] = [
            t for t in self._attempts.get(key, []) if t > window_start
        ]
        if len(self._attempts[key]) >= self.max_attempts:
            return False
        self._attempts[key].append(now)
        return True


class AuthException(Exception):
    """Authentication error."""
    pass


class RateLimitException(Exception):
    """Rate limit exceeded."""
    pass
