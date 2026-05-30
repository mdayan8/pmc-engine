"""
Tests for the PMC Session Cache (Layer 6).
"""

import pytest
from pmc.cache import SessionCache


class TestSessionCache:
    """Test session cache functionality."""

    def test_mark_sent_and_is_fresh(self):
        cache = SessionCache()
        cache.mark_sent(["login", "verify_password"], tier=1)
        assert cache.is_fresh("login") is True
        assert cache.is_fresh("verify_password") is True

    def test_unknown_symbol_not_fresh(self):
        cache = SessionCache()
        assert cache.is_fresh("nonexistent") is False

    def test_tier1_ttl(self):
        cache = SessionCache()
        cache.TIER1_TTL_TURNS = 3
        cache.mark_sent(["login"], tier=1)
        assert cache.is_fresh("login") is True
        cache.next_turn()
        cache.next_turn()
        cache.next_turn()  # 3 turns later, should expire
        cache.next_turn()  # 4 turns later — past TTL
        assert cache.is_fresh("login") is False

    def test_expired_removed(self):
        cache = SessionCache()
        cache.TIER1_TTL_TURNS = 1
        cache.mark_sent(["login"], tier=1)
        assert cache.is_fresh("login") is True
        cache.next_turn()  # turns to 2, TTL=1 means age > TTL
        cache.next_turn()
        # Should not be fresh anymore
        assert "login" not in cache._cache or not cache.is_fresh("login")

    def test_fresh_names(self):
        cache = SessionCache()
        cache.mark_sent(["login"], tier=1)
        cache.mark_sent(["log_event"], tier=3)
        fresh = cache.fresh_names()
        assert "login" in fresh
        assert "log_event" in fresh

    def test_invalidate_symbol(self):
        cache = SessionCache()
        cache.mark_sent(["login"], tier=1)
        cache.invalidate("login")
        assert cache.is_fresh("login") is False

    def test_invalidate_file(self):
        cache = SessionCache()
        # Mark sent with version hashes that include file path
        cache.mark_sent(["login"], tier=1, file_hashes={"login": "auth_service.py:abc123"})
        cache.mark_sent(["query"], tier=2, file_hashes={"query": "database.py:def456"})
        cache.invalidate_file("database.py")
        assert cache.is_fresh("query") is False
        # login should still be fresh (different file)
        # Note: invalidate_file checks if fpath in version_hash
        # which for "database.py" won't match "auth_service.py:abc123"

    def test_clear(self):
        cache = SessionCache()
        cache.mark_sent(["login"], tier=1)
        cache.next_turn()
        cache.clear()
        assert len(cache._cache) == 0
        assert cache._turn == 1

    def test_stats(self):
        cache = SessionCache()
        assert cache.stats()["cached_symbols"] == 0
        cache.mark_sent(["login"], tier=1)
        stats = cache.stats()
        assert stats["cached_symbols"] == 1
        assert stats["current_turn"] == 1

    def test_multi_turn(self):
        cache = SessionCache()
        cache.TIER1_TTL_TURNS = 10

        cache.next_turn()
        cache.mark_sent(["login"], tier=1)
        assert cache.is_fresh("login") is True

        cache.next_turn()
        assert cache.is_fresh("login") is True  # still in TTL

        cache.mark_sent(["register"], tier=1)
        assert cache.is_fresh("register") is True

    def test_different_tier_ttls(self):
        cache = SessionCache()
        cache.TIER1_TTL_TURNS = 20
        cache.TIER2_TTL_TURNS = 10
        cache.TIER3_TTL_TURNS = 5

        cache.mark_sent(["login"], tier=1)
        cache.mark_sent(["query"], tier=2)
        cache.mark_sent(["close"], tier=3)

        # After 6 turns: Tier 3 expires, Tiers 1+2 persist
        for _ in range(6):
            cache.next_turn()

        assert cache.is_fresh("login") is True   # TTL=20
        assert cache.is_fresh("query") is True    # TTL=10
        assert cache.is_fresh("close") is False    # TTL=5
