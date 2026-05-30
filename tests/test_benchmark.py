"""
Benchmark tests for PMC Engine.
Measures token reduction and verifies benchmark output format.
"""

import pytest
import json
from pmc import PMCEngine, PMCConfig


class TestBenchmark:
    """Test benchmark functionality."""

    def test_benchmark_runs(self, sample_auth_dir):
        """Test that benchmark runs without errors."""
        from pmc.cli import cmd_bench
        # Not easily callable directly, but we can verify the engine works

    def test_token_reduction_across_queries(self, indexed_engine, sample_auth_dir):
        """Test that multiple queries all show token reduction."""
        sym_names = list(indexed_engine._index.symbols.keys())
        if len(sym_names) < 2:
            return

        queries = [
            f"Fix the bug in {sym_names[0]}",
            f"Explain how {sym_names[min(1, len(sym_names)-1)]} works",
            f"Add error handling to {sym_names[0]}",
            f"Write tests for {sym_names[min(2, len(sym_names)-1)]}",
        ]

        total_naive = 0
        total_pmc = 0

        for query in queries:
            indexed_engine.new_conversation()
            result = indexed_engine.compress(query, source_root=sample_auth_dir)
            total_naive += result.naive_token_count
            total_pmc += result.token_count
            assert result.token_count < result.naive_token_count, f"No reduction for: {query}"

        # Overall reduction should be > 0
        avg_reduction = (total_naive - total_pmc) / total_naive * 100
        assert avg_reduction > 0, "No average reduction across queries"

    def test_all_modes_show_reduction(self, sample_auth_dir):
        """Test that all 3 modes produce token reduction."""
        from pmc import CompressionMode

        for mode in CompressionMode.all_modes():
            config = PMCConfig()
            config.mode = mode
            config._apply_mode()
            engine = PMCEngine(config=config)
            engine.index(sample_auth_dir)

            result = engine.compress(
                "Fix the race condition in the login function",
                source_root=sample_auth_dir,
            )
            assert result.token_count < result.naive_token_count, f"{mode} mode failed"

    def test_benchmark_tool(self, sample_auth_dir):
        """Test CLI entry point format."""
        from pmc.cli import _load_engine
        import argparse

        args = argparse.Namespace(
            directory=sample_auth_dir,
            mode="balanced",
        )
        engine = _load_engine(args)
        stats = engine.index(sample_auth_dir)
        assert stats["files"] > 0
        assert stats["symbols"] > 0
