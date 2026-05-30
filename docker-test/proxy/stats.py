"""
Token budget tracker for proxy containers.

Tracks input tokens, output tokens, and enforces a hard budget cap.
"""

import time
import threading
from collections import deque


class TokenBudgetTracker:
    """
    Tracks token usage and enforces budget caps.
    Thread-safe for concurrent requests.
    """

    def __init__(self, budget: int = 60000, name: str = "proxy"):
        self.budget = budget
        self.name = name
        self._lock = threading.Lock()

        # Running totals
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.total_tokens: int = 0
        self.request_count: int = 0
        self.query_log: deque[dict] = deque(maxlen=200)

        # Start time
        self.start_time: float = time.time()

        # Budget exhausted flag
        self.exhausted: bool = False

    def track_request(self, query: str, input_tokens: int, output_tokens: int,
                      naive_tokens: int = 0, reduction_pct: float = 0.0) -> bool:
        """
        Track a completed request. Returns True if budget remains, False if exhausted.
        """
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.total_tokens += input_tokens + output_tokens
            self.request_count += 1

            self.query_log.append({
                "query": query[:80],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "naive_tokens": naive_tokens,
                "reduction_pct": reduction_pct,
                "timestamp": time.time(),
                "budget_remaining": self.budget - self.total_tokens,
            })

            if not self.exhausted and self.total_tokens >= self.budget:
                self.exhausted = True
                return False

            return self.total_tokens < self.budget

    def check_budget(self, estimated_tokens: int = 0) -> bool:
        """
        Check if a request fits within budget.
        Called BEFORE forwarding the request.
        """
        with self._lock:
            if self.exhausted:
                return False
            if self.total_tokens + estimated_tokens > self.budget:
                return False
            return True

    def estimated_input_tokens(self, text: str) -> int:
        """Rough estimate: ~4 chars per token for code."""
        return max(1, len(text) // 4)

    def stats(self) -> dict:
        """Get current statistics snapshot."""
        elapsed = time.time() - self.start_time
        with self._lock:
            return {
                "name": self.name,
                "budget": self.budget,
                "total_tokens": self.total_tokens,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "request_count": self.request_count,
                "budget_remaining": max(0, self.budget - self.total_tokens),
                "budget_used_pct": round(self.total_tokens / max(self.budget, 1) * 100, 1),
                "exhausted": self.exhausted,
                "elapsed_seconds": round(elapsed, 1),
                "recent_queries": list(self.query_log)[-20:],
            }

    def reset(self):
        """Reset all counters."""
        with self._lock:
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_tokens = 0
            self.request_count = 0
            self.query_log.clear()
            self.start_time = time.time()
            self.exhausted = False
