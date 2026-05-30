"""
PMC Engine — MCP Server
=========================
MCP (Model Context Protocol) server that exposes PMC compression
tools to AI assistants like Claude Code and Cursor.

Tools:
  - pmc_index              Build/update symbol index
  - pmc_compress           Compress a query into minimal context
  - pmc_expand             Expand a stubbed symbol to full source
  - pmc_stats              Get compression statistics
  - pmc_search             Search symbol index
  - pmc_clear_cache        Reset session cache

Resources:
  - pmc://file/{path}?mode=   Compressed file view
  - pmc://stats                Compression statistics
"""

import os
import json
import sys
from typing import Any

from pmc import PMCEngine


def start_mcp_server(mode: str = "balanced", source_root: str = "."):
    """Start the MCP stdio server."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("  ⚠ mcp package required for MCP server mode.")
        print("  Install: pip install 'pmc-engine[mcp]'")
        return

    engine = PMCEngine()
    app = FastMCP("PMC Engine", log_level="ERROR")

    @app.tool()
    def pmc_index(directory: str = ".") -> str:
        """Build or update the symbol index for a codebase directory."""
        stats = engine.index(directory)
        return json.dumps(stats, indent=2)

    @app.tool()
    def pmc_compress(query: str, source_root: str = ".") -> str:
        """
        Compress a developer query into surgical minimal context.
        Returns tiered context string with full code, signatures, and stubs.
        """
        if not engine._indexed:
            engine.index(source_root)
        result = engine.compress(query, source_root=source_root)
        return result.context_string

    @app.tool()
    def pmc_expand(symbol_name: str, source_root: str = ".") -> str:
        """
        Expand a stubbed symbol to its full source code.
        Use this when the AI needs to see the complete implementation.
        """
        if not engine._indexed:
            engine.index(source_root)
        from pmc.context import SurgicalContextBuilder
        builder = SurgicalContextBuilder(
            index=engine._index,
            session_cache=set(),
            config=engine.config,
        )
        expanded = builder._expand_symbol(symbol_name)
        if expanded:
            return f"# FILE: {expanded['file']} lines {expanded['line_start']}–{expanded['line_end']}\n{expanded['source']}"
        return f"Symbol '{symbol_name}' not found in index."

    @app.tool()
    def pmc_stats() -> str:
        """Get PMC compression statistics and metrics."""
        stats = engine.stats()
        if stats.get("index", {}).get("total_symbols", 0) == 0:
            return "No index built yet. Run pmc_index first."
        return json.dumps(stats, indent=2)

    @app.tool()
    def pmc_search(query: str, top_k: int = 10) -> str:
        """
        Search the symbol index for functions, classes, and methods
        matching the query text.
        """
        results = engine._index.search(query, top_k=top_k)
        if not results:
            return "No matching symbols found."
        lines = [f"Found {len(results)} symbols:\n"]
        for sym in results:
            lines.append(f"  {sym.name} → {sym.file}:{sym.line_start}")
            if sym.docstring:
                lines.append(f"    {sym.docstring[:80]}")
        return "\n".join(lines)

    @app.tool()
    def pmc_calibrate(source_root: str = ".") -> str:
        """
        Auto-calibrate scoring weights for this codebase.
        Run after indexing to optimize compression for your project.
        """
        if not engine._indexed:
            engine.index(source_root)
        result = engine.calibrate(source_root)
        return json.dumps(result, indent=2)

    @app.resource("pmc://file/{path:path}")
    def pmc_file_resource(path: str, mode: str = "compact") -> str:
        """
        Serve a compressed view of a file.
        Modes:
          skeleton — signatures only
          compact  — signatures + docstrings (default)
          full     — complete file
        """
        full_path = os.path.join(source_root, path)
        if not os.path.exists(full_path):
            return f"File not found: {path}"

        try:
            source = open(full_path, encoding="utf-8").read()
        except Exception as e:
            return f"Error reading file: {e}"

        if mode == "full":
            return f"# {path}\n{source}"
        elif mode == "skeleton":
            # Extract just signatures using grammars
            syms = engine._index.file_to_symbols.get(full_path, [])
            lines = [f"# {path} (skeleton)\n"]
            for name in syms:
                sym = engine._index.get(name)
                if sym:
                    lines.append(f"# Line {sym.line_start}: {sym.signature}")
            return "\n".join(lines)
        else:  # compact — signatures + docstrings
            syms = engine._index.file_to_symbols.get(full_path, [])
            lines = [f"# {path} (compact)\n"]
            for name in syms:
                sym = engine._index.get(name)
                if sym:
                    doc = f"  \"\"\"{sym.docstring[:100]}\"\"\"" if sym.docstring else ""
                    lines.append(f"# Line {sym.line_start}: {sym.signature}  {doc}")
            return "\n".join(lines)

    @app.resource("pmc://stats")
    def pmc_stats_resource() -> str:
        """Get compression statistics as a resource."""
        try:
            stats = engine.stats()
            return json.dumps(stats, indent=2)
        except Exception:
            return '{"status": "not_initialized"}'

    @app.tool()
    def pmc_clear_cache() -> str:
        """Reset the session cache for a fresh conversation."""
        engine.new_conversation()
        return "Session cache cleared."

    # Run the server
    app.run(transport="stdio")
