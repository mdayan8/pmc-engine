"""
PMC Proxy — Request/Response Compression Middleware
=====================================================
Intercepts HTTP requests to AI APIs and compresses code context.

Works with:
  - Anthropic Messages API (POST /v1/messages)
  - OpenAI Chat Completions API (POST /v1/chat/completions)
"""

import json
import re
from typing import Optional, Any
from pmc import PMCEngine


class PMCProxyCompressor:
    """
    Middleware that compresses code context in AI API requests.

    Usage:
        compressor = PMCProxyCompressor(source_root="./my_project")
        modified_body = compressor.compress_request(body_bytes)
        modified_response = compressor.compress_response(response_body)
    """

    # Pattern to detect code-heavy messages
    _CODE_LINE_PATTERN = re.compile(r'(^\s*(def |class |import |from |async |@|# )|^\s*[a-z_][\w.]+\s*=\s*)', re.MULTILINE)
    _CODE_INDICATOR_PATTERN = re.compile(r'(```\w*\n|\.py|source code|code|function|class|method|file)', re.IGNORECASE)

    def __init__(self, source_root: str = ".", mode: str = "balanced"):
        self.engine = PMCEngine()
        self.source_root = source_root
        self.mode = mode
        self._indexed = False
        self.stats = {
            "requests_processed": 0,
            "total_naive_tokens": 0,
            "total_pmc_tokens": 0,
            "total_savings": 0,
        }

    def ensure_indexed(self):
        """Build index if not already done."""
        if not self._indexed:
            self.engine.index(self.source_root)
            self._indexed = True

    def compress_request(self, body: dict) -> dict:
        """
        Compress code context in an API request body.

        Works by:
        1. Extracting the user's query from the messages
        2. Running PMC compression
        3. Prepending compressed context to the system prompt
        4. Tracking token savings
        """
        self.ensure_indexed()
        self.stats["requests_processed"] += 1

        # Extract user query from messages
        messages = body.get("messages", [])
        user_query = self._extract_user_query(messages)

        if not user_query:
            return body  # No user query found, pass through

        # Run PMC compression
        try:
            result = self.engine.compress(
                user_query,
                source_root=self.source_root,
                new_turn=True,
            )
        except Exception:
            return body  # Compression failed, pass through

        # Track stats
        self.stats["total_naive_tokens"] += result.naive_token_count
        self.stats["total_pmc_tokens"] += result.token_count
        self.stats["total_savings"] += result.saved_tokens

        # Prepend compressed context to the system prompt
        compressed = result.context_string
        if not compressed:
            return body

        # Inject as system prompt prefix or assistant message prefix
        system = body.get("system", "")
        if system:
            body["system"] = compressed + "\n\n" + system
        else:
            # Check if first message is system
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = compressed + "\n\n" + messages[0]["content"]
            else:
                # Add as a new system message
                body["system"] = compressed

        return body

    def compress_response(self, body: dict) -> dict:
        """
        Compress AI response by replacing known code blocks with [REF] stubs.

        (Response compression is optional and best-effort.)
        """
        return body  # Pass through for now (response compression is a future optimization)

    def _extract_user_query(self, messages: list[dict]) -> str:
        """Extract the most recent user message."""
        for msg in reversed(messages):
            if msg.get("role") in ("user", "human"):
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Handle content blocks
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    return "\n".join(texts)
                return content
        return ""

    def get_stats(self) -> dict:
        stats = dict(self.stats)
        if self.stats["total_naive_tokens"] > 0:
            stats["avg_reduction_pct"] = round(
                100 * self.stats["total_savings"] / self.stats["total_naive_tokens"], 1
            )
        else:
            stats["avg_reduction_pct"] = 0
        return stats
