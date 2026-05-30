"""
Audit logging — Track authentication events.
"""
from database import query
from typing import Optional


def log_event(event_type: str, user_id: int, details: Optional[str] = None):
    """
    Log an authentication event to the audit trail.

    Args:
        event_type: Type of event (login_success, user_registered, etc.)
        user_id: ID of the affected user
        details: Optional additional details
    """
    query(
        "INSERT INTO audit_log (event_type, user_id, details) VALUES (?, ?, ?)",
        (event_type, user_id, details)
    )


def log_failed_login(email: str, ip_address: str, reason: str):
    """
    Log a failed login attempt.

    Args:
        email: Email used in attempt
        ip_address: Client IP
        reason: Failure reason (rate_limited, not_found, bad_password)
    """
    query(
        "INSERT INTO audit_log (event_type, email, ip_address, details) "
        "VALUES ('login_failed', ?, ?, ?)",
        (email, ip_address, reason)
    )
