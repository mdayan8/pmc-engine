"""
API Middleware — Request preprocessing.
"""
import time
from typing import Callable
from database import query


REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_SIZE_KB = 100


class RequestMiddleware:
    """Middleware for request preprocessing."""

    def __init__(self):
        self._start_times: dict[str, float] = {}

    def validate_request(self, body: dict) -> bool:
        """Validate incoming request body."""
        if not body:
            return False
        if len(str(body)) > MAX_REQUEST_SIZE_KB * 1024:
            return False
        return True

    def track_request(self, request_id: str):
        """Track request timing."""
        self._start_times[request_id] = time.time()

    def get_latency(self, request_id: str) -> float:
        """Get request processing latency in seconds."""
        start = self._start_times.pop(request_id, None)
        return time.time() - start if start else 0

    def check_timeout(self, start_time: float) -> bool:
        """Check if request has exceeded timeout."""
        return time.time() - start_time > REQUEST_TIMEOUT_SECONDS
