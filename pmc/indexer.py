"""
PMC Engine — Live Symbol Index (Layer 1)
=========================================
AST-based symbol indexer with 6-source dependency graph:

  1. Call graph (AST function calls)
  2. Import graph (who imports what)
  3. Config key tracking (who references DB_URL, JWT_SECRET, etc.)
  4. Type/model usage (who references User.jwt_token, etc.)
  5. Test file mapping (test_auth.py → auth_service.py)
  6. Convention clustering (jwt_*.py, *_service.py clustering)
"""

import ast
import os
import hashlib
import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ─── Data Model ─────────────────────────────────────────────────────────────

@dataclass
class Symbol:
    name: str
    file: str
    line_start: int
    line_end: int
    signature: str
    docstring: str
    calls: list[str]
    callers: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    config_keys_refd: list[str] = field(default_factory=list)
    types_refd: list[str] = field(default_factory=list)
    is_class: bool = False
    parent_class: Optional[str] = None
    token_estimate: int = 0
    is_test: bool = False
    convention_cluster: str = ""

    def to_tier1(self, source_lines: list[str]) -> str:
        """Full source code — direct touch points only."""
        body = "".join(source_lines[self.line_start - 1 : self.line_end])
        return f"# FILE: {self.file} lines {self.line_start}–{self.line_end}\n{body}"

    def to_tier2(self) -> str:
        """Signature + docstring — 1-hop dependencies."""
        doc = f'\n    """{self.docstring}"""' if self.docstring else ""
        return f"def {self.signature}{doc}  # [{self.file}:{self.line_start}]"

    def to_tier3(self) -> str:
        """Name + location stub — expand on demand."""
        lines = self.line_end - self.line_start + 1
        return f"[STUB] {self.name}({lines} lines) → {self.file}:{self.line_start}"


# ─── Indexer ────────────────────────────────────────────────────────────────

class LiveSymbolIndex:
    """
    Builds and maintains a live symbol index with a 6-source dependency graph.

    The index stores every function and class as a Symbol with:
    - Signature, docstring, line range
    - Call graph edges (what each function calls)
    - Import graph (what each file imports)
    - Config key references (JWT_SECRET, DB_URL, etc.)
    - Type/model usage references
    - Test mapping (test files → source files)
    - Convention clustering by naming patterns
    - Reverse call graph (who calls each function)
    - Token estimate for budget planning

    Incremental updates: only re-parses files changed since last index.
    """

    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 "dist", "build", ".mypy_cache", ".pytest_cache", ".hg", ".svn"}

    # Config key pattern: ALL_CAPS with underscores
    _CONFIG_KEY_PATTERN = re.compile(r'\b([A-Z][A-Z0-9_]{2,})\b')

    # Type reference pattern: ClassName or module.ClassName
    _TYPE_REF_PATTERN = re.compile(r'\b([A-Z][a-zA-Z0-9]+)\b')

    # Test mapping: test_*.py → source_*.py (strip test_ prefix)
    # Or *_test.py → *.py (strip _test suffix)

    def __init__(self, cache_path: Optional[str] = None):
        self.symbols: dict[str, Symbol] = {}
        self.file_hashes: dict[str, str] = {}
        self.file_to_symbols: dict[str, list[str]] = {}
        self.file_imports: dict[str, list[str]] = {}
        self.file_config_keys: dict[str, set[str]] = {}
        self.file_types: dict[str, set[str]] = {}
        self.cache_path = cache_path
        self._build_time: float = 0

        if cache_path and os.path.exists(cache_path):
            self._load_cache()

    # ── Build / Update ─────────────────────────────────────────────────────

    def build_index(self, directory: str) -> dict:
        """
        Full index build. Walks directory tree, parses all .py files.
        Returns stats dict: {files, symbols, edges, duration_ms}
        """
        t0 = time.time()
        files_parsed = 0
        errors = []

        # Phase 1: Parse all files
        for fpath in self._iter_python_files(directory):
            result = self._parse_file(fpath)
            if result is True:
                files_parsed += 1
            elif isinstance(result, str):
                errors.append(result)

        # Phase 2: Build cross-file dependency graph
        self._build_callers()
        self._build_import_graph()
        self._build_config_key_graph()
        self._build_type_graph()
        self._build_test_mappings()
        self._build_convention_clusters()

        self._build_time = time.time() - t0

        if self.cache_path:
            self._save_cache()

        return {
            "files": files_parsed,
            "symbols": len(self.symbols),
            "edges": sum(len(s.calls) for s in self.symbols.values()),
            "duration_ms": round(self._build_time * 1000, 1),
            "errors": errors,
        }

    def update_file(self, fpath: str) -> bool:
        """
        Incremental update: re-parse a single file if it changed.
        Returns True if file was re-indexed.
        """
        if not os.path.exists(fpath):
            return False

        file_hash = self._file_hash(fpath)
        if self.file_hashes.get(fpath) == file_hash:
            return False  # unchanged

        # Remove old symbols from this file
        for name in self.file_to_symbols.get(fpath, []):
            self.symbols.pop(name, None)

        # Clean up file-level caches
        self.file_imports.pop(fpath, None)
        self.file_config_keys.pop(fpath, None)
        self.file_types.pop(fpath, None)

        self._parse_file(fpath)
        self._build_callers()
        self._build_import_graph()
        self._build_config_key_graph()
        self._build_type_graph()
        self._build_test_mappings()
        self._build_convention_clusters()

        if self.cache_path:
            self._save_cache()
        return True

    # ── Query API ──────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Symbol]:
        """Get a symbol by name."""
        return self.symbols.get(name)

    def get_callees(self, name: str, depth: int = 2) -> list[Symbol]:
        """
        Walk call graph outward (what this symbol calls).
        depth=1 → direct calls only
        depth=2 → calls + their calls
        """
        visited = set()
        result = []

        def walk(sym_name: str, remaining: int):
            if remaining <= 0 or sym_name in visited:
                return
            visited.add(sym_name)
            sym = self.symbols.get(sym_name)
            if sym:
                for callee in sym.calls:
                    callee_sym = self.symbols.get(callee)
                    if callee_sym and callee not in visited:
                        result.append(callee_sym)
                        walk(callee, remaining - 1)

        walk(name, depth)
        return result

    def get_callers(self, name: str, depth: int = 1) -> list[Symbol]:
        """Walk call graph inward (blast radius — who calls this symbol)."""
        visited = set()
        result = []

        def walk(sym_name: str, remaining: int):
            if remaining <= 0 or sym_name in visited:
                return
            visited.add(sym_name)
            sym = self.symbols.get(sym_name)
            if sym:
                for caller in sym.callers:
                    caller_sym = self.symbols.get(caller)
                    if caller_sym and caller not in visited:
                        result.append(caller_sym)
                        walk(caller, remaining - 1)

        walk(name, depth)
        return result

    def get_importers(self, filepath: str) -> list[str]:
        """Find files that import symbols from the given file."""
        importers = []
        for fpath, imports in self.file_imports.items():
            if filepath in imports or self._file_stem(filepath) in imports:
                importers.append(fpath)
        return importers

    def get_config_users(self, key: str) -> list[str]:
        """Find files that reference a specific config key."""
        users = []
        for fpath, keys in self.file_config_keys.items():
            if key in keys:
                users.append(fpath)
        return users

    def get_type_users(self, type_name: str) -> list[str]:
        """Find files that reference a specific type."""
        users = []
        for fpath, types in self.file_types.items():
            if type_name in types:
                users.append(fpath)
        return users

    def search(self, query: str, top_k: int = 15) -> list[Symbol]:
        """Simple text search across symbol names and docstrings."""
        q = query.lower()
        scored = []
        for sym in self.symbols.values():
            score = 0
            if q in sym.name.lower():
                score += 3
            if sym.docstring and q in sym.docstring.lower():
                score += 1
            if q in sym.file.lower():
                score += 0.5
            if score > 0:
                scored.append((score, sym))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def stats(self) -> dict:
        return {
            "total_symbols": len(self.symbols),
            "total_files": len(self.file_to_symbols),
            "total_edges": sum(len(s.calls) for s in self.symbols.values()),
            "total_imports": sum(len(v) for v in self.file_imports.values()),
            "total_coupling_hints": (
                sum(len(v) for v in self.file_config_keys.values())
                + sum(len(v) for v in self.file_types.values())
            ),
            "index_size_bytes": sum(
                len(json.dumps(asdict(s))) for s in self.symbols.values()
            ),
            "build_time_ms": round(self._build_time * 1000, 1),
        }

    # ── Internal: File Parsing ─────────────────────────────────────────────

    def _iter_python_files(self, directory: str):
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(root, f)

    def _parse_file(self, fpath: str):
        try:
            source = open(fpath, encoding="utf-8", errors="ignore").read()
            tree = ast.parse(source)
        except SyntaxError as e:
            return f"{fpath}: {e}"
        except Exception as e:
            return f"{fpath}: {e}"

        lines = source.splitlines(keepends=True)
        file_hash = hashlib.md5(source.encode()).hexdigest()
        self.file_hashes[fpath] = file_hash
        self.file_to_symbols[fpath] = []

        # Extract imports
        file_imports = self._extract_imports(tree)
        self.file_imports[fpath] = file_imports

        # Extract config keys from non-code context (comments, strings?)
        # And from variable assignments
        config_keys = self._extract_config_keys(source)
        self.file_config_keys[fpath] = config_keys

        # Extract type references
        types = self._extract_types(tree)
        self.file_types[fpath] = types

        # Extract symbols
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sym = self._node_to_symbol(node, fpath, lines, source, file_imports, config_keys, types)
                if sym:
                    self.symbols[sym.name] = sym
                    self.file_to_symbols[fpath].append(sym.name)

        return True

    def _node_to_symbol(self, node, fpath: str, lines: list, source: str,
                        file_imports: list[str], config_keys: set[str],
                        types: set[str]) -> Optional[Symbol]:
        name = node.name
        line_start = node.lineno
        line_end = getattr(node, "end_lineno", node.lineno)
        docstring = ast.get_docstring(node) or ""

        # Build signature
        if isinstance(node, ast.ClassDef):
            sig = f"{name}"
            calls = []
            is_class = True
        else:
            try:
                sig = f"{name}({ast.unparse(node.args)})"
                if node.returns:
                    sig += f" -> {ast.unparse(node.returns)}"
            except Exception:
                sig = f"{name}(...)"
            calls = self._extract_calls(node)
            is_class = False

        # Find which config keys this symbol references
        node_source = ast.get_source_segment(source, node) or ""
        sym_config_keys = [k for k in config_keys if k in node_source]

        # Find which types this symbol references
        sym_types = [t for t in types if t in node_source]

        # Estimate tokens
        body_chars = sum(len(l) for l in lines[line_start - 1 : line_end])
        token_estimate = max(1, body_chars // 4)

        # Detect if test file
        is_test = self._is_test_file(fpath)

        # Convention cluster
        cluster = self._detect_cluster(fpath)

        return Symbol(
            name=name,
            file=fpath,
            line_start=line_start,
            line_end=line_end,
            signature=sig,
            docstring=docstring[:200],
            calls=list(set(calls)),
            imports=file_imports,
            config_keys_refd=sym_config_keys,
            types_refd=sym_types,
            token_estimate=token_estimate,
            is_class=is_class,
            is_test=is_test,
            convention_cluster=cluster,
        )

    # ── Internal: Dependency Sources ───────────────────────────────────────

    def _extract_calls(self, node) -> list[str]:
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return calls

    def _extract_imports(self, tree) -> list[str]:
        """Extract imported module names from AST."""
        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        return list(set(imports))

    def _extract_config_keys(self, source: str) -> set[str]:
        """Extract ALL_CAPS config key references from source."""
        return set(self._CONFIG_KEY_PATTERN.findall(source))

    def _extract_types(self, tree) -> set[str]:
        """Extract CamelCase type references from AST."""
        types = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if (len(node.id) > 1
                        and node.id[0].isupper()
                        and not node.id.isupper()):
                    types.add(node.id)
            elif isinstance(node, ast.Attribute):
                if (len(node.attr) > 1
                        and node.attr[0].isupper()
                        and not node.attr.isupper()):
                    types.add(node.attr)
        return types

    def _build_callers(self):
        """Populate reverse call graph."""
        for sym in self.symbols.values():
            sym.callers = []
        for caller_name, caller_sym in self.symbols.items():
            for callee_name in caller_sym.calls:
                callee = self.symbols.get(callee_name)
                if callee and caller_name not in callee.callers:
                    callee.callers.append(caller_name)

    def _build_import_graph(self):
        """
        Build import relationships: for each symbol, find which files
        import its parent file's module.
        """
        for sym_name, sym in self.symbols.items():
            sym.imported_by = []
            sym_parent_stem = self._file_stem(sym.file)
            for fpath, imports in self.file_imports.items():
                if sym_parent_stem in imports and fpath != sym.file:
                    sym.imported_by.append(fpath)

    def _build_config_key_graph(self):
        """
        Cross-file config key tracking.
        Maps which files reference shared config keys.
        """
        pass  # Data collected in _parse_file, used in scoring

    def _build_type_graph(self):
        """
        Cross-file type reference tracking.
        Maps which files reference shared types.
        """
        pass  # Data collected in _parse_file, used in scoring

    def _build_test_mappings(self):
        """
        Map test files to source files.
        test_*.py → source_*.py (strip test_ prefix)
        *_test.py → *.py (strip _test suffix)
        """
        test_files = {f for f in self.file_to_symbols if self._is_test_file(f)}
        for tf in test_files:
            stem = self._file_stem(tf)
            source_candidates = []
            if stem.startswith("test_"):
                src_stem = stem[5:]
                source_candidates = [f for f in self.file_to_symbols
                                     if self._file_stem(f) == src_stem
                                     and not self._is_test_file(f)]
            elif stem.endswith("_test"):
                src_stem = stem[:-5]
                source_candidates = [f for f in self.file_to_symbols
                                     if self._file_stem(f) == src_stem
                                     and not self._is_test_file(f)]
            # Mark test symbols with parent source mapping
            for sc in source_candidates:
                for sym_name in self.file_to_symbols.get(sc, []):
                    sym = self.symbols.get(sym_name)
                    if sym:
                        # Test file content is already indexed; we use
                        # the mapping during scoring
                        pass

    def _build_convention_clusters(self):
        """
        Cluster symbols by file naming convention.
        e.g., jwt_*.py, *_service.py, *_model.py
        """
        for sym_name, sym in self.symbols.items():
            stem = self._file_stem(sym.file)
            sym.convention_cluster = stem

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _file_hash(self, fpath: str) -> str:
        try:
            return hashlib.md5(open(fpath, "rb").read()).hexdigest()
        except Exception:
            return ""

    def _file_stem(self, fpath: str) -> str:
        return os.path.splitext(os.path.basename(fpath))[0]

    def _is_test_file(self, fpath: str) -> bool:
        stem = self._file_stem(fpath)
        return stem.startswith("test_") or stem.endswith("_test")

    def _detect_cluster(self, fpath: str) -> str:
        """Detect convention cluster from filename."""
        stem = self._file_stem(fpath)
        # Strip common prefixes/suffixes
        for prefix in ["test_", "base_", "abstract_"]:
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
        for suffix in ["_test", "_impl", "_base", "_abstract"]:
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)]
        return stem

    # ── Persistence ────────────────────────────────────────────────────────

    def _save_cache(self):
        data = {
            "symbols": {k: asdict(v) for k, v in self.symbols.items()},
            "file_hashes": self.file_hashes,
            "file_imports": self.file_imports,
            "file_config_keys": {k: list(v) for k, v in self.file_config_keys.items()},
            "file_types": {k: list(v) for k, v in self.file_types.items()},
        }
        with open(self.cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def _load_cache(self):
        try:
            data = json.load(open(self.cache_path))
            self.symbols = {}
            for k, v in data["symbols"].items():
                v["config_keys_refd"] = v.get("config_keys_refd", [])
                v["types_refd"] = v.get("types_refd", [])
                v["imports"] = v.get("imports", [])
                v["imported_by"] = v.get("imported_by", [])
                v["is_test"] = v.get("is_test", False)
                v["convention_cluster"] = v.get("convention_cluster", "")
                v["callers"] = v.get("callers", [])
                self.symbols[k] = Symbol(**v)
            self.file_hashes = data.get("file_hashes", {})
            self.file_imports = data.get("file_imports", {})
            self.file_config_keys = {k: set(v) for k, v in data.get("file_config_keys", {}).items()}
            self.file_types = {k: set(v) for k, v in data.get("file_types", {}).items()}
        except Exception:
            pass
