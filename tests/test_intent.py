"""
Tests for the PMC Intent Parser (Layer 2).
"""

import pytest
from pmc.intent import IntentParser, OpType, BlastRadius


class TestIntentParser:
    """Test the hybrid intent parser."""

    @pytest.fixture
    def parser(self):
        return IntentParser(use_embeddings=False)

    def test_classify_debug(self, parser):
        intent = parser.parse("Fix the race condition in the login function")
        assert intent.op_type in (OpType.DEBUG, OpType.MODIFY)
        assert "login" in intent.target_syms or intent.confidence > 0

    def test_classify_modify(self, parser):
        intent = parser.parse("Update the JWT expiry to 24 hours")
        assert intent.op_type in (OpType.MODIFY, OpType.DEBUG)
        assert intent.confidence > 0.3

    def test_classify_create(self, parser):
        intent = parser.parse("Add a new endpoint for password reset")
        assert intent.op_type == OpType.CREATE

    def test_classify_read(self, parser):
        intent = parser.parse("Explain how the password reset flow works")
        assert intent.op_type == OpType.READ
        assert intent.blast_radius == BlastRadius.LOW

    def test_classify_refactor(self, parser):
        intent = parser.parse("Refactor the auth module to use dependency injection")
        assert intent.op_type == OpType.REFACTOR

    def test_classify_test(self, parser):
        intent = parser.parse("Write unit tests for the login function")
        assert intent.op_type in (OpType.TEST, OpType.CREATE)  # 'write' = CREATE, 'test' = TEST; tiebreak resolves first

    def test_classify_unknown(self, parser):
        intent = parser.parse("What time is it")
        assert intent.op_type == OpType.UNKNOWN
        assert intent.confidence == 0.0

    def test_extract_known_symbols(self, parser):
        known = {"login", "verify_password", "auth_service"}
        intent = parser.parse("Fix the bug in login and verify_password", known_symbols=known)
        assert "login" in intent.target_syms
        assert "verify_password" in intent.target_syms

    def test_extract_camel_case(self, parser):
        """Test extraction of CamelCase symbols."""
        intent = parser.parse("Fix the AuthService class", known_symbols=set())
        assert "AuthService" in intent.target_syms

    def test_extract_snake_case(self, parser):
        """Test extraction of snake_case identifiers."""
        intent = parser.parse("Fix the rate_limiter function", known_symbols=set())
        assert "rate_limiter" in intent.target_syms

    def test_blast_radius_high(self, parser):
        intent = parser.parse("Update the database connection pool")
        assert intent.blast_radius == BlastRadius.HIGH

    def test_blast_radius_low_read(self, parser):
        intent = parser.parse("Show me the config values")
        assert intent.blast_radius == BlastRadius.LOW

    def test_context_budget(self, parser):
        intent = parser.parse("Refactor the entire authentication system")
        assert intent.context_budget >= 4000  # REFACTOR + HIGH blast

    def test_priority_terms(self, parser):
        intent = parser.parse("Fix the password validation rate limiting")
        assert len(intent.priority_terms) > 0
        assert "password" in intent.priority_terms
        assert "validation" in intent.priority_terms
        assert "limiting" in intent.priority_terms

    def test_multiple_targets(self, parser):
        known = {"login", "register", "refresh_token"}
        intent = parser.parse("Fix login and optimize register and update refresh_token",
                              known_symbols=known)
        assert len(intent.target_syms) >= 2
        assert intent.blast_radius in (BlastRadius.MEDIUM, BlastRadius.HIGH)  # 3+ targets or 'login' keyword

    def test_confidence(self, parser):
        intent = parser.parse("Fix the bug login crash")
        assert intent.confidence > 0.5  # High confidence

    def test_confidence_low(self, parser):
        intent = parser.parse("Hmm maybe look at that thing over there")
        assert intent.confidence < 0.5

    def test_conservative_on_unknown(self, parser):
        intent = parser.parse("Qqq xxx zzz yyy www")
        assert intent.confidence == 0.0
        # When unknown, budget should be generous
        assert intent.context_budget >= 2500
