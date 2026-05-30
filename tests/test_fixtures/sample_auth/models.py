"""
Data models for the auth service.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class User:
    """User account model."""
    id: int
    email: str
    password_hash: str
    locked: bool = False
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    jwt_token: Optional[str] = None  # Current valid JWT, stored for session management


@dataclass
class AuditEntry:
    """Audit log entry model."""
    id: int
    event_type: str
    user_id: Optional[int] = None
    email: Optional[str] = None
    ip_address: Optional[str] = None
    details: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class RateLimitEntry:
    """Rate limit tracking model."""
    key: str
    attempt_count: int = 0
    window_start: Optional[str] = None
    blocked_until: Optional[str] = None
