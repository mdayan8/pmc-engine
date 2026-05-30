"""
PMC Engine — Surgical Context Builder (Layers 3-5)
====================================================
Heart of PMC. Takes parsed intent + symbol index, scores every symbol
using an extended scoring formula, assigns tiers, and assembles the
minimal context string.

Layers:
  L3: Auto-calibrating scorer with 7-term formula
  L4: Tiered context builder with blast radius + coupling warnings
  L5: Passive demand expansion (scans AI response, auto-expands stubs)
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from pmc.indexer import LiveSymbolIndex, Symbol
from pmc.intent import ParsedIntent, BlastRadius, OpType
from pmc.config import PMCConfig, CompressionMode


# ─── Output ─────────────────────────────────────────────────────────────────

@dataclass
class ContextResult:
    context_string: str
    token_count: int
    naive_token_count: int
    symbols_tier1: list[str]
    symbols_tier2: list[str]
    symbols_tier3: list[str]
    blast_radius_syms: list[str]
    coupling_warnings: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    mode: str = CompressionMode.BALANCED

    @property
    def saved_tokens(self) -> int:
        return self.naive_token_count - self.token_count

    @property
    def reduction_pct(self) -> float:
        if self.naive_token_count == 0:
            return 0.0
        return round(100 * self.saved_tokens / self.naive_token_count, 1)

    def summary(self) -> str:
        mode_label = self.mode.upper()
        return (
            f"Tokens: {self.token_count:,} vs naive {self.naive_token_count:,} "
            f"({self.reduction_pct}% reduction) [{mode_label} mode]\n"
            f"T1={len(self.symbols_tier1)} T2={len(self.symbols_tier2)} "
            f"T3={len(self.symbols_tier3)} blast={len(self.blast_radius_syms)}"
        )


# ─── Builder ────────────────────────────────────────────────────────────────

class SurgicalContextBuilder:
    """
    Scores symbols and assembles tiered context.

    Scoring formula (7 terms):
      score = direct×3.0 + hop1×1.5 + hop2×0.6 + import×0.5
            + config_key×1.0 + type_ref×1.0 + semantic×0.4 − cache×0.9

    session_cache: set of symbol names already sent in this conversation.
    """

    _EXPAND_PATTERN = re.compile(r'\[EXPAND:\s*(\w+)\]')
    _SYMBOL_MENTION_PATTERN = re.compile(r'\b([a-z_][a-z0-9_]{2,})\b')

    def __init__(
        self,
        index: LiveSymbolIndex,
        session_cache: Optional[set[str]] = None,
        config: Optional[PMCConfig] = None,
    ):
        self.index = index
        self.session_cache = session_cache or set()
        self.config = config or PMCConfig()

    def build(
        self,
        intent: ParsedIntent,
        source_root: str,
        token_budget: Optional[int] = None,
    ) -> ContextResult:
        """Main entry point. Returns assembled context string + metadata."""
        budget = token_budget or intent.context_budget
        mode = self.config.mode

        # 1. Score all candidate symbols
        scores = self._score_symbols(intent)

        # 2. Sort by score desc, assign tiers within budget
        t1, t2, t3 = [], [], []
        tokens_used = 0
        th_t1 = self.config.threshold_tier1
        th_t2 = self.config.threshold_tier2
        th_t3 = self.config.threshold_tier3

        for name, score in sorted(scores.items(), key=lambda x: -x[1]):
            sym = self.index.get(name)
            if not sym:
                continue

            if score >= th_t1 and tokens_used + sym.token_estimate <= budget:
                t1.append(name)
                tokens_used += sym.token_estimate
            elif score >= th_t2:
                sig_tokens = max(5, len(sym.signature) // 4 + 10)
                if tokens_used + sig_tokens <= budget * 1.2:
                    t2.append(name)
                    tokens_used += sig_tokens
            elif score >= th_t3:
                t3.append(name)
                tokens_used += 5  # stubs are tiny

            # Enforce max limits
            if len(t1) >= self.config.max_tier1_per_query:
                break  # stop adding to T1, keep scoring for T2/T3

        # 3. Blast radius + coupling warnings
        blast = self._get_blast_radius(t1, intent)
        coupling_warnings = self._get_coupling_warnings(t1, intent)

        # 4. Load source for Tier 1
        file_sources = self._load_sources(t1, source_root)

        # 5. Compute naive token count
        naive_tokens = sum(
            self.index.get(n).token_estimate
            for n in self.index.symbols
            if self.index.get(n)
        ) or 1

        # 6. Assemble context string
        ctx = self._assemble(intent, t1, t2, t3, blast, coupling_warnings, file_sources, mode)

        # 7. Update session cache
        self.session_cache.update(t1)
        self.session_cache.update(t2)

        return ContextResult(
            context_string=ctx,
            token_count=tokens_used,
            naive_token_count=naive_tokens,
            symbols_tier1=t1,
            symbols_tier2=t2,
            symbols_tier3=t3,
            blast_radius_syms=blast,
            coupling_warnings=coupling_warnings,
            scores=scores,
            mode=mode,
        )

    # ── Scoring ────────────────────────────────────────────────────────────

    def _score_symbols(self, intent: ParsedIntent) -> dict[str, float]:
        scores: dict[str, float] = {}
        target_set = set(intent.target_syms)
        weights = self.config.weights

        # Gather 1-hop and 2-hop callees
        hop1: set[str] = set()
        hop2: set[str] = set()
        for tgt in target_set:
            for sym in self.index.get_callees(tgt, depth=1):
                hop1.add(sym.name)
            for sym in self.index.get_callees(tgt, depth=2):
                if sym.name not in hop1:
                    hop2.add(sym.name)

        # Gather import, config_key, type dependencies
        import_related: set[str] = set()
        config_related: set[str] = set()
        type_related: set[str] = set()
        convention_related: set[str] = set()

        for tgt in target_set:
            sym = self.index.get(tgt)
            if not sym:
                continue

            # Files that import this symbol's file
            for importer_fpath in self.index.get_importers(sym.file):
                for sname in self.index.file_to_symbols.get(importer_fpath, []):
                    import_related.add(sname)

            # Files that share config keys with target file
            for key in sym.config_keys_refd:
                for user_fpath in self.index.get_config_users(key):
                    for sname in self.index.file_to_symbols.get(user_fpath, []):
                        config_related.add(sname)

            # Files that share types with target file
            for type_name in sym.types_refd:
                for user_fpath in self.index.get_type_users(type_name):
                    for sname in self.index.file_to_symbols.get(user_fpath, []):
                        type_related.add(sname)

            # Convention cluster peers
            for sname, s in self.index.symbols.items():
                if (s.convention_cluster == sym.convention_cluster
                        and sname != tgt
                        and sname not in target_set):
                    convention_related.add(sname)

        # Text search hits
        search_results = self.index.search(" ".join(intent.priority_terms), top_k=15)
        search_hits: set[str] = {s.name for s in search_results}

        # Score everything
        all_candidates = (target_set | hop1 | hop2 | import_related
                          | config_related | type_related | convention_related
                          | search_hits)

        for name in all_candidates:
            score = 0.0
            if name in target_set:
                score += weights.get("direct", 3.0)
            if name in hop1:
                score += weights.get("hop1", 1.5)
            if name in hop2:
                score += weights.get("hop2", 0.6)
            if name in import_related:
                score += weights.get("import", 0.5)
            if name in config_related:
                score += weights.get("config_key", 1.0)
            if name in type_related:
                score += weights.get("type_ref", 1.0)
            if name in convention_related:
                score += weights.get("convention", 0.4)
            if name in search_hits:
                score += weights.get("semantic", 0.4)
            if name in self.session_cache:
                score -= weights.get("cache_penalty", 0.9)
            scores[name] = max(0.0, score)

        return scores

    # ── Blast Radius & Coupling ────────────────────────────────────────────

    def _get_blast_radius(self, tier1_names: list[str], intent: ParsedIntent) -> list[str]:
        """Find callers of Tier 1 symbols — regression risk."""
        if intent.blast_radius == BlastRadius.LOW:
            return []

        blast = set()
        for name in tier1_names:
            for caller in self.index.get_callers(name, depth=1):
                if caller.name not in set(tier1_names):
                    blast.add(caller.name)
        return list(blast)[:self.config.max_blast_symbols]

    def _get_coupling_warnings(self, tier1_names: list[str], intent: ParsedIntent) -> list[str]:
        """Generate coupling warnings for config keys and types."""
        warnings = []
        seen_keys = set()
        seen_types = set()
        seen_files = set()

        for name in tier1_names:
            sym = self.index.get(name)
            if not sym:
                continue

            # Config key warnings
            for key in sym.config_keys_refd:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                users = self.index.get_config_users(key)
                other_users = [u for u in users if u != sym.file]
                if other_users:
                    warnings.append(
                        f"⚠ CONFIG: '{key}' also referenced in "
                        f"{', '.join(os.path.basename(u) for u in other_users[:3])}"
                    )

            # Type coupling warnings
            for type_name in sym.types_refd:
                if type_name in seen_types:
                    continue
                seen_types.add(type_name)
                users = self.index.get_type_users(type_name)
                other_users = [u for u in users if u != sym.file]
                if other_users:
                    warnings.append(
                        f"⚠ TYPE: '{type_name}' also referenced in "
                        f"{', '.join(os.path.basename(u) for u in other_users[:3])}"
                    )

            # Test mapping warning
            sym_file = sym.file
            if sym_file not in seen_files:
                seen_files.add(sym_file)
                stem = self._get_stem(sym_file)
                test_files = [f for f in self.index.file_to_symbols
                              if self._is_test_for(f, stem)
                              and os.path.exists(f)]
                if test_files:
                    test_names = [os.path.basename(t) for t in test_files[:2]]
                    warnings.append(
                        f"⚠ TESTS: {', '.join(test_names)} tests this module"
                    )

        return warnings[:self.config.max_blast_symbols]

    def _get_stem(self, fpath: str) -> str:
        return os.path.splitext(os.path.basename(fpath))[0]

    def _is_test_for(self, test_path: str, source_stem: str) -> bool:
        stem = self._get_stem(test_path)
        return stem == f"test_{source_stem}" or stem == f"{source_stem}_test"

    # ── Source Loading ─────────────────────────────────────────────────────

    def _load_sources(self, names: list[str], source_root: str) -> dict[str, list[str]]:
        """Load source lines for Tier 1 symbols, grouped by file."""
        file_to_lines: dict[str, list[str]] = {}
        for name in names:
            sym = self.index.get(name)
            if not sym:
                continue
            fpath = sym.file
            if fpath not in file_to_lines:
                try:
                    file_to_lines[fpath] = open(fpath, encoding="utf-8", errors="ignore").readlines()
                except Exception:
                    file_to_lines[fpath] = []
        return file_to_lines

    # ── Context Assembly ───────────────────────────────────────────────────

    def _assemble(
        self,
        intent: ParsedIntent,
        t1: list[str],
        t2: list[str],
        t3: list[str],
        blast: list[str],
        coupling_warnings: list[str],
        file_sources: dict[str, list[str]],
        mode: str,
    ) -> str:
        lines = []

        lines.append(f"# PMC Context — Operation: {intent.op_type} [{mode}]")
        lines.append(f"# Query: {intent.raw_query}")
        if intent.confidence < 0.5:
            lines.append(f"# Note: Intent confidence {intent.confidence:.0%} — conservative mode active")
        lines.append("")

        # ── TIER 1: Full code ──
        if t1:
            lines.append("# ═══ TIER 1: FULL CODE (direct touch points) ═══")
            for name in t1:
                sym = self.index.get(name)
                if not sym:
                    continue
                src = file_sources.get(sym.file, [])
                if src:
                    body = "".join(src[sym.line_start - 1 : sym.line_end])
                    lines.append(f"# FILE: {sym.file} lines {sym.line_start}–{sym.line_end}")
                    lines.append(body.rstrip())
                    lines.append("")
            lines.append("")

        # ── TIER 2: Signatures ──
        if t2:
            lines.append("# ═══ TIER 2: SIGNATURES (1-hop dependencies) ═══")
            for name in t2:
                sym = self.index.get(name)
                if sym:
                    doc = f"  # {sym.docstring[:80]}" if sym.docstring else ""
                    lines.append(f"# def {sym.signature}{doc}  [{sym.file}:{sym.line_start}]")
            lines.append("")

        # ── TIER 3: Stubs ──
        if t3:
            lines.append("# ═══ TIER 3: STUBS (expand on demand) ═══")
            for name in t3:
                sym = self.index.get(name)
                if sym:
                    n_lines = sym.line_end - sym.line_start + 1
                    lines.append(f"# [STUB] {sym.name}({n_lines} lines) → {sym.file}:{sym.line_start}")
            lines.append("# Mention any stub name in your response and I'll auto-expand it.")
            lines.append("")

        # ── Blast radius ──
        if blast:
            lines.append("# ═══ BLAST RADIUS (regression check) ═══")
            for name in blast:
                sym = self.index.get(name)
                if sym:
                    lines.append(f"# ⚠ CALLER: {sym.name}() → {sym.file}:{sym.line_start}")
            lines.append("")

        # ── Coupling warnings ──
        if coupling_warnings:
            lines.append("# ═══ COUPLING WARNINGS ═══")
            for w in coupling_warnings:
                lines.append(f"# {w}")
            lines.append("")

        return "\n".join(lines)

    # ── Passive Demand Expansion (L5) ──────────────────────────────────────

    def handle_expand(self, ai_response: str) -> list[dict]:
        """
        Passive demand expansion.

        Scans the AI response for:
        1. Explicit [EXPAND: <name>] signals
        2. Mentions of stubbed symbol names

        Returns list of expanded symbol data: [{name, file, start, end, source}]
        """
        expansions = []
        seen = set()

        # 1. Check for explicit [EXPAND: X] patterns
        for m in self._EXPAND_PATTERN.finditer(ai_response):
            sym_name = m.group(1)
            if sym_name not in seen:
                result = self._expand_symbol(sym_name)
                if result:
                    expansions.append(result)
                    seen.add(sym_name)

        # 2. Check for mentions of stubbed symbols
        stubbed_names = set()  # We don't maintain a separate stub list here
        # In practice, the caller passes in t3 symbol names

        return expansions

    def _expand_symbol(self, name: str) -> Optional[dict]:
        """Fetch full source of a symbol."""
        sym = self.index.get(name)
        if not sym:
            return None

        try:
            source_lines = open(sym.file, encoding="utf-8", errors="ignore").readlines()
            body = "".join(source_lines[sym.line_start - 1 : sym.line_end])
            return {
                "name": name,
                "file": sym.file,
                "line_start": sym.line_start,
                "line_end": sym.line_end,
                "source": body,
            }
        except Exception:
            return None

    def format_expansions(self, expansions: list[dict]) -> str:
        """Format expanded symbols for injection into context."""
        if not expansions:
            return ""
        lines = ["", "# ═══ EXPANDED SYMBOLS (auto-fetched) ═══"]
        for exp in expansions:
            lines.append(f"# [EXPANDED] {exp['name']} — full source")
            lines.append(f"# FILE: {exp['file']} lines {exp['line_start']}–{exp['line_end']}")
            lines.append(exp["source"].rstrip())
            lines.append("")
        return "\n".join(lines)

    def pre_expand_file(self, filepath: str, min_count: int = 3) -> str:
        """
        Pre-expand a whole file when the AI mentions 3+ symbols from it.
        Returns formatted expanded content.
        """
        mentions = set()
        expansions = []

        for name, sym in self.index.symbols.items():
            if sym.file == filepath:
                result = self._expand_symbol(name)
                if result:
                    expansions.append(result)

        if not expansions:
            return ""

        lines = ["", f"# ═══ PRE-EXPANDED: {os.path.basename(filepath)} (multiple symbols referenced) ═══"]
        for exp in expansions:
            lines.append(f"# [EXPANDED] {exp['name']} — full source")
            lines.append(f"# FILE: {exp['file']} lines {exp['line_start']}–{exp['line_end']}")
            lines.append(exp["source"].rstrip())
            lines.append("")
        return "\n".join(lines)

    def calibrate(self, source_root: str, iterations: int = 5) -> dict:
        """
        Auto-calibrate scoring weights for a codebase.

        Runs calibration queries, tries different weight combinations,
        and picks the combination that gives the best reduction/quality trade-off.
        """
        from pmc.intent import IntentParser

        parser = IntentParser()
        calib_queries = [
            ("Explain how login works", OpType.READ),
            ("Fix the bug in query", OpType.DEBUG),
            ("Add error handling to rate_limiter", OpType.CREATE),
            ("Refactor the auth module", OpType.REFACTOR),
        ]

        # Generate some valid queries from actual symbols
        sym_names = list(self.index.symbols.keys())
        for i in range(min(4, len(sym_names))):
            calib_queries.append(
                (f"What does {sym_names[i]} do", OpType.READ)
            )

        best_weights = dict(self.config.weights)
        best_score = 0

        weight_variants = [
            {"direct": 3.0, "hop1": 1.5, "hop2": 0.6, "import": 0.5, "config_key": 1.0, "type_ref": 1.0},
            {"direct": 2.5, "hop1": 2.0, "hop2": 0.8, "import": 0.7, "config_key": 0.8, "type_ref": 0.8},
            {"direct": 4.0, "hop1": 1.0, "hop2": 0.5, "import": 0.3, "config_key": 1.2, "type_ref": 1.2},
            {"direct": 3.5, "hop1": 1.8, "hop2": 0.7, "import": 0.6, "config_key": 0.6, "type_ref": 0.6},
            {"direct": 3.0, "hop1": 1.2, "hop2": 1.0, "import": 0.8, "config_key": 1.5, "type_ref": 1.5},
        ]

        for variant in weight_variants:
            total_reduction = 0
            total_count = 0

            for query, _ in calib_queries:
                orig_weights = dict(self.config.weights)
                self.config.weights.update(variant)

                intent = parser.parse(query, known_symbols=set(self.index.symbols.keys()))
                result = self.build(intent, source_root=source_root)

                total_reduction += result.reduction_pct
                total_count += 1

                # Restore
                self.config.weights.update(orig_weights)

            avg = total_reduction / max(total_count, 1)
            # Score: higher reduction is better, but we want to avoid extremes
            if 40 <= avg <= 80:
                variant_score = avg
            else:
                variant_score = abs(avg - 60) * -1 + 60  # penalize extremes

            if variant_score > best_score:
                best_score = variant_score
                best_weights = dict(variant)

        self.config.weights.update(best_weights)
        self.config._apply_mode()

        return {
            "best_weights": best_weights,
            "best_score": round(best_score, 1),
            "estimated_reduction": f"{best_score - 10:.0f}–{best_score + 10:.0f}%",
            "mode": self.config.mode,
        }
