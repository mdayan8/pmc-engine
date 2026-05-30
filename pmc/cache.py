"""
PMC Engine — Session Cache + Response Compression (Layer 6)
=============================================================
Tracks which symbols have been sent in the current conversation.
On second turn, only deltas are sent — not repeated context.

Also handles response compression: replaces known code blocks
in AI responses with [REF: X] stubs to save on multi-turn context.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CachedSymbol:
    name: str
    sent_at: float  # turn number
    tier_sent: int   # 1, 2, or 3
    version_hash: str = ""


class SessionCache:
    """
    Per-conversation symbol cache.

    Symbols sent at Tier 1 (full code) stay fresh for the entire session
    unless the underlying file changes. Tier 2/3 entries expire sooner.

    TTL is measured in conversation turns, not wall time.
    """

    TIER1_TTL_TURNS = 20
    TIER2_TTL_TURNS = 10
    TIER3_TTL_TURNS = 5

    # Pattern for response compression: function definitions
    _FUNC_PATTERN = re.compile(
        r'(def |async def |class )([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(->[^:]*)?:\n(?:[ \t]+.*\n)*'
    )

    def __init__(self):
        self._cache: dict[str, CachedSymbol] = {}
        self._turn: int = 1
        self._response_refs: dict[str, dict] = {}  # ref_id → expanded content

    def next_turn(self):
        """Call at the start of each new user message."""
        self._turn += 1

    def mark_sent(self, names: list[str], tier: int, file_hashes: dict[str, str] = None):
        """Record that these symbols were sent at the given tier."""
        for name in names:
            self._cache[name] = CachedSymbol(
                name=name,
                sent_at=self._turn,
                tier_sent=tier,
                version_hash=(file_hashes or {}).get(name, ""),
            )

    def is_fresh(self, name: str, current_hash: str = "") -> bool:
        """
        Returns True if symbol was recently sent and hasn't changed.
        Fresh symbols get a score penalty → deprioritized from resend.
        """
        entry = self._cache.get(name)
        if not entry:
            return False

        # Check file changed
        if current_hash and entry.version_hash and entry.version_hash != current_hash:
            del self._cache[name]
            return False

        # Check TTL
        ttl = {1: self.TIER1_TTL_TURNS, 2: self.TIER2_TTL_TURNS, 3: self.TIER3_TTL_TURNS}
        age = self._turn - entry.sent_at
        return age <= ttl.get(entry.tier_sent, 5)

    def fresh_names(self) -> set[str]:
        """All symbol names currently considered fresh."""
        return {n for n in self._cache if self.is_fresh(n)}

    def invalidate(self, name: str):
        """Force re-send of a specific symbol."""
        self._cache.pop(name, None)

    def invalidate_file(self, fpath: str):
        """
        Invalidate all cached symbols from a changed file.
        Call after file save/git-commit webhook.
        """
        to_remove = [
            n for n, e in self._cache.items()
            if fpath in e.name or fpath in getattr(e, 'version_hash', '')
        ]
        for n in to_remove:
            del self._cache[n]

    def clear(self):
        """Reset for new conversation."""
        self._cache.clear()
        self._turn = 1
        self._response_refs.clear()

    def stats(self) -> dict:
        return {
            "cached_symbols": len(self._cache),
            "current_turn": self._turn,
            "fresh": len(self.fresh_names()),
            "response_refs": len(self._response_refs),
        }

    # ── Response Compression ───────────────────────────────────────────────

    def compress_response(self, response: str, known_symbols: dict[str, str]) -> str:
        """
        Compress AI response by replacing known code blocks with [REF: X] stubs.

        known_symbols: dict of symbol_name → file_path for symbols in our index.
        """
        result = response

        for name, filepath in known_symbols.items():
            # Replace full function definitions with [REF: name]
            pattern = rf'(def {name}\s*\([^)]*\)[^:]*:\n(?:[ \t]+.*\n)*)'
            replacement = f'[REF: {name} → {os.path.basename(filepath)}]'

            def replace_func(match):
                full = match.group(1)
                self._response_refs[f"ref_{name}_{self._turn}"] = {
                    "name": name,
                    "file": filepath,
                    "source": full,
                }
                return replacement

            result = re.sub(pattern, replace_func, result)

        return result

    def expand_refs(self, text: str) -> str:
        """
        Expand [REF: X] stubs back to full code before sending to AI.
        """
        ref_pattern = re.compile(r'\[REF:\s*(\w+)\s*→\s*([^\]]+)\]')

        def expand(match):
            name = match.group(1)
            for ref_id, ref_data in self._response_refs.items():
                if ref_data["name"] == name:
                    return ref_data["source"]
            return match.group(0)  # keep REF stub if can't expand

        return ref_pattern.sub(expand, text)


import os
