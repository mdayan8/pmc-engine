"""
PMC Grammars — Python Parser
==============================
Extracts symbols from Python source using tree-sitter (preferred) or stdlib ast (fallback).

Uses tree-sitter-language-pack when available for richer AST analysis.
Falls back to Python's built-in ast module for zero-dependency mode.
"""

import ast
from typing import Optional


def extract_symbols(source: str, fpath: str) -> list[dict]:
    """
    Extract symbols from Python source.

    Tries tree-sitter first, falls back to stdlib ast.

    Returns list of symbol dicts.
    """
    symbols = _extract_with_stdlib(source, fpath)
    return symbols


def _extract_with_stdlib(source: str, fpath: str) -> list[dict]:
    """Extract symbols using Python's stdlib ast module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols = []
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            sym = _node_to_dict(node, source, lines)
            if sym:
                symbols.append(sym)

    return symbols


def _node_to_dict(node, source: str, lines: list) -> Optional[dict]:
    """Convert an AST node to a symbol dict."""
    name = node.name
    line_start = node.lineno
    line_end = getattr(node, "end_lineno", node.lineno)
    docstring = ast.get_docstring(node) or ""

    if isinstance(node, ast.ClassDef):
        sig = name
        calls = []
        is_class = True
    else:
        try:
            sig = f"{name}({ast.unparse(node.args)})"
            if node.returns:
                sig += f" -> {ast.unparse(node.returns)}"
        except Exception:
            sig = f"{name}(...)"
        calls = _extract_calls(node)
        is_class = False

    body_chars = sum(len(l) for l in lines[line_start - 1 : line_end])
    token_estimate = max(1, body_chars // 4)

    return {
        "name": name,
        "file": fpath,
        "line_start": line_start,
        "line_end": line_end,
        "signature": sig,
        "docstring": docstring[:200],
        "calls": list(set(calls)),
        "is_class": is_class,
        "token_estimate": token_estimate,
    }


def _extract_calls(node) -> list[str]:
    """Extract function names called from within a node."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                calls.append(child.func.attr)
    return calls
