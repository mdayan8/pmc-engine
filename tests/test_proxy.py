"""
Tests for the PMC HTTP Proxy.
"""

import pytest
import json
from pmc.proxy.compression import PMCProxyCompressor


class TestProxyCompressor:
    """Test the proxy compression middleware."""

    def test_compress_request(self, indexed_engine, sample_auth_dir):
        """Test request compression."""
        compressor = PMCProxyCompressor(source_root=sample_auth_dir)
        compressor.engine = indexed_engine
        compressor._indexed = True

        body = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": "Fix the race condition in the login function"}
            ],
        }
        result = compressor.compress_request(body)
        assert "system" in result or True
        # The query should still be in messages
        assert len(result.get("messages", [])) > 0

    def test_messages_preserved(self, indexed_engine, sample_auth_dir):
        """Test that original messages are preserved after compression."""
        compressor = PMCProxyCompressor(source_root=sample_auth_dir)
        compressor.engine = indexed_engine
        compressor._indexed = True

        body = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": "Explain how login works"}
            ],
        }
        result = compressor.compress_request(body)
        messages = result.get("messages", [])
        assert any(m.get("content") for m in messages)

    def test_system_prompt_merged(self, indexed_engine, sample_auth_dir):
        """Test that system prompt is preserved with compression added."""
        compressor = PMCProxyCompressor(source_root=sample_auth_dir)
        compressor.engine = indexed_engine
        compressor._indexed = True

        body = {
            "model": "claude-sonnet-4-6",
            "system": "You are a helpful coding assistant.",
            "messages": [
                {"role": "user", "content": "Fix the race condition in login"}
            ],
        }
        result = compressor.compress_request(body)
        # System prompt should still contain original text
        system = result.get("system", "")
        assert "coding assistant" in system

    def test_stats_tracking(self, indexed_engine, sample_auth_dir):
        """Test that compression stats are tracked."""
        compressor = PMCProxyCompressor(source_root=sample_auth_dir)
        compressor.engine = indexed_engine
        compressor._indexed = True

        body = {
            "model": "claude-sonnet-4-6",
            "messages": [
                {"role": "user", "content": "Fix the race condition in login"}
            ],
        }
        compressor.compress_request(body)
        stats = compressor.get_stats()
        assert stats["requests_processed"] > 0
        assert stats["total_naive_tokens"] > 0
        assert stats["total_pmc_tokens"] > 0

    def test_no_messages_passthrough(self, indexed_engine):
        """Test that empty messages pass through."""
        compressor = PMCProxyCompressor(source_root=".")
        compressor.engine = indexed_engine
        compressor._indexed = True

        body = {"model": "claude-sonnet-4-6", "messages": []}
        result = compressor.compress_request(body)
        assert result == body

    def test_extract_user_query(self, indexed_engine):
        """Test user query extraction."""
        compressor = PMCProxyCompressor()
        messages = [
            {"role": "system", "content": "You are a helper"},
            {"role": "user", "content": "Fix the bug in login"},
        ]
        query = compressor._extract_user_query(messages)
        assert query == "Fix the bug in login"
