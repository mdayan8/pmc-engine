"""
PMC Engine — Predictive Minimal Context
========================================
Cut AI coding token costs by 40-80% via AST-based surgical context compression.

Quick start:
    from pmc import PMCEngine

    engine = PMCEngine()
    engine.index("./my_project")

    result = engine.compress("Fix the race condition in the login function")
    print(result.context_string)   # send to Claude
    print(result.summary())        # token savings report

Integration:
    HTTP proxy:  pmc serve  (Anthropic + OpenAI compatible)
    MCP server:  pmc mcp    (Claude Code / Cursor native tool)
    Python lib:  from pmc import PMCEngine
    Claude Code: pmc install-cc-hooks
"""

from pmc.indexer import LiveSymbolIndex
from pmc.intent import IntentParser
from pmc.context import SurgicalContextBuilder, ContextResult
from pmc.cache import SessionCache
from pmc.verify import Verifier
from pmc.config import PMCConfig, CompressionMode


class PMCEngine:
    """
    Predictive Minimal Context Engine.

    Seven-layer pipeline:
        L1: LiveSymbolIndex   — AST symbol index + 6-source dep graph
        L2: IntentParser      — Hybrid regex+embedding intent classification
        L3: SurgicalSelector  — 7-term scoring formula
        L4: ContextBuilder    — Tiered context assembly
        L5: PassiveExpansion  — Auto-expand stubs from AI response
        L6: SessionCache      — Diff-only updates + response compression
        L7: Verification      — Quality measurement + auto-tuning

    Args:
        config: Optional PMCConfig. Loads from .pmc.yaml if not provided.
    """

    def __init__(self, config: PMCConfig = None):
        self.config = config or PMCConfig.load()
        self._index = LiveSymbolIndex()
        self.parser = IntentParser(use_embeddings=False)
        self.session = SessionCache()
        self.verifier = None
        self._indexed = False

    # ── Setup ──────────────────────────────────────────────────────────────

    def index(self, directory: str) -> dict:
        """
        Build the symbol index for a codebase directory.
        Returns stats: files, symbols, edges, duration_ms.
        """
        if not self.config.enabled:
            return {"files": 0, "symbols": 0, "edges": 0, "duration_ms": 0, "bypass": True}

        stats = self._index.build_index(directory)
        self._indexed = True
        return stats

    def update_file(self, fpath: str) -> bool:
        """Incremental update for a single file."""
        if not self.config.enabled or not self._indexed:
            return False
        changed = self._index.update_file(fpath)
        if changed:
            self.session.invalidate_file(fpath)
        return changed

    def enable_embeddings(self):
        """Enable optional embedding-based intent parser."""
        self.parser = IntentParser(use_embeddings=True)

    # ── Main API ───────────────────────────────────────────────────────────

    def compress(
        self,
        query: str,
        source_root: str = ".",
        token_budget: int = None,
        new_turn: bool = True,
        ai_response: str = None,
    ) -> ContextResult:
        """
        Compress a developer query into surgical minimal context.

        Args:
            query:        The developer's natural language instruction.
            source_root:  Root of the codebase.
            token_budget: Override default budget (tokens).
            new_turn:     True = new user message.
            ai_response:  Previous AI response to scan for expansions.

        Returns:
            ContextResult with .context_string (send to AI) and .summary().
        """
        if not self.config.enabled:
            return self._passthrough(query)

        if not self._indexed:
            raise RuntimeError(
                "Call engine.index('./your_project') before engine.compress()."
            )

        if new_turn:
            self.session.next_turn()

        # L2: Parse intent
        known_symbols = set(self._index.symbols.keys())
        intent = self.parser.parse(query, known_symbols=known_symbols)

        # Inject intent confidence into mode
        if intent.confidence < 0.4:
            original_mode = self.config.mode
            self.config.mode = CompressionMode.CONSERVATIVE
            self.config._apply_mode()

        # L3 + L4: Score and assemble
        builder = SurgicalContextBuilder(
            index=self._index,
            session_cache=self.session.fresh_names(),
            config=self.config,
        )
        result = builder.build(intent, source_root=source_root, token_budget=token_budget)

        # L5: Passive expansion from previous AI response
        if ai_response:
            expansions = builder.handle_expand(ai_response)
            if expansions:
                expanded = builder.format_expansions(expansions)
                result.context_string += expanded

                # Check for pre-expansion (3+ symbols from same file)
                file_mentions: dict[str, int] = {}
                for exp in expansions:
                    f = exp.get("file", "")
                    file_mentions[f] = file_mentions.get(f, 0) + 1
                for fpath, count in file_mentions.items():
                    if count >= self.config.pre_expand_threshold:
                        pre = builder.pre_expand_file(fpath)
                        if pre:
                            result.context_string += pre

        # Restore mode
        if intent.confidence < 0.4:
            self.config.mode = original_mode
            self.config._apply_mode()

        # L6: Update session cache
        self.session.mark_sent(result.symbols_tier1, tier=1)
        self.session.mark_sent(result.symbols_tier2, tier=2)
        self.session.mark_sent(result.symbols_tier3, tier=3)

        return result

    def new_conversation(self):
        """Reset session cache for a new chat session."""
        self.session.clear()

    # ── Verification ───────────────────────────────────────────────────────

    def verify(self, source_root: str, num_tasks: int = 20) -> dict:
        """Run quality verification loop."""
        self.verifier = Verifier(self)
        result = self.verifier.verify(source_root, num_tasks=num_tasks)
        return result

    def calibrate(self, source_root: str) -> dict:
        """Auto-calibrate scoring weights for this codebase."""
        builder = SurgicalContextBuilder(
            index=self._index,
            session_cache=set(),
            config=self.config,
        )
        return builder.calibrate(source_root)

    # ── Stats ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return combined engine stats."""
        return {
            "index": self._index.stats(),
            "session": self.session.stats(),
            "config_mode": self.config.mode,
            "config_enabled": self.config.enabled,
        }

    # ── Internal ───────────────────────────────────────────────────────────

    def _passthrough(self, query: str) -> ContextResult:
        """Bypass mode — pass query through unmodified."""
        return ContextResult(
            context_string=query,
            token_count=0,
            naive_token_count=0,
            symbols_tier1=[],
            symbols_tier2=[],
            symbols_tier3=[],
            blast_radius_syms=[],
            mode="disabled",
        )
