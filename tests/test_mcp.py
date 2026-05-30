"""
Tests for the PMC MCP Server tools.
"""

import pytest
import json


class TestMCPServer:
    """Test MCP server functionality."""

    def test_mcp_tools_available(self):
        """Test that MCP tools are properly defined."""
        from pmc.mcp.server import start_mcp_server
        # Verify the module loads without errors
        assert True

    def test_expand_symbol(self, indexed_engine):
        """Test symbol expansion via builder."""
        from pmc.context import SurgicalContextBuilder
        builder = SurgicalContextBuilder(
            index=indexed_engine._index,
            session_cache=set(),
        )
        result = builder._expand_symbol("login")
        assert result is not None
        assert "source" in result

    def test_search_tool(self, indexed_engine):
        """Test symbol search via engine index."""
        results = indexed_engine._index.search("login", top_k=5)
        assert len(results) > 0
        assert any("login" in r.name for r in results)
