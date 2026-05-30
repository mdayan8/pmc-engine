"""
PMC Grammars — TypeScript/TSX Parser
======================================
Extracts symbols from TypeScript source using tree-sitter-language-pack.
Falls back to regex-based extraction if tree-sitter is not installed.
"""

import re
from typing import Optional


def extract_symbols(source: str, fpath: str) -> list[dict]:
    """
    Extract symbols from TypeScript/TSX source.
    Tries tree-sitter first, falls back to regex.
    """
    symbols = _extract_with_treesitter(source, fpath)
    if symbols:
        return symbols
    return _extract_with_regex(source, fpath)


def _extract_with_treesitter(source: str, fpath: str) -> Optional[list[dict]]:
    """Extract symbols using tree-sitter-language-pack."""
    try:
        from tree_sitter_language_pack import process, ProcessConfig
        from tree_sitter_language_pack import SupportedLanguages

        lang = "typescript" if fpath.endswith(".ts") else "tsx"
        result = process(source, ProcessConfig(language=lang))

        symbols = []
        lines = source.splitlines(keepends=True)

        # Extract functions
        for func in getattr(result, "functions", []):
            name = getattr(func, "name", "unknown")
            line_start = getattr(func, "line_start", 1)
            line_end = getattr(func, "line_end", 1)
            docstring = getattr(func, "docstring", "") or ""

            # Build signature from params
            params = getattr(func, "parameters", [])
            if isinstance(params, list):
                sig = f"{name}({', '.join(p if isinstance(p, str) else str(p) for p in params)})"
            else:
                sig = f"{name}(...)"
            return_type = getattr(func, "return_type", "")
            if return_type:
                sig += f": {return_type}"

            body_chars = sum(len(l) for l in lines[line_start - 1 : line_end])
            token_estimate = max(1, body_chars // 4)

            calls = getattr(func, "calls", [])
            if isinstance(calls, list):
                call_names = [c if isinstance(c, str) else str(c) for c in calls]
            else:
                call_names = []

            symbols.append({
                "name": name,
                "file": fpath,
                "line_start": line_start,
                "line_end": line_end,
                "signature": sig,
                "docstring": docstring[:200],
                "calls": call_names,
                "is_class": False,
                "token_estimate": token_estimate,
            })

        # Extract classes
        for cls in getattr(result, "classes", []):
            name = getattr(cls, "name", "unknown")
            line_start = getattr(cls, "line_start", 1)
            line_end = getattr(cls, "line_end", 1)
            docstring = getattr(cls, "docstring", "") or ""

            body_chars = sum(len(l) for l in lines[line_start - 1 : line_end])
            token_estimate = max(1, body_chars // 4)

            symbols.append({
                "name": name,
                "file": fpath,
                "line_start": line_start,
                "line_end": line_end,
                "signature": f"class {name}",
                "docstring": docstring[:200],
                "calls": [],
                "is_class": True,
                "token_estimate": token_estimate,
            })

        return symbols if symbols else None
    except ImportError:
        return None
    except Exception:
        return None


def _extract_with_regex(source: str, fpath: str) -> list[dict]:
    """
    Fallback: extract symbols using regex patterns for TypeScript.
    Less accurate but zero-dependency.
    """
    symbols = []
    lines = source.splitlines(keepends=True)

    # Match function declarations
    func_pattern = re.compile(
        r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*(\w+(?:<[^>]*>)?))?'
    )
    for m in func_pattern.finditer(source):
        name = m.group(1)
        params = m.group(2)
        sig = f"{name}({params})"
        if m.group(3):
            sig += f": {m.group(3)}"

        # Find line number
        line_start = source[:m.start()].count("\n") + 1
        line_end = _find_block_end(lines, line_start)

        body_chars = sum(len(l) for l in lines[line_start - 1 : line_end]) if line_end >= line_start else 1
        token_estimate = max(1, body_chars // 4)

        symbols.append({
            "name": name,
            "file": fpath,
            "line_start": line_start,
            "line_end": line_end,
            "signature": sig,
            "docstring": "",
            "calls": list(set(_extract_call_names(source[m.start():m.end() + 500]))),
            "is_class": False,
            "token_estimate": token_estimate,
        })

    # Match arrow functions assigned to const/let
    arrow_pattern = re.compile(
        r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*(?::\s*(\w+))?\s*=>'
    )
    for m in arrow_pattern.finditer(source):
        name = m.group(1)

        # Skip if already captured as a named function
        if any(s["name"] == name for s in symbols):
            continue

        sig = f"{name}({m.group(2)})"
        if m.group(3):
            sig += f": {m.group(3)}"

        line_start = source[:m.start()].count("\n") + 1
        line_end = _find_arrow_block_end(lines, line_start)

        body_chars = sum(len(l) for l in lines[line_start - 1 : line_end]) if line_end >= line_start else 1
        token_estimate = max(1, body_chars // 4)

        symbols.append({
            "name": name,
            "file": fpath,
            "line_start": line_start,
            "line_end": line_end,
            "signature": sig,
            "docstring": "",
            "calls": list(set(_extract_call_names(source[m.start():m.end() + 500]))),
            "is_class": False,
            "token_estimate": token_estimate,
        })

    # Match class declarations
    class_pattern = re.compile(
        r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?'
    )
    for m in class_pattern.finditer(source):
        name = m.group(1)
        extends = m.group(2) or ""

        sig = f"class {name}"
        if extends:
            sig += f" extends {extends}"

        line_start = source[:m.start()].count("\n") + 1
        line_end = _find_block_end(lines, line_start)

        body_chars = sum(len(l) for l in lines[line_start - 1 : line_end]) if line_end >= line_start else 1
        token_estimate = max(1, body_chars // 4)

        symbols.append({
            "name": name,
            "file": fpath,
            "line_start": line_start,
            "line_end": line_end,
            "signature": sig,
            "docstring": "",
            "calls": [],
            "is_class": True,
            "token_estimate": token_estimate,
        })

    return symbols


def _find_block_end(lines: list[str], start_line: int) -> int:
    """Find the closing brace of a block starting at start_line."""
    if start_line > len(lines):
        return start_line
    brace_depth = 0
    found_opening = False
    for i in range(start_line - 1, len(lines)):
        line = lines[i]
        for ch in line:
            if ch == '{':
                brace_depth += 1
                found_opening = True
            elif ch == '}':
                brace_depth -= 1
                if found_opening and brace_depth <= 0:
                    return i + 1
    return len(lines)


def _find_arrow_block_end(lines: list[str], start_line: int) -> int:
    """Find the end of an arrow function body."""
    if start_line > len(lines):
        return start_line
    brace_depth = 0
    found_opening = False
    # Check if arrow body uses braces or is expression-only
    for i in range(start_line - 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("=>") and len(stripped) > 2 and stripped[2] != '{':
            # Expression body (single line)
            return i + 1
        for ch in line:
            if ch == '{':
                brace_depth += 1
                found_opening = True
            elif ch == '}':
                brace_depth -= 1
                if found_opening and brace_depth <= 0:
                    return i + 1
    return len(lines)


def _extract_call_names(source_snippet: str) -> list[str]:
    """Extract function call names from a source snippet."""
    call_pattern = re.compile(r'(\w+)\s*\(')
    return [m.group(1) for m in call_pattern.finditer(source_snippet)
            if m.group(1) not in ("if", "while", "for", "switch", "catch", "function", "typeof")]
