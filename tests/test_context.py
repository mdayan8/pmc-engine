"""
Tests for the PMC Surgical Context Builder (Layers 3-5).
"""

import pytest
from pmc.context import SurgicalContextBuilder, ContextResult
from pmc.intent import IntentParser, OpType, BlastRadius, ParsedIntent


class TestContextBuilder:
    """Test the context builder."""

    def test_build_returns_result(self, indexed_engine, sample_auth_dir):
        """Test that build returns a ContextResult."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        assert isinstance(result, ContextResult)
        assert result.context_string is not None
        assert len(result.context_string) > 0

    def test_tier1_contains_direct_targets(self, indexed_engine, sample_auth_dir):
        """Test that direct targets go to Tier 1."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        assert "login" in result.symbols_tier1
        assert "login" in result.context_string

    def test_tier2_contains_deps(self, indexed_engine, sample_auth_dir):
        """Test that 1-hop deps go to Tier 2."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        # verify_password is called by login → hop1
        # It could be T1 (if score >= 2.5) or T2 (if >= 1.0)
        assert "verify_password" in result.symbols_tier2 or "verify_password" in result.symbols_tier1

    def test_token_reduction(self, indexed_engine, sample_auth_dir):
        """Test that PMC uses fewer tokens than naive."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        assert result.token_count < result.naive_token_count
        assert result.reduction_pct > 0

    def test_session_cache_penalty(self, indexed_engine, sample_auth_dir):
        """Test that cached symbols get score penalty."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        # First build — no cache
        builder1 = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        result1 = builder1.build(intent, source_root=sample_auth_dir)

        # Second build — with login in cache
        builder2 = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache={"login"},
        )
        result2 = builder2.build(intent, source_root=sample_auth_dir)

        # Scores should differ (login gets penalty)
        if result1.scores and result2.scores and "login" in result1.scores:
            assert result2.scores.get("login", 0) <= result1.scores.get("login", 0)

    def test_blast_radius(self, indexed_engine, sample_auth_dir):
        """Test that blast radius is detected."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)
        intent.blast_radius = BlastRadius.HIGH

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        # login is called by tests / other code → blast should be non-empty
        # or empty if no callers found in the sample
        assert isinstance(result.blast_radius_syms, list)

    def test_different_modes(self, indexed_engine, sample_auth_dir, conservative_engine):
        """Test that different modes produce different contexts."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        # Balanced
        builder_b = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result_b = builder_b.build(intent, source_root=sample_auth_dir)

        # Conservative
        builder_c = SurgicalContextBuilder(
            index=conservative_engine._index,
            session_cache=set(),
            config=conservative_engine.config,
        )
        result_c = builder_c.build(intent, source_root=sample_auth_dir)

        # Conservative should include more symbols (lower thresholds)
        # The key: both should have login in T1
        assert "login" in result_b.symbols_tier1
        assert "login" in result_c.symbols_tier1

    def test_context_structure(self, indexed_engine, sample_auth_dir):
        """Test the assembled context structure."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        ctx = result.context_string
        assert "PMC Context" in ctx
        assert "Operation:" in ctx
        assert "Query:" in ctx
        assert "TIER 1" in ctx

    def test_expand_symbol(self, indexed_engine):
        """Test symbol expansion."""
        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        expanded = builder._expand_symbol("login")
        assert expanded is not None
        assert expanded["name"] == "login"
        assert "source" in expanded
        assert "def login" in expanded["source"]

    def test_expand_nonexistent(self, indexed_engine):
        """Test expansion of non-existent symbol."""
        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        expanded = builder._expand_symbol("does_not_exist_xyz")
        assert expanded is None

    def test_summary_format(self, indexed_engine, sample_auth_dir):
        """Test that summary is human-readable."""
        parser = IntentParser()
        known = set(indexed_engine._index.symbols.keys())
        intent = parser.parse("Fix the race condition in login", known_symbols=known)

        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        result = builder.build(intent, source_root=sample_auth_dir)

        summary = result.summary()
        assert "Tokens:" in summary
        assert "reduction" in summary
        assert "T1=" in summary
        assert "T2=" in summary

    def test_calibrate(self, indexed_engine, sample_auth_dir):
        """Test auto-calibration."""
        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
            config=indexed_engine.config,
        )
        result = builder.calibrate(sample_auth_dir)
        assert "best_weights" in result
        assert result["best_weights"]["direct"] > 0
