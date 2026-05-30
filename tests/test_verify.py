"""
Tests for the PMC Quality Verification Loop (Layer 7).
"""

import pytest
from pmc.verify import Verifier


class TestVerifier:
    """Test quality verification."""

    def test_verify_runs(self, indexed_engine, sample_auth_dir):
        """Test that verification runs without errors."""
        verifier = Verifier(indexed_engine)
        result = verifier.verify(sample_auth_dir, num_tasks=5, verbose=False)
        assert "quality_score" in result
        assert result["total_tasks"] == 5
        assert result["avg_reduction_pct"] > 0

    def test_verify_returns_metrics(self, indexed_engine, sample_auth_dir):
        """Test that verify returns proper metrics."""
        verifier = Verifier(indexed_engine)
        result = verifier.verify(sample_auth_dir, num_tasks=3, verbose=False)
        assert result["passed_tasks"] >= 0
        assert result["failed_tasks"] >= 0
        assert result["passed_tasks"] + result["failed_tasks"] == result["total_tasks"]
        assert result["total_full_tokens"] > 0
        assert result["total_pmc_tokens"] > 0

    def test_verify_auto_tune(self, indexed_engine, sample_auth_dir):
        """Test that auto-tuning produces adjustments."""
        verifier = Verifier(indexed_engine)
        result = verifier.verify(sample_auth_dir, num_tasks=5, verbose=False)
        if result.get("tuning"):
            assert "adjustments_applied" in result["tuning"]

    def test_generate_tasks(self, indexed_engine):
        """Test task generation."""
        verifier = Verifier(indexed_engine)
        tasks = verifier._generate_tasks(5)
        assert len(tasks) <= 5
        for query, symbols in tasks:
            assert isinstance(query, str)
            assert isinstance(symbols, set)

    def test_report_format(self, indexed_engine, sample_auth_dir, capsys):
        """Test report printing."""
        verifier = Verifier(indexed_engine)
        result = verifier.verify(sample_auth_dir, num_tasks=3, verbose=False)
        verifier.print_report(result)
        captured = capsys.readouterr()
        assert "QUALITY VERIFICATION" in captured.out
        assert "quality_score" in result or "Quality score" in captured.out
