"""
PMC Grammars — Language Dispatch
==================================
Dispatches to the right parser based on file extension.

Uses tree-sitter-language-pack when available, falls back to
stdlib `ast` for Python files.
"""

import os
from typing import Optional


# Language registry — maps file extensions to parser modules
_PARSER_REGISTRY: dict[str, str] = {}


def register_parser(extension: str, parser_module: str):
    """Register a parser module for a file extension."""
    _PARSER_REGISTRY[extension] = parser_module


def get_parser(extension: str):
    """Get the parser function for a file extension."""
    module_name = _PARSER_REGISTRY.get(extension)
    if not module_name:
        return None
    try:
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, "extract_symbols", None)
    except Exception:
        return None


def extract_symbols(source: str, fpath: str) -> list[dict]:
    """
    Extract symbols from source code for any registered language.
    Dispatches based on file extension.

    Returns list of symbol dicts with keys:
        name, line_start, line_end, signature, docstring,
        calls, is_class, token_estimate
    """
    ext = os.path.splitext(fpath)[1].lower()
    parser_fn = get_parser(ext)
    if parser_fn:
        return parser_fn(source, fpath)
    return []


def supported_extensions() -> list[str]:
    """Return list of supported file extensions."""
    return list(_PARSER_REGISTRY.keys())


# Register built-in parsers
register_parser(".py", "pmc.grammars.python")
register_parser(".ts", "pmc.grammars.typescript")
register_parser(".tsx", "pmc.grammars.typescript")
