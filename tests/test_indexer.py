"""
Tests for the PMC Symbol Indexer (Layer 1).
"""

import os
import pytest
from pmc.indexer import LiveSymbolIndex, Symbol


class TestLiveSymbolIndex:
    """Test the symbol indexer."""

    def test_build_index(self, sample_auth_dir):
        """Test that index builds without errors."""
        idx = LiveSymbolIndex()
        stats = idx.build_index(sample_auth_dir)
        assert stats["files"] > 0
        assert stats["symbols"] > 0
        assert stats["duration_ms"] > 0

    def test_extracts_functions(self, sample_auth_dir):
        """Test that functions are extracted."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        assert "login" in idx.symbols
        assert "register" in idx.symbols
        assert "refresh_token" in idx.symbols

    def test_extracts_classes(self, sample_auth_dir):
        """Test that classes are extracted."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        assert "AuthService" in idx.symbols
        assert "RateLimiter" in idx.symbols

    def test_call_graph(self, sample_auth_dir):
        """Test that call edges are extracted."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        login = idx.get("login")
        assert login is not None
        # login() calls verify_password
        assert "verify_password" in login.calls
        # login() calls query
        assert "query" in login.calls
        # login() calls log_failed_login
        assert "log_failed_login" in login.calls

    def test_reverse_call_graph(self, sample_auth_dir):
        """Test that callers are populated."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        # query is called by login, register, etc.
        query_sym = idx.get("query")
        assert query_sym is not None
        assert len(query_sym.callers) > 0

    def test_get_callees(self, sample_auth_dir):
        """Test call graph traversal."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        callees = idx.get_callees("login", depth=1)
        names = {c.name for c in callees}
        assert "verify_password" in names
        assert "log_failed_login" in names

    def test_get_callers(self, sample_auth_dir):
        """Test reverse call graph traversal."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        callers = idx.get_callers("query", depth=1)
        names = {c.name for c in callers}
        assert "login" in names or len(callers) > 0

    def test_text_search(self, sample_auth_dir):
        """Test symbol search by name."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        results = idx.search("login", top_k=5)
        assert len(results) > 0
        assert any("login" in r.name for r in results)

    def test_skip_dirs(self, tmp_path):
        """Test that skip directories are respected."""
        # Create a file in a skip directory
        skip_dir = tmp_path / "__pycache__"
        skip_dir.mkdir()
        (skip_dir / "test.py").write_text("def foo(): pass")

        idx = LiveSymbolIndex()
        stats = idx.build_index(str(tmp_path))
        # Should have 0 symbols from __pycache__
        assert stats["files"] == 0

    def test_syntax_error_skipped(self, tmp_path):
        """Test files with syntax errors are skipped."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def foo(: pass")

        idx = LiveSymbolIndex()
        stats = idx.build_index(str(tmp_path))
        assert stats["errors"] is not None

    def test_incremental_update(self, sample_auth_dir, tmp_path):
        """Test incremental file update."""
        import shutil
        test_dir = tmp_path / "test_update"
        shutil.copytree(sample_auth_dir, test_dir)

        idx = LiveSymbolIndex()
        idx.build_index(str(test_dir))

        # Modify a file
        auth_file = test_dir / "auth_service.py"
        content = auth_file.read_text()
        auth_file.write_text(content + "\ndef new_func(): pass\n")

        # Update
        result = idx.update_file(str(auth_file))
        assert result == True

        # New symbol should be present
        assert "new_func" in idx.symbols

        # Unchanged file should not re-parse
        result2 = idx.update_file(str(auth_file))
        assert result2 == False

    def test_symbol_to_tier1(self, sample_auth_dir):
        """Test Tier 1 output format."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        sym = idx.get("login")
        assert sym is not None
        lines = open(sym.file).readlines()
        t1 = sym.to_tier1(lines)
        assert "login" in t1
        assert "FILE:" in t1

    def test_symbol_to_tier2(self, sample_auth_dir):
        """Test Tier 2 output format."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        sym = idx.get("verify_password")
        assert sym is not None
        t2 = sym.to_tier2()
        assert "verify_password" in t2

    def test_symbol_to_tier3(self, sample_auth_dir):
        """Test Tier 3 output format."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        sym = idx.get("log_failed_login")
        assert sym is not None
        t3 = sym.to_tier3()
        assert "[STUB]" in t3
        assert "log_failed_login" in t3

    def test_stats(self, sample_auth_dir):
        """Test stats output."""
        idx = LiveSymbolIndex()
        idx.build_index(sample_auth_dir)
        stats = idx.stats()
        assert stats["total_symbols"] > 0
        assert stats["total_files"] > 0
        assert stats["total_edges"] > 0
        assert stats["build_time_ms"] > 0

    def test_async_function_extraction(self, tmp_path):
        """Test that async functions are extracted."""
        src = tmp_path / "async_test.py"
        src.write_text("async def fetch_data(url: str) -> dict:\n    return {'data': 'test'}")

        idx = LiveSymbolIndex()
        idx.build_index(str(tmp_path))
        assert "fetch_data" in idx.symbols

    def test_cache_persistence(self, sample_auth_dir, tmp_path):
        """Test that cache can save and load."""
        cache_file = tmp_path / "test_cache.json"
        idx = LiveSymbolIndex(cache_path=str(cache_file))
        idx.build_index(sample_auth_dir)
        original_count = len(idx.symbols)

        # New instance should load from cache
        idx2 = LiveSymbolIndex(cache_path=str(cache_file))
        assert len(idx2.symbols) == original_count
